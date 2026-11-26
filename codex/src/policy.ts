/**
 * Codex route resolution. Pure selection/validation rules are reused from the
 * universal core; this module only adds Codex-specific precedence sources and
 * typed rejection reasons.
 */

import { findBySelector } from "#universal/domain/catalog";
import { decideWithScopes, emptyRule } from "#universal/domain/policy";
import { resolveSubagentRoute } from "#universal/domain/routing";
import { formatModelRef, parseModelSelector } from "#universal/domain/selector";
import type { AllowlistRule, Catalog, ModelRef } from "#universal/domain/types";
import { CoreError } from "#universal/domain/types";

import { RESERVED_PROVIDER_IDS } from "./providers.js";

export type RouteRejectionReason =
  | "UNKNOWN_PROVIDER"
  | "RESERVED_PROVIDER_ID"
  | "NOT_IN_CATALOG"
  | "NOT_ALLOWED"
  | "CHAT_WIRE_API"
  | "PROJECT_CONFIG_REJECTED"
  | "PROVIDER_OVERRIDE_UNSUPPORTED";

export interface Route {
  providerID: string;
  model: string;
  reasoningEffort?: string;
}

export type RouteResult =
  | { ok: true; route: Route }
  | { ok: false; reason: RouteRejectionReason };

export interface ResolveRouteInput {
  agent?: string;
  requestedModel?: string;
  requestedProvider?: string;
  allowlist: AllowlistRule;
  catalog: Catalog;
  parentModel?: ModelRef;
  agentFileModel?: string;
  agentsDefaultModel?: string;
  effort?: string;
  /** Offline facts used only to classify rejections; never persisted. */
  providerWireApis?: Record<string, string>;
  providerSources?: Record<string, "user" | "project">;
  [key: string]: unknown;
}

const reject = (reason: RouteRejectionReason): RouteResult => ({ ok: false, reason });

/** Try the universal parser; malformed selectors are simply skipped. */
function tryParse(value: string): ModelRef | undefined {
  try {
    return parseModelSelector(value);
  } catch (error) {
    if (error instanceof CoreError) return undefined;
    throw error;
  }
}

function findProviderForModel(catalog: Catalog, model: string): string | undefined {
  const matches = catalog.models.filter(
    (candidate) => candidate.id === model || candidate.modelID === model,
  );
  return matches[0]?.providerID;
}

/**
 * Resolve a subagent model for Codex.
 *
 * Precedence: explicit requested model → custom agent file → persisted agent
 * default → `[agents]` default → parent model. Per-subagent provider switching
 * is unsupported: a requested provider must match the inherited/catalog one.
 */
export function resolveRoute(input: ResolveRouteInput): RouteResult {
  const { catalog, allowlist } = input;

  const requestedProvider = input.requestedProvider;
  if (requestedProvider !== undefined) {
    if ((RESERVED_PROVIDER_IDS as readonly string[]).includes(requestedProvider)) {
      return reject("RESERVED_PROVIDER_ID");
    }
    if (!catalog.providers.some((provider) => provider.id === requestedProvider)) {
      return reject("UNKNOWN_PROVIDER");
    }
  }

  const candidates: Array<{ value: string; effort?: string }> = [];
  const push = (value: string | undefined): void => {
    if (typeof value === "string" && value.trim().length > 0) {
      candidates.push({ value: value.trim() });
    }
  };
  push(input.requestedModel);
  push(input.agentFileModel);
  if (input.agent !== undefined) {
    push(allowlist.agentDefaults[input.agent]);
  }
  push(input.agentsDefaultModel);
  if (input.parentModel !== undefined) push(formatModelRef(input.parentModel));

  let ref: ModelRef | undefined;
  for (const candidate of candidates) {
    const parsed = tryParse(candidate.value) ?? {
      providerID: requestedProvider ?? input.parentModel?.providerID ?? "",
      id: candidate.value,
    };
    const providerID =
      parsed.providerID.length > 0
        ? parsed.providerID
        : (requestedProvider ??
          input.parentModel?.providerID ??
          findProviderForModel(catalog, parsed.id) ??
          "");
    if (providerID.length === 0) continue;
    ref = {
      providerID,
      id: parsed.id,
      ...(input.effort !== undefined ? { variant: input.effort } : parsed.variant !== undefined ? { variant: parsed.variant } : {}),
    };
    break;
  }
  if (ref === undefined) return reject("NOT_IN_CATALOG");

  if (requestedProvider !== undefined && requestedProvider !== ref.providerID) {
    return reject("PROVIDER_OVERRIDE_UNSUPPORTED");
  }
  if (input.providerSources?.[ref.providerID] === "project") {
    return reject("PROJECT_CONFIG_REJECTED");
  }
  if (input.providerWireApis?.[ref.providerID] === "chat") {
    return reject("CHAT_WIRE_API");
  }

  const descriptor = findBySelector(catalog, `${ref.providerID}/${ref.id}`);
  if (descriptor === undefined) return reject("NOT_IN_CATALOG");
  if (ref.variant !== undefined && !descriptor.efforts.includes(ref.variant)) {
    return reject("NOT_IN_CATALOG");
  }
  if (!decideWithScopes(descriptor, allowlist, emptyRule()).allowed) {
    return reject("NOT_ALLOWED");
  }

  // Let the universal resolver make the final, validated choice. Passing an
  // empty agent id prevents its own agent-default lookup from changing it.
  const selector = formatModelRef(ref);
  const parent: ModelRef = input.parentModel ?? { providerID: "", id: "" };
  const resolved = resolveSubagentRoute(
    { agent: "", description: "", prompt: "", model: selector },
    catalog,
    allowlist,
    emptyRule(),
    parent,
  );
  if (resolved === undefined) return reject("NOT_ALLOWED");

  return {
    ok: true,
    route: {
      providerID: resolved.ref.providerID,
      model: resolved.ref.id,
      ...(resolved.ref.variant !== undefined ? { reasoningEffort: resolved.ref.variant } : {}),
    },
  };
}
