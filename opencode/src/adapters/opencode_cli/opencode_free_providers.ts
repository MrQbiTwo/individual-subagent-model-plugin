/**
 * OpenCode-specific catalog fact, injected into the universal catalog builder.
 *
 * This is the only place that knows which built-in providers ship free models.
 * A different agent adapter supplies its own list without touching the core.
 */

import type { CatalogConfig } from "#universal/ports";

export const OPENCODE_FREE_PROVIDERS = ["opencode", "opencode-go"] as const;

export const OPENCODE_CATALOG_CONFIG: CatalogConfig = {
  builtInFreeProviders: OPENCODE_FREE_PROVIDERS,
};
