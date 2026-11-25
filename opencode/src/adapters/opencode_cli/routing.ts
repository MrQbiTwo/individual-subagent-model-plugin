/**
 * OpenCode adapter for the routing core.
 *
 * Registers the discovery tool, the context enrichment hook, the `subagent`
 * tool enforcement hook and persistent per-agent model defaults. This is the
 * only layer that imports the V2 server SDK; all decisions live in `universal/`.
 */

import type { Context as PluginContext } from "@opencode/plugin/promise/plugin";

import { applyRuleMutation, decideWithScopes } from "#universal/domain/policy";
import { buildCatalogNote, resolveSubagentRoute } from "#universal/domain/routing";
import { parseModelSelector } from "#universal/domain/selector";
import type {
  AllowlistRule,
  Catalog,
  CoreEvent,
  ListPermittedModelsInput,
  ListPermittedModelsOutput,
  ModelRef,
  RuleMutation,
  ScopeName,
  SubagentToolInput,
} from "#universal/domain/types";
import type { ModelService } from "#universal/services/catalog_service";
import type { ConfigStore } from "#universal/ports";

/** Dependencies supplied by `setupServerPlugin`. */
export interface ServerDeps {
  readonly modelService: ModelService;
  readonly configStore: ConfigStore;
  readonly projectKey: string;
  readonly emit: (event: CoreEvent) => Promise<void>;
}

export interface RoutingHandle {
  /** Re-read persisted agent defaults and replay the agent transform. */
  refresh(): Promise<void>;
  dispose(): Promise<void>;
}

/** Tool hook input is mutable; the shared contract declares fields readonly. */
type MutableSubagentInput = { -readonly [K in keyof SubagentToolInput]: SubagentToolInput[K] };

const SELECTOR_NOTE =
  "Use provider/id#variant in the subagent tool's model parameter; the suffix selects the effort level. " +
  "Only the listed models are permitted for subagents.";

/**
 * Apply a rule mutation through the shared policy engine. The scope is kept in
 * the signature so RPC/tool callers share one mutation contract.
 */
export async function mutateRuleFromTool(
  rule: AllowlistRule,
  mutation: RuleMutation,
  _scope: ScopeName,
): Promise<AllowlistRule> {
  return applyRuleMutation(rule, mutation);
}

/** Register the four routing integrations and return a disposer. */
export async function registerRouting(ctx: PluginContext, deps: ServerDeps): Promise<RoutingHandle> {
  const registrations: Array<{ dispose(): Promise<void> }> = [];
  let agentDefaults: Readonly<Record<string, string>> = {};
  let cachedAgentDefaults = "";

  // Rules are read on every call so config file edits take effect immediately.
  const readRules = async (): Promise<{ global: AllowlistRule; project: AllowlistRule }> => {
    const [global, project] = await Promise.all([
      deps.configStore.read("global"),
      deps.configStore.read("project", deps.projectKey),
    ]);
    return { global, project };
  };

  const listPermitted = async (input: ListPermittedModelsInput): Promise<ListPermittedModelsOutput> => {
    const { global, project } = await readRules();
    const models = deps.modelService.current().models.filter(
      (model) =>
        decideWithScopes(model, global, project).allowed &&
        (input.providerID === undefined || model.providerID === input.providerID),
    );
    return { models, note: SELECTOR_NOTE };
  };

  // 1. Discovery tool: exposes only permitted models and their effort variants.
  const toolRegistration = await ctx.tool.transform((editor) => {
    editor.add({
      name: "subagent_models",
      description: "List models permitted for subagents, with provider and effort variants",
      input: {
        type: "object",
        properties: { providerID: { type: "string" } },
        additionalProperties: false,
      },
      options: { namespace: "subagent_models", codemode: true },
      execute: async (input) => ({
        content: JSON.stringify(await listPermitted(input as ListPermittedModelsInput)),
      }),
    });
  });
  registrations.push(toolRegistration);
  await ctx.tool.reload();

  // 2. Context hook: inform the primary model without hiding any model from it.
  const contextRegistration = await ctx.session.hook("context", async (event) => {
    const { global, project } = await readRules();
    const note = buildCatalogNote(deps.modelService.current(), global, project);
    event.system.push({ type: "text", text: note });
    const subagentTool = event.tools.subagent;
    if (subagentTool !== undefined) {
      subagentTool.description += " Permitted models: " + note;
    }
  });
  registrations.push(contextRegistration);

  // 3. Enforcement: rewrite the built-in `subagent` tool input before validation.
  const parentModel = async (sessionID: string, catalog: Catalog): Promise<ModelRef> => {
    try {
      const session = await ctx.session.get({ sessionID });
      const model = session.model;
      if (model !== undefined) {
        return {
          providerID: String(model.providerID),
          id: String(model.id),
          variant: model.variant,
        };
      }
    } catch {
      // Parent lookup is best effort; the catalog fallback below still applies.
    }
    const free = catalog.models.find((model) => model.isFree);
    const fallback = free ?? catalog.models[0];
    if (fallback !== undefined) {
      return { providerID: fallback.providerID, id: fallback.id, variant: fallback.efforts[0] };
    }
    return { providerID: "opencode", id: "unknown" };
  };

  const beforeRegistration = await ctx.tool.hook("execute.before", async (event) => {
    if (event.tool !== "subagent") return;
    const input = event.input as MutableSubagentInput;
    const { global, project } = await readRules();
    const catalog = deps.modelService.current();
    const parent = await parentModel(event.sessionID, catalog);
    const resolved = resolveSubagentRoute(input, catalog, global, project, parent);

    if (resolved !== undefined) {
      // selectorWithVariant is already the canonical `provider/id#variant`
      // string including the chosen effort; do not append a variant twice.
      input.model = resolved.selectorWithVariant;
    } else {
      delete input.model;
    }
  });
  registrations.push(beforeRegistration);

  // 4. Persistent per-agent defaults; variant carries the effort level.
  const agentRegistration = await ctx.agent.transform((editor) => {
    for (const [agentID, selector] of Object.entries(agentDefaults)) {
      const agent = editor.get(agentID);
      if (agent === undefined) continue;
      try {
        const ref = parseModelSelector(selector);
        agent.model = {
          providerID: ref.providerID,
          id: ref.id,
          variant: ref.variant,
        } as NonNullable<typeof agent.model>;
      } catch {
        // Ignore invalid persisted selectors; routing validates at call time.
      }
    }
  });
  registrations.push(agentRegistration);

  const applyAgentDefaults = async (global: AllowlistRule, project: AllowlistRule): Promise<void> => {
    const merged = { ...global.agentDefaults, ...project.agentDefaults };
    const serialized = JSON.stringify(merged);
    if (serialized === cachedAgentDefaults) return;
    cachedAgentDefaults = serialized;
    agentDefaults = merged;
    await ctx.agent.reload();
  };

  const initial = await readRules();
  await applyAgentDefaults(initial.global, initial.project);

  return {
    async refresh(): Promise<void> {
      const { global, project } = await readRules();
      await applyAgentDefaults(global, project);
    },
    async dispose(): Promise<void> {
      for (const registration of registrations) {
        await registration.dispose();
      }
    },
  };
}
