/**
 * Host-neutral ports. Every adapter implements these with its own SDK calls;
 * nothing here imports an SDK, a UI framework, or a Node built-in.
 */

import type {
  AllowlistRule,
  Catalog,
  CoreEvent,
  ModelDescriptor,
  ModelRef,
  PluginConfig,
  PolicyDecision,
  RawModelInfo,
  RawProviderInfo,
  ResolvedSubagentModel,
  RuleMutation,
  ScopeName,
  SubagentToolInput,
} from "./domain/types.js";

/** Agent-neutral supply of raw catalog data plus invalidation notifications. */
export interface CatalogProvider {
  listModels(): Promise<readonly RawModelInfo[]>;
  listProviders(): Promise<readonly RawProviderInfo[]>;
  subscribeInvalidation(handler: () => void): Promise<() => void>;
}

/** Agent-neutral allowlist persistence. */
export interface ConfigStore {
  read(scope: ScopeName, projectKey?: string): Promise<AllowlistRule>;
  write(scope: ScopeName, rule: AllowlistRule, projectKey?: string): Promise<void>;
  readAll(): Promise<PluginConfig>;
}

/** Pure decision and mutation engine, backed by `domain/policy.ts`. */
export interface PolicyEngine {
  decide(model: ModelDescriptor, rule: AllowlistRule): PolicyDecision;
  decideWithScopes(
    model: ModelDescriptor,
    global: AllowlistRule,
    project: AllowlistRule,
  ): PolicyDecision;
  effectiveRule(global: AllowlistRule, project: AllowlistRule): AllowlistRule;
  isModelAllowed(model: ModelDescriptor, rule: AllowlistRule): boolean;
  applyRuleMutation(rule: AllowlistRule, mutation: RuleMutation): AllowlistRule;
}

/** Pure route selection plus context note, backed by `domain/routing.ts`. */
export interface RoutingResolver {
  resolve(
    input: SubagentToolInput,
    catalog: Catalog,
    global: AllowlistRule,
    project: AllowlistRule,
    parentModel: ModelRef,
  ): ResolvedSubagentModel | undefined;
  buildNote(catalog: Catalog, global: AllowlistRule, project: AllowlistRule): string;
}

/** Agent-specific facts injected into otherwise-universal catalog building. */
export interface CatalogConfig {
  readonly builtInFreeProviders: readonly string[];
}

/** Sink used by adapters to turn core events into host reloads/invalidations. */
export interface CoreEventSink {
  emit(event: CoreEvent): Promise<void>;
}
