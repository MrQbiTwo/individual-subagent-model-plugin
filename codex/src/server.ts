/** Composition root: build the SDK-free Codex adapter from the universal core. */

import { homedir } from "node:os";
import * as path from "node:path";

import { projectKey as sanitizeProjectKey } from "#universal/domain/config";
import type {
  AllowlistRule,
  Catalog,
  CoreEvent,
  ModelRef,
  ScopeName,
} from "#universal/domain/types";
import { createModelService } from "#universal/services/catalog_service";

import type { BuildExecArgsInput } from "./argv.js";
import { buildExecArgs } from "./argv.js";
import { parseBundledCatalog } from "./catalog.js";
import { CODEX_CATALOG_CONFIG } from "./codex_free_providers.js";
import type { CodexConfig } from "./config.js";
import { readConfig } from "./config.js";
import { CodexConfigStore, CodexCatalogProvider } from "./ports.js";
import type { ResolveRouteInput, RouteResult } from "./policy.js";
import { resolveRoute } from "./policy.js";

export interface CodexAdapterOptions {
  codexHome?: string;
  projectKey?: string;
  config?: CodexConfig;
  bundledCatalogJson?: string;
  catalogJson?: string;
}

export interface CodexAdapter {
  getCatalog(): Promise<Catalog>;
  getPolicy(scope: ScopeName, projectKey?: string): Promise<AllowlistRule>;
  setPolicy(scope: ScopeName, rule: AllowlistRule, projectKey?: string): Promise<void>;
  resolveRoute(input: ResolveRouteInput, parentModel?: ModelRef): RouteResult;
  buildExecArgs(input: BuildExecArgsInput): string[];
  subscribe(listener: (event: CoreEvent) => void): () => void;
  dispose(): Promise<void>;
}

/** Build a complete, disposable adapter. No commands and no UI are registered. */
export async function createCodexAdapter(options: CodexAdapterOptions = {}): Promise<CodexAdapter> {
  const home = options.codexHome ?? process.env.CODEX_HOME ?? path.join(homedir(), ".codex");
  const config =
    options.config ??
    (options.codexHome !== undefined
      ? await readConfig(path.join(home, "config.toml"))
      : {});
  const key = sanitizeProjectKey(options.projectKey ?? "default");

  const modelService = await createModelService(
    new CodexCatalogProvider({
      config,
      bundledCatalogJson: options.bundledCatalogJson,
      catalogJson: options.catalogJson,
    }),
    undefined,
    CODEX_CATALOG_CONFIG,
  );
  const configStore = new CodexConfigStore(path.join(home, "individual-subagent-model-plugin"));

  const listeners = new Set<(event: CoreEvent) => void>();
  const emit = (event: CoreEvent): void => {
    for (const listener of listeners) listener(event);
  };
  const unsubscribeCatalog = modelService.subscribe(() => emit({ type: "catalog.updated" }));

  return {
    async getCatalog(): Promise<Catalog> {
      return modelService.current();
    },
    async getPolicy(scope: ScopeName, projectKey?: string): Promise<AllowlistRule> {
      return configStore.read(scope, scope === "project" ? (projectKey ?? key) : undefined);
    },
    async setPolicy(scope: ScopeName, rule: AllowlistRule, projectKey?: string): Promise<void> {
      await configStore.write(scope, rule, scope === "project" ? (projectKey ?? key) : undefined);
      emit({ type: "policy.updated", scope });
    },
    resolveRoute(input: ResolveRouteInput, parentModel?: ModelRef): RouteResult {
      return resolveRoute({ ...input, parentModel: input.parentModel ?? parentModel });
    },
    buildExecArgs(input: BuildExecArgsInput): string[] {
      return buildExecArgs(input);
    },
    subscribe(listener: (event: CoreEvent) => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async dispose(): Promise<void> {
      unsubscribeCatalog();
      listeners.clear();
      await modelService.dispose();
    },
  };
}

// Re-exported for callers that want to pre-parse a bundled catalog fixture.
export { parseBundledCatalog };
