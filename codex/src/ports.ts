/** The two mandatory universal ports, implemented with node:fs only. */

import { mkdir, readFile, readdir, rename, unlink, writeFile } from "node:fs/promises";
import type { Dirent } from "node:fs";
import * as path from "node:path";

import {
  CONFIG_VERSION,
  isAllowlistRule,
  parsePluginConfig,
  projectKey as sanitizeProjectKey,
  serializePluginConfig,
} from "#universal/domain/config";
import { emptyRule } from "#universal/domain/policy";
import { CoreError, type AllowlistRule, type PluginConfig, type ScopeName } from "#universal/domain/types";
import type { CatalogProvider, ConfigStore } from "#universal/ports";

import { discoverModels } from "./catalog.js";
import type { CodexConfig } from "./config.js";

export interface CodexCatalogProviderInput {
  config: CodexConfig;
  bundledCatalogJson?: string;
  catalogJson?: string;
}

/** Offline catalog source: configuration plus an optional supplied catalog. */
export class CodexCatalogProvider implements CatalogProvider {
  private readonly input: CodexCatalogProviderInput;

  constructor(input: CodexCatalogProviderInput | CodexConfig) {
    this.input =
      typeof input === "object" && input !== null && "config" in input && typeof (input as CodexCatalogProviderInput).config === "object"
        ? (input as CodexCatalogProviderInput)
        : { config: input as CodexConfig };
  }

  async listModels() {
    return discoverModels(this.input).models;
  }

  async listProviders() {
    return discoverModels(this.input).providers;
  }

  /** Offline there is no live host event source: return a no-op unsubscribe. */
  async subscribeInvalidation(handler: () => void): Promise<() => void> {
    void handler;
    return () => {};
  }
}

/** File-backed allowlist store under `<root>/global.json` and `projects/`. */
export class CodexConfigStore implements ConfigStore {
  constructor(private readonly root: string) {}

  private filePath(scope: ScopeName, key?: string): string {
    if (scope === "global") return path.join(this.root, "global.json");
    return path.join(this.root, "projects", sanitizeProjectKey(key ?? "") + ".json");
  }

  private async parseRuleFile(filePath: string): Promise<AllowlistRule> {
    let text: string;
    try {
      text = await readFile(filePath, "utf8");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return emptyRule();
      throw error;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new CoreError("invalid-config", "config file is not valid JSON: " + filePath);
    }
    if (!isAllowlistRule(parsed)) {
      throw new CoreError("invalid-config", "invalid allowlist rule in config file: " + filePath);
    }
    return parsed;
  }

  async read(scope: ScopeName, key?: string): Promise<AllowlistRule> {
    return this.parseRuleFile(this.filePath(scope, key));
  }

  async write(scope: ScopeName, rule: AllowlistRule, key?: string): Promise<void> {
    const filePath = this.filePath(scope, key);
    await mkdir(path.dirname(filePath), { recursive: true });
    const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
    try {
      await writeFile(tempPath, JSON.stringify(rule, null, 2) + "\n", "utf8");
      try {
        await rename(tempPath, filePath);
      } catch {
        await unlink(filePath).catch(() => undefined);
        await rename(tempPath, filePath);
      }
    } catch (error) {
      await unlink(tempPath).catch(() => undefined);
      throw error;
    }
  }

  /** Read both scopes into one validated, coherent PluginConfig. */
  async readAll(): Promise<PluginConfig> {
    const global = await this.parseRuleFile(path.join(this.root, "global.json"));
    const projectsDir = path.join(this.root, "projects");
    let entries: Dirent[] = [];
    try {
      entries = await readdir(projectsDir, { withFileTypes: true });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    const projects: Record<string, AllowlistRule> = {};
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
      const rule = await this.parseRuleFile(path.join(projectsDir, entry.name));
      projects[entry.name.slice(0, -".json".length)] = rule;
    }
    const built: PluginConfig = { version: CONFIG_VERSION, global, projects };
    return parsePluginConfig(serializePluginConfig(built));
  }
}
