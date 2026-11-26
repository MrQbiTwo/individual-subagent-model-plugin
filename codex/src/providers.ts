/**
 * Validation and construction of custom `[model_providers.<id>]` tables.
 * Only shapes supported by Codex 0.153.4 are emitted; later-version keys are
 * rejected instead of silently written into a config that the binary rejects.
 */

import type { CodexProviderTable } from "./config.js";

/** Built-in ids from v0.153.4 plus `gcp`, which later versions also reserve. */
export const RESERVED_PROVIDER_IDS = [
  "openai",
  "ollama",
  "lmstudio",
  "amazon-bedrock",
  "amazon-bedrock-runtime",
  "gcp",
] as const;

/** Fields that belong to later Codex releases, not the 0.153.4 target. */
export const FORBIDDEN_PROVIDER_KEYS = [
  "model_catalog_url",
  "capabilities",
  "gateway_oauth",
] as const;

/** Error carrying a stable machine-readable code for callers and the probe. */
export class CodexError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface BuildProviderInput {
  id: string;
  name?: string;
  baseUrl: string;
  envKey?: string;
  wireApi?: string;
  httpHeaders?: Record<string, string>;
  auth?: CodexProviderTable["auth"];
  aws?: Record<string, unknown>;
  extra?: Record<string, unknown>;
}

const PROVIDER_ID = /^[a-z][a-z0-9_-]*$/;
const ENV_KEY_NAME = /^[A-Z][A-Z0-9_]*$/;

function reject(code: string, message: string): never {
  throw new CodexError(code, message);
}

/**
 * Build one custom provider table. `env_key` carries the *name* of an
 * environment variable, never the credential itself.
 */
export function buildProvider(input: BuildProviderInput): { id: string; table: CodexProviderTable } {
  const { id } = input;
  if (!PROVIDER_ID.test(id)) {
    reject("INVALID_PROVIDER_ID", `Invalid provider id: ${JSON.stringify(id)}`);
  }
  if ((RESERVED_PROVIDER_IDS as readonly string[]).includes(id)) {
    reject("RESERVED_PROVIDER_ID", `Provider id is reserved by Codex: ${id}`);
  }
  if (input.wireApi !== undefined && input.wireApi !== "responses") {
    reject("CHAT_WIRE_API", `Only wire_api = "responses" is supported: ${input.wireApi}`);
  }
  if (input.envKey !== undefined && !ENV_KEY_NAME.test(input.envKey)) {
    reject("SECRET_IN_ENV_KEY", "env_key must be an environment variable name, not a secret");
  }
  if (input.auth !== undefined && input.envKey !== undefined) {
    reject("AUTH_ENV_KEY_CONFLICT", "auth and env_key cannot be combined");
  }
  if (input.aws !== undefined) {
    reject("AWS_ON_CUSTOM_PROVIDER", "aws settings are only valid on Bedrock built-ins");
  }
  const unsupported = (FORBIDDEN_PROVIDER_KEYS as readonly string[]).find(
    (key) => input.extra !== undefined && Object.hasOwn(input.extra, key),
  );
  if (unsupported !== undefined) {
    reject("UNSUPPORTED_KEY", `Unsupported provider key for Codex 0.153.4: ${unsupported}`);
  }

  const table: CodexProviderTable = {
    name: input.name,
    base_url: input.baseUrl,
    ...(input.envKey !== undefined ? { env_key: input.envKey } : {}),
    wire_api: "responses",
    ...(input.httpHeaders !== undefined ? { http_headers: input.httpHeaders } : {}),
    ...(input.auth !== undefined ? { auth: input.auth } : {}),
    ...(input.extra ?? {}),
  };
  // Remove keys that were explicitly undefined (e.g. an omitted `name`).
  for (const [key, value] of Object.entries(table)) {
    if (value === undefined) delete table[key];
  }
  return { id, table };
}
