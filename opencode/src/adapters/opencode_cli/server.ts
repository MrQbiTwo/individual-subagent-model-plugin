/**
 * Server plugin composition root.
 *
 * Builds the SDK-free services from the OpenCode context, wires the core event
 * emitter to transform reloads, and returns a cleanup that disposes everything
 * in reverse construction order.
 */

import { Plugin } from "@opencode/plugin";
import type { Context } from "@opencode/plugin/promise/plugin";

import { projectKey } from "#universal/domain/config";
import type { CoreEvent } from "#universal/domain/types";
import { createModelService } from "#universal/services/catalog_service";
import { FileConfigStore, resolveConfigRoot } from "./config_store.js";
import { toCatalogProvider } from "./host.js";
import { OPENCODE_CATALOG_CONFIG } from "./opencode_free_providers.js";
import { registerRpc, type RpcHandle } from "./rpc_server.js";
import { registerRouting, type RoutingHandle, type ServerDeps } from "./routing.js";

export async function setupServerPlugin(ctx: Context): Promise<() => Promise<void>> {
  const modelService = await createModelService(
    toCatalogProvider(ctx),
    undefined,
    OPENCODE_CATALOG_CONFIG,
  );
  const configStore = new FileConfigStore(resolveConfigRoot());
  const key = projectKey(ctx.location.workspaceID ?? "default");

  let routing: RoutingHandle | undefined;
  let rpc: RpcHandle | undefined;

  const emit = async (event: CoreEvent): Promise<void> => {
    if (event.type === "policy.updated") {
      // Transforms replay from the config store, so updating captured state and
      // reloading agents is sufficient; models do not depend on policy.
      await routing?.refresh();
    } else if (event.type === "catalog.updated") {
      await ctx.model.reload();
    }
  };

  const deps: ServerDeps = { modelService, configStore, projectKey: key, emit };

  // The plugin exposes no commands or GUI; users configure it through JSON files.

  routing = await registerRouting(ctx, deps);
  rpc = await registerRpc(ctx, deps);

  return async () => {
    await rpc?.dispose();
    await routing?.dispose();
    await modelService.dispose();
  };
}

const setup = async (ctx: Context): Promise<() => Promise<void>> => setupServerPlugin(ctx);

/** Host identity is frozen: the root `index.ts` shim re-exports this default. */
export default Plugin.define({ id: "individual-subagent-model-plugin", setup });
