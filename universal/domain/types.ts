/**
 * Runtime-neutral shared type contract.
 *
 * This module has zero `@opencode/*` imports so it can be shared by the core
 * logic and any host adapter. All fields are readonly: transforms build new
 * values instead of mutating shared state.
 */

export type ScopeName = "project" | "global";

/** Raw variant shape as returned by `Model.Info.variants[]` (the effort levels). */
export interface RawVariant {
  readonly id: string;
  readonly settings?: Readonly<Record<string, unknown>>;
}

/** One cost tier from `Model.Info.cost[]`; only the input price is needed. */
export interface RawCost {
  readonly input: number;
}

/** Minimal `Model.Info` projection consumed by the core. */
export interface RawModelInfo {
  readonly id: string;
  readonly modelID: string;
  readonly providerID: string;
  readonly name: string;
  readonly variants: readonly RawVariant[];
  readonly cost: readonly RawCost[];
  readonly enabled: boolean;
}

/** Minimal `Provider.Info` projection consumed by the core. */
export interface RawProviderInfo {
  readonly id: string;
  readonly name: string;
}

/** Normalized variant: settings are always present (empty object when absent). */
export interface VariantDescriptor {
  readonly id: string;
  readonly settings: Readonly<Record<string, unknown>>;
}

/** Normalized model exposed to policy, routing and the discovery tool. */
export interface ModelDescriptor {
  readonly id: string;
  readonly modelID: string;
  readonly providerID: string;
  readonly providerName: string;
  readonly name: string;
  readonly variants: readonly VariantDescriptor[];
  readonly efforts: readonly string[];
  readonly enabled: boolean;
  readonly isFree: boolean;
  /** `${providerID}/${id}` — uses the catalog id, never `modelID`. */
  readonly selector: string;
}

export interface ProviderDescriptor {
  readonly id: string;
  readonly name: string;
  readonly models: readonly ModelDescriptor[];
}

/** Immutable snapshot rebuilt on every model/provider invalidation event. */
export interface Catalog {
  readonly generatedAt: number;
  readonly providers: readonly ProviderDescriptor[];
  readonly models: readonly ModelDescriptor[];
}

/** Explicit allowlist state for one scope. Free models are computed, not stored. */
export interface AllowlistRule {
  readonly models: readonly string[];
  readonly providers: readonly string[];
  readonly agentDefaults: Readonly<Record<string, string>>;
  /** Optional explicit model denies (`providerID/modelID`); deny wins over allow. */
  readonly deniedModels?: readonly string[];
  /** Optional explicit provider denies (`providerID`); deny wins over allow. */
  readonly deniedProviders?: readonly string[];
}

export interface ScopeConfig {
  readonly version: 1;
  readonly rule: AllowlistRule;
}

export interface PluginConfig {
  readonly version: 1;
  readonly global: AllowlistRule;
  readonly projects: Readonly<Record<string, AllowlistRule>>;
}

/** Parsed `providerID/id#variant` selector. `id` may contain further `/`. */
export type ModelRef = {
  readonly providerID: string;
  readonly id: string;
  readonly variant?: string;
};

export type DecisionReason =
  | "free-default"
  | "global-model"
  | "global-provider"
  | "project-model"
  | "project-provider"
  | "not-allowlisted"
  | "explicitly-denied"
  | "model-unavailable"
  | "invalid-model-ref"
  | "invalid-variant";

export interface PolicyDecision {
  readonly allowed: boolean;
  readonly reason: DecisionReason;
  readonly selector?: string;
}

export type ResolutionSource = "explicit" | "agent-default" | "parent" | "free-default";

export interface ResolvedSubagentModel {
  readonly ref: ModelRef;
  readonly descriptor: ModelDescriptor;
  readonly selectorWithVariant: string;
  readonly source: ResolutionSource;
}

/** Input of the built-in `subagent` tool that routing may rewrite. */
export interface SubagentToolInput {
  readonly agent: string;
  readonly description: string;
  readonly prompt: string;
  readonly model?: string;
  readonly sessionID?: string;
}

export interface GetCatalogInput {}

export interface GetCatalogOutput {
  readonly catalog: Catalog;
}

export interface GetPolicyInput {
  readonly scope: ScopeName;
}

export interface GetPolicyOutput {
  readonly rule: AllowlistRule;
}

export interface SetPolicyInput {
  readonly scope: ScopeName;
  readonly rule: AllowlistRule;
}

export interface SetPolicyOutput {
  readonly rule: AllowlistRule;
}

export type CoreEvent =
  | { readonly type: "catalog.updated" }
  | { readonly type: "policy.updated"; readonly scope: ScopeName };

export interface ListPermittedModelsInput {
  readonly providerID?: string;
}

export interface ListPermittedModelsOutput {
  readonly models: readonly ModelDescriptor[];
  readonly note: string;
}

export type RuleMutation =
  | { readonly kind: "toggle-model"; readonly selector: string }
  | { readonly kind: "set-model"; readonly selector: string; readonly enabled: boolean }
  | { readonly kind: "set-provider"; readonly providerID: string; readonly enabled: boolean }
  | {
      readonly kind: "set-agent-default";
      readonly agentID: string;
      readonly selectorWithVariant?: string;
    };

/** Error carrying a stable machine-readable code for the probe and RPC layers. */
export class CoreError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}
