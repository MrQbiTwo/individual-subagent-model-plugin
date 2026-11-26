/**
 * Codex-specific catalog fact. Built-in Codex models are not OpenCode free
 * models, so the allowlist fails closed: nothing is free by default.
 */

import type { CatalogConfig } from "#universal/ports";

export const CODEX_FREE_PROVIDERS: readonly string[] = [];

export const CODEX_CATALOG_CONFIG: CatalogConfig = {
  builtInFreeProviders: CODEX_FREE_PROVIDERS,
};
