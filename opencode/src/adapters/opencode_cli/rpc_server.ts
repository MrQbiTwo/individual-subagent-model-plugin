/**
 * Server side of the typed RPC contract.
 *
 * Clients read and write allowlist state through these methods, so the
 * file-backed config store has a single writer.
 */

import type { Context as PluginContext } from "@opencode/plugin/promise/plugin";

import type {
  GetCatalogOutput,
  GetPolicyInput,
  GetPolicyOutput,
  SetPolicyInput,
  SetPolicyOutput,
} from "#universal/domain/types";
import { SubagentModels } from "./rpc.js";
import type { ServerDeps } from "./routing.js";

export interface RpcHandle {
  dispose(): Promise<void>;
}

/** Register the three methods and forward catalog updates to RPC subscribers. */
export async function registerRpc(ctx: PluginContext, deps: ServerDeps): Promise<RpcHandle> {
  const registration = await ctx.rpc.register(SubagentModels, {
    get_catalog: async () => {
      const output: GetCatalogOutput = { catalog: deps.modelService.current() };
      return output;
    },
    get_policy: async (input) => {
      const { scope } = input as GetPolicyInput;
      const rule = await deps.configStore.read(scope, scope === "project" ? deps.projectKey : undefined);
      const output: GetPolicyOutput = { rule };
      return output;
    },
    set_policy: async (input) => {
      const { scope, rule } = input as SetPolicyInput;
      await deps.configStore.write(scope, rule, scope === "project" ? deps.projectKey : undefined);
      // Notify the core first so transforms replay, then push the RPC event.
      await deps.emit({ type: "policy.updated", scope });
      await registration.events.emit("policy_updated", { scope });
      const output: SetPolicyOutput = { rule };
      return output;
    },
  });

  const unsubscribe = deps.modelService.subscribe(() => {
    void registration.events.emit("catalog_updated", {}).catch((error: unknown) => {
      console.error("failed to emit catalog_updated RPC event", error);
    });
  });

  return {
    async dispose(): Promise<void> {
      unsubscribe();
      await registration.dispose();
    },
  };
}
