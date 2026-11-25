import type { CatalogConfig } from "../ports.js";
import type {
  Catalog,
  ModelDescriptor,
  ProviderDescriptor,
  RawModelInfo,
  RawProviderInfo,
  VariantDescriptor,
} from "./types.js";

/**
 * Fail closed: a model is free only when its provider is listed by the injected
 * catalog config, it has at least one cost tier, and every tier has a zero
 * input price. Empty or missing cost data never counts as free.
 */
export function isBuiltInFree(model: RawModelInfo, config: CatalogConfig): boolean {
  return (
    config.builtInFreeProviders.includes(model.providerID) &&
    model.cost.length > 0 &&
    model.cost.every((tier) => tier.input === 0)
  );
}

/** Normalize a raw model into the descriptor shared across the plugin. */
export function toModelDescriptor(
  model: RawModelInfo,
  providerName: string,
  config: CatalogConfig,
): ModelDescriptor {
  const variants: VariantDescriptor[] = model.variants.map((variant) => ({
    id: variant.id,
    settings: variant.settings ?? {},
  }));

  return {
    id: model.id,
    modelID: model.modelID,
    providerID: model.providerID,
    providerName,
    name: model.name,
    variants,
    efforts: model.variants.map((variant) => variant.id),
    enabled: model.enabled,
    isFree: isBuiltInFree(model, config),
    selector: `${model.providerID}/${model.id}`,
  };
}

/** Build an immutable snapshot, grouping models by provider id in sorted order. */
export function buildCatalog(
  models: readonly RawModelInfo[],
  providers: readonly RawProviderInfo[],
  config: CatalogConfig,
): Catalog {
  const providerNames = new Map(providers.map((provider) => [provider.id, provider.name]));
  const grouped = new Map<string, ModelDescriptor[]>();

  for (const model of models) {
    const bucket = grouped.get(model.providerID) ?? [];
    bucket.push(
      toModelDescriptor(
        model,
        providerNames.get(model.providerID) ?? model.providerID,
        config,
      ),
    );
    grouped.set(model.providerID, bucket);
  }

  const sortedProviderIds = [...grouped.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const providerDescriptors: ProviderDescriptor[] = sortedProviderIds.map((id) => ({
    id,
    name: providerNames.get(id) ?? id,
    models: grouped.get(id) ?? [],
  }));

  return {
    generatedAt: Date.now(),
    providers: providerDescriptors,
    models: providerDescriptors.flatMap((provider) => provider.models),
  };
}

/** Look up a model by its `providerID/id` selector. */
export function findBySelector(catalog: Catalog, selector: string): ModelDescriptor | undefined {
  return catalog.models.find((model) => model.selector === selector);
}
