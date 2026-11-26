/**
 * Model discovery for Codex. The bundled catalog is read only for its
 * structural fields (`slug`, `display_name`, `supported_reasoning_levels`,
 * `default_reasoning_level`); all other content, especially free-form message
 * templates, is inert data and is neither interpreted nor copied.
 */

import type { CodexConfig } from "./config.js";
import type { RawModelInfo, RawProviderInfo, RawVariant } from "#universal/domain/types";

/** Normalize one reasoning-level entry to an effort id string. */
function effortId(entry: unknown): string | undefined {
  if (typeof entry === "string") {
    const trimmed = entry.trim();
    return trimmed.length > 0 ? trimmed : undefined;
  }
  if (typeof entry === "object" && entry !== null) {
    const record = entry as Record<string, unknown>;
    for (const key of ["effort", "id", "name"] as const) {
      const value = record[key];
      if (typeof value === "string" && value.trim().length > 0) return value.trim();
    }
  }
  return undefined;
}

/**
 * Parse `codex debug models --bundled` JSON (or a `model_catalog_json` file).
 * Cost tiers stay empty so the core's free-model check fails closed.
 */
export function parseBundledCatalog(json: string, providerID = "openai"): RawModelInfo[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return [];
  }
  const source = Array.isArray(parsed)
    ? parsed
    : typeof parsed === "object" && parsed !== null && Array.isArray((parsed as { models?: unknown }).models)
      ? ((parsed as { models: unknown[] }).models)
      : [];

  const models: RawModelInfo[] = [];
  for (const entry of source) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as Record<string, unknown>;
    const slug = typeof record.slug === "string" ? record.slug : undefined;
    if (slug === undefined || slug.length === 0) continue;
    const levels = Array.isArray(record.supported_reasoning_levels)
      ? record.supported_reasoning_levels
      : [];
    const variants: RawVariant[] = [];
    for (const level of levels) {
      const id = effortId(level);
      if (id !== undefined && !variants.some((variant) => variant.id === id)) {
        variants.push({ id });
      }
    }
    models.push({
      id: slug,
      modelID: slug,
      providerID,
      name: typeof record.display_name === "string" ? record.display_name : slug,
      variants,
      cost: [],
      enabled: true,
    });
  }
  return models;
}

export interface DiscoverModelsInput {
  config: CodexConfig;
  bundledCatalogJson?: string;
  catalogJson?: string;
}

/**
 * Discover from configuration and supplied catalog JSON only. A custom
 * provider never gets fabricated models: an absent catalog yields no models.
 */
export function discoverModels(input: DiscoverModelsInput): {
  models: RawModelInfo[];
  providers: RawProviderInfo[];
} {
  const configured = input.config.model_providers ?? {};
  const providers: RawProviderInfo[] = [{ id: "openai", name: "OpenAI" }];
  for (const id of Object.keys(configured).sort()) {
    if (providers.some((provider) => provider.id === id)) continue;
    const table = configured[id] ?? {};
    providers.push({ id, name: typeof table.name === "string" ? table.name : id });
  }

  const catalogText = input.catalogJson ?? input.bundledCatalogJson;
  const models = catalogText === undefined ? [] : parseBundledCatalog(catalogText);
  return { models, providers };
}
