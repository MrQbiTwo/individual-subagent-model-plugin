import { mkdir, readFile, readdir, rename, unlink, writeFile } from "node:fs/promises";
import type { Dirent } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { CONFIG_VERSION, isAllowlistRule, projectKey } from "#universal/domain/config";
import { emptyRule } from "#universal/domain/policy";
import { CoreError, type AllowlistRule, type PluginConfig, type ScopeName } from "#universal/domain/types";
import type { ConfigStore } from "#universal/ports";

/** Backwards-compatible alias for the universal port. */
export type ConfigStorePort = ConfigStore;

/** Platform-neutral config root: APPDATA on Windows, XDG_CONFIG_HOME elsewhere. */
export function resolveConfigRoot(env: NodeJS.ProcessEnv = process.env): string {
  const base =
    process.platform === "win32"
      ? (env.APPDATA ?? path.join(os.homedir(), "AppData", "Roaming"))
      : (env.XDG_CONFIG_HOME ?? path.join(os.homedir(), ".config"));
  return path.join(base, "individual-subagent-model-plugin");
}

/** File-backed allowlist store; global.json plus projects/<key>.json. */
export class FileConfigStore implements ConfigStore {
  private readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  private filePath(scope: ScopeName, key?: string): string {
    if (scope === "global") return path.join(this.root, "global.json");
    // Sanitize the key so it can never escape the projects directory.
    return path.join(this.root, "projects", projectKey(key ?? "") + ".json");
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
        // Windows refuses to rename over an existing file; remove it and retry.
        await unlink(filePath).catch(() => undefined);
        await rename(tempPath, filePath);
      }
    } catch (error) {
      await unlink(tempPath).catch(() => undefined);
      throw error;
    }
  }

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
    return { version: CONFIG_VERSION, global, projects };
  }
}
