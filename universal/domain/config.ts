import { CoreError, type AllowlistRule, type PluginConfig } from "./types.js";
import { emptyRule } from "./policy.js";

export const CONFIG_VERSION = 1;

/** Sanitize a workspace identifier for safe use as a file name. */
export function projectKey(workspaceID: string): string {
  return workspaceID.replace(/[^A-Za-z0-9_-]/g, "_");
}

export function defaultPluginConfig(): PluginConfig {
  return { version: CONFIG_VERSION, global: emptyRule(), projects: {} };
}

/** Structural validation of a rule loaded from untrusted JSON. */
export function isAllowlistRule(value: unknown): value is AllowlistRule {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const hasValidBase =
    Array.isArray(candidate.models) &&
    candidate.models.every((item) => typeof item === "string") &&
    Array.isArray(candidate.providers) &&
    candidate.providers.every((item) => typeof item === "string") &&
    typeof candidate.agentDefaults === "object" &&
    candidate.agentDefaults !== null &&
    !Array.isArray(candidate.agentDefaults) &&
    Object.values(candidate.agentDefaults).every((item) => typeof item === "string");
  if (!hasValidBase) return false;

  // Deny fields are optional for backward compatibility with bare legacy rules,
  // but when present they must be arrays of strings.
  for (const key of ["deniedModels", "deniedProviders"] as const) {
    const field = candidate[key];
    if (field === undefined) continue;
    if (!Array.isArray(field) || !field.every((item) => typeof item === "string")) return false;
  }
  return true;
}

function invalidConfig(message: string): never {
  throw new CoreError("invalid-config", message);
}

export function parsePluginConfig(text: string): PluginConfig {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    invalidConfig("config is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    invalidConfig("config must be a JSON object");
  }
  const config = parsed as Record<string, unknown>;
  if (config.version !== CONFIG_VERSION) {
    invalidConfig("unsupported config version");
  }
  if (!isAllowlistRule(config.global)) {
    invalidConfig("invalid global allowlist rule");
  }
  if (typeof config.projects !== "object" || config.projects === null || Array.isArray(config.projects)) {
    invalidConfig("invalid projects section");
  }
  const projects: Record<string, AllowlistRule> = {};
  for (const [key, value] of Object.entries(config.projects)) {
    if (!isAllowlistRule(value)) {
      invalidConfig("invalid allowlist rule for project " + key);
    }
    projects[key] = value;
  }
  return { version: CONFIG_VERSION, global: config.global, projects };
}

export function serializePluginConfig(config: PluginConfig): string {
  return JSON.stringify(config, null, 2) + "\n";
}
