import { buildCatalog } from "../domain/catalog.js";
import type { Catalog } from "../domain/types.js";
import type { CatalogConfig, CatalogProvider, CoreEventSink } from "../ports.js";

/** Owns the live, event-refreshed catalog snapshot. */
export interface ModelService {
  current(): Catalog;
  refresh(): Promise<Catalog>;
  subscribe(listener: (catalog: Catalog) => void): () => void;
  dispose(): Promise<void>;
}

const NO_FREE_PROVIDERS: CatalogConfig = { builtInFreeProviders: [] };

/**
 * Fetch the initial catalog immediately, then rebuild it on every host
 * invalidation event. Concurrent refreshes are coalesced: a request arriving
 * while one is in flight schedules exactly one follow-up run. Listeners are
 * notified only when a new catalog is committed.
 *
 * `sink` is accepted for adapters that want core events; emitting is opt-in so
 * adding the port never changes existing refresh fan-out behaviour.
 */
export async function createModelService(
  provider: CatalogProvider,
  sink?: CoreEventSink,
  config: CatalogConfig = NO_FREE_PROVIDERS,
): Promise<ModelService> {
  const listeners = new Set<(catalog: Catalog) => void>();
  let snapshot: Catalog | undefined;
  let inFlight: Promise<Catalog> | undefined;
  let queued = false;
  // Reserved for adapters that subscribe; kept local to avoid a hidden host call.
  void sink;

  const runRefresh = async (): Promise<Catalog> => {
    const [models, providers] = await Promise.all([
      provider.listModels(),
      provider.listProviders(),
    ]);
    const catalog = buildCatalog(models, providers, config);
    snapshot = catalog;
    for (const listener of listeners) {
      listener(catalog);
    }
    return catalog;
  };

  const refresh = (): Promise<Catalog> => {
    if (inFlight) {
      queued = true;
      return inFlight;
    }
    const task = runRefresh().finally(() => {
      inFlight = undefined;
      if (queued) {
        queued = false;
        void refresh().catch((error) => console.error("catalog refresh failed", error));
      }
    });
    inFlight = task;
    return task;
  };

  // `await` guarantees `current()` is always backed by a committed snapshot.
  await refresh();

  // Subscribe after the first commit so listeners only observe real updates.
  const unsubscribe = await provider.subscribeInvalidation(() => {
    void refresh().catch((error) => console.error("catalog refresh failed", error));
  });

  return {
    current(): Catalog {
      if (!snapshot) {
        throw new Error("ModelService has no catalog snapshot");
      }
      return snapshot;
    },
    refresh,
    subscribe(listener: (catalog: Catalog) => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async dispose(): Promise<void> {
      unsubscribe();
      listeners.clear();
    },
  };
}
