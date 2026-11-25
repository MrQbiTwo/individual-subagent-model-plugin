import type { Context } from "@opencode/plugin/promise/plugin";
import type { RawModelInfo, RawProviderInfo } from "#universal/domain/types";
import type { CatalogProvider } from "#universal/ports";

/** Invalidation events only: their payloads are empty, so we always re-fetch. */
const CATALOG_EVENT_TYPES = ["model.updated", "provider.updated", "models-dev.refreshed"] as const;

/** Adapt an OpenCode server plugin context to the SDK-free CatalogProvider. */
export function toCatalogProvider(ctx: Context): CatalogProvider {
  return {
    async listModels(): Promise<readonly RawModelInfo[]> {
      const models = (await ctx.model.list()).data;
      return models.map((model) => ({
        id: model.id,
        modelID: model.modelID,
        providerID: model.providerID,
        name: model.name,
        variants: model.variants.map((variant) => ({
          id: variant.id,
          settings: variant.settings as Readonly<Record<string, unknown>> | undefined,
        })),
        cost: model.cost.map((tier) => ({ input: tier.input })),
        enabled: model.enabled,
      }));
    },

    async listProviders(): Promise<readonly RawProviderInfo[]> {
      const providers = (await ctx.provider.list()).data;
      return providers.map((provider) => ({ id: provider.id, name: provider.name }));
    },

    async subscribeInvalidation(handler: () => void): Promise<() => void> {
      const controller = new AbortController();
      const events = await ctx.event.subscribe({
        types: [...CATALOG_EVENT_TYPES],
        signal: controller.signal,
      });

      // Run a detached loop; the event data is intentionally ignored.
      void (async () => {
        try {
          for await (const _event of events) {
            handler();
          }
        } catch (error) {
          if (!controller.signal.aborted) {
            console.error("catalog event subscription failed", error);
          }
        }
      })();

      return () => controller.abort();
    },
  };
}
