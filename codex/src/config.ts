/**
 * Focused reader/writer for the subset of `config.toml` that Codex 0.153.4
 * understands. Unknown keys are preserved so a user's file is not destroyed by
 * a rewrite; secret-looking values are never emitted.
 */

import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import * as path from "node:path";

export interface CodexProviderTable {
  name?: string;
  base_url?: string;
  env_key?: string;
  wire_api?: string;
  http_headers?: Record<string, string>;
  env_http_headers?: Record<string, string>;
  query_params?: Record<string, string>;
  request_max_retries?: number;
  stream_max_retries?: number;
  stream_idle_timeout_ms?: number;
  websocket_connect_timeout_ms?: number;
  supports_websockets?: boolean;
  supports_standalone_web_search?: boolean;
  requires_openai_auth?: boolean;
  auth?: {
    command?: string;
    args?: string[];
    timeout_ms?: number;
    refresh_interval_ms?: number;
  };
  aws?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface CodexConfig {
  model?: string;
  model_provider?: string;
  model_reasoning_effort?: string;
  openai_base_url?: string;
  model_catalog_json?: string;
  model_providers?: Record<string, CodexProviderTable>;
  agents?: {
    enabled?: boolean;
    max_concurrent_threads_per_session?: number;
    default_subagent_model?: string;
    default_subagent_reasoning_effort?: string;
    [k: string]: unknown;
  };
  features?: Record<string, boolean>;
  [k: string]: unknown;
}

type Table = Record<string, unknown>;

function isPlainObject(value: unknown): value is Table {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Strip a TOML `#` comment while respecting quoted strings. */
function stripComment(text: string): string {
  let quote: '"' | "'" | undefined;
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]!;
    if (quote === '"' && escaped) {
      escaped = false;
      continue;
    }
    if (quote === '"' && char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"' || char === "'") {
      if (quote === char) quote = undefined;
      else if (quote === undefined) quote = char;
      continue;
    }
    if (char === "#" && quote === undefined) return text.slice(0, index);
  }
  return text;
}

/** Find the first `=` outside quotes, arrays and inline tables. */
function findEquals(text: string): number {
  let quote: '"' | "'" | undefined;
  let escaped = false;
  let brackets = 0;
  let braces = 0;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]!;
    if (quote === '"' && escaped) {
      escaped = false;
      continue;
    }
    if (quote === '"' && char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"' || char === "'") {
      if (quote === char) quote = undefined;
      else if (quote === undefined) quote = char;
      continue;
    }
    if (quote !== undefined) continue;
    if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    else if (char === "=" && brackets === 0 && braces === 0) return index;
  }
  return -1;
}

/** Split on a delimiter that is outside quotes, arrays and inline tables. */
function splitTopLevel(text: string, delimiter: string): string[] {
  const parts: string[] = [];
  let quote: '"' | "'" | undefined;
  let escaped = false;
  let brackets = 0;
  let braces = 0;
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]!;
    if (quote === '"' && escaped) {
      escaped = false;
      continue;
    }
    if (quote === '"' && char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"' || char === "'") {
      if (quote === char) quote = undefined;
      else if (quote === undefined) quote = char;
      continue;
    }
    if (quote !== undefined) continue;
    if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    else if (char === delimiter && brackets === 0 && braces === 0) {
      parts.push(text.slice(start, index));
      start = index + 1;
    }
  }
  parts.push(text.slice(start));
  return parts;
}

/** Read one quoted TOML string starting at `start`; returns value and end index. */
function readQuoted(text: string, start: number): { value: string; end: number } {
  const quote = text[start]!;
  let value = "";
  let index = start + 1;
  while (index < text.length) {
    const char = text[index]!;
    if (char === quote) return { value, end: index + 1 };
    if (quote === "'") {
      value += char;
      index += 1;
      continue;
    }
    if (char === "\\") {
      const next = text[index + 1] ?? "";
      const escapes: Record<string, string> = {
        n: "\n",
        r: "\r",
        t: "\t",
        b: "\b",
        f: "\f",
        '"': '"',
        "\\": "\\",
      };
      if (next in escapes) {
        value += escapes[next]!;
        index += 2;
        continue;
      }
      if (next === "u" || next === "U") {
        const width = next === "u" ? 4 : 8;
        const hex = text.slice(index + 2, index + 2 + width);
        if (/^[0-9a-fA-F]+$/.test(hex) && hex.length === width) {
          value += String.fromCodePoint(Number.parseInt(hex, 16));
          index += 2 + width;
          continue;
        }
      }
      value += next;
      index += 2;
      continue;
    }
    value += char;
    index += 1;
  }
  return { value, end: index };
}

function parseInlineTable(body: string): Table {
  const result: Table = {};
  for (const part of splitTopLevel(body, ",")) {
    const equals = findEquals(part);
    if (equals === -1) continue;
    const key = parseKey(part.slice(0, equals).trim());
    if (key.length === 0) continue;
    result[key] = parseValue(part.slice(equals + 1));
  }
  return result;
}

function parseKey(token: string): string {
  if (token.length === 0) return "";
  if (token[0] === '"' || token[0] === "'") return readQuoted(token, 0).value;
  return token;
}

/** Parse one TOML value from the supported subset. */
function parseValue(raw: string): unknown {
  const text = stripComment(raw).trim();
  if (text.length === 0) return "";
  const first = text[0]!;
  if (first === '"' || first === "'") return readQuoted(text, 0).value;
  if (text === "true") return true;
  if (text === "false") return false;
  if (/^[+-]?\d[\d_]*(\.\d[\d_]*)?$/.test(text)) {
    const numeric = Number(text.replace(/_/g, ""));
    if (Number.isFinite(numeric)) return numeric;
  }
  if (first === "{" && text.endsWith("}")) return parseInlineTable(text.slice(1, -1));
  if (first === "[" && text.endsWith("]")) {
    return splitTopLevel(text.slice(1, -1), ",")
      .map((part) => part.trim())
      .filter((part) => part.length > 0)
      .map((part) => parseValue(part));
  }
  return text;
}

function setAtPath(root: Table, segments: readonly string[]): Table {
  let current = root;
  for (const segment of segments) {
    const existing = current[segment];
    if (isPlainObject(existing)) {
      current = existing;
    } else {
      const next: Table = {};
      current[segment] = next;
      current = next;
    }
  }
  return current;
}

/** Parse the supported `config.toml` subset, preserving unknown keys. */
export function parseConfig(text: string): CodexConfig {
  const root: Table = {};
  let current = root;
  for (const line of text.split(/\r?\n/)) {
    const trimmed = stripComment(line).trim();
    if (trimmed.length === 0) continue;
    if (trimmed.startsWith("[")) {
      const end = trimmed.indexOf("]");
      if (end === -1) continue;
      const segments = splitTopLevel(trimmed.slice(1, end), ".")
        .map((part) => parseKey(part.trim()))
        .filter((part) => part.length > 0);
      if (segments.length > 0) current = setAtPath(root, segments);
      continue;
    }
    const equals = findEquals(trimmed);
    if (equals === -1) continue;
    const key = parseKey(trimmed.slice(0, equals).trim());
    if (key.length === 0) continue;
    current[key] = parseValue(trimmed.slice(equals + 1));
  }
  return root as CodexConfig;
}

function quoteToml(text: string): string {
  return `"${text
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t")}"`;
}

function formatKey(key: string): string {
  return /^[A-Za-z0-9_-]+$/.test(key) ? key : quoteToml(key);
}

const SECRET_KEY = /(^|[_.-])(api_?key|bearer_?token|secret|password|token)([_.-]|$)/i;
const SECRET_VALUE = /^(?:sk|rk|ghp|gho|ghu|ghs|ghr)-[A-Za-z0-9_-]{8,}$/;

/** Never emit credentials or secret-looking values, even if present in memory. */
function isSecret(key: string, value: unknown): boolean {
  if (key === "env_key" || key === "env_http_headers") return false;
  if (SECRET_KEY.test(key)) return true;
  return typeof value === "string" && SECRET_VALUE.test(value);
}

function isSecretValue(value: unknown): boolean {
  return typeof value === "string" && SECRET_VALUE.test(value);
}

function isEmittedValue(value: unknown): boolean {
  return value !== undefined && value !== null && !isSecretValue(value);
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return quoteToml(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `[${value.filter(isEmittedValue).map(formatValue).join(", ")}]`;
  if (isPlainObject(value)) {
    // Inline-table keys (e.g. `X-Tenant-Token`) are header names, not secrets;
    // only values are screened here. Field-name screening happens in writeTable.
    const entries = Object.entries(value).filter(([, item]) => isEmittedValue(item));
    return `{ ${entries.map(([key, item]) => `${formatKey(key)} = ${formatValue(item)}`).join(", ")} }`;
  }
  return quoteToml(String(value));
}

function orderKeys(entries: Array<[string, unknown]>, preferred: readonly string[]): Array<[string, unknown]> {
  return [...entries].sort(([left], [right]) => {
    const leftIndex = preferred.indexOf(left);
    const rightIndex = preferred.indexOf(right);
    if (leftIndex !== -1 || rightIndex !== -1) {
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    }
    return left < right ? -1 : left > right ? 1 : 0;
  });
}

const TOP_SCALARS = [
  "model",
  "model_provider",
  "model_reasoning_effort",
  "openai_base_url",
  "model_catalog_json",
];
const TOP_TABLES = ["model_providers", "agents", "features"];
const PROVIDER_SCALARS = [
  "name",
  "base_url",
  "env_key",
  "wire_api",
  "request_max_retries",
  "stream_max_retries",
  "stream_idle_timeout_ms",
  "websocket_connect_timeout_ms",
  "supports_websockets",
  "supports_standalone_web_search",
  "requires_openai_auth",
  "http_headers",
  "env_http_headers",
  "query_params",
  "aws",
];
const AGENT_SCALARS = [
  "enabled",
  "max_concurrent_threads_per_session",
  "default_subagent_model",
  "default_subagent_reasoning_effort",
];
const INLINE_KEYS = new Set(["http_headers", "env_http_headers", "query_params", "aws"]);

/**
 * Write one `[table]` (scalars first, then nested tables) into `lines`.
 * Inline-table keys such as `http_headers` are emitted as scalar values.
 */
function writeTable(
  lines: string[],
  segments: readonly string[],
  table: Table,
  preferred: readonly string[],
): void {
  const entries = Object.entries(table).filter(
    ([key, value]) => isEmittedValue(value) && !isSecret(key, value),
  );
  const scalars = entries.filter(
    ([key, value]) => !isPlainObject(value) || INLINE_KEYS.has(key),
  );
  const nested = entries.filter(
    ([key, value]) => isPlainObject(value) && !INLINE_KEYS.has(key),
  );

  if (segments.length > 0) lines.push(`[${segments.join(".")}]`);
  for (const [key, value] of orderKeys(scalars, preferred)) {
    lines.push(`${formatKey(key)} = ${formatValue(value)}`);
  }
  if (lines[lines.length - 1] !== "" && segments.length > 0) lines.push("");
  for (const [key, value] of orderKeys(nested, [])) {
    writeTable(lines, [...segments, key], value as Table, []);
  }
}

/**
 * Serialize a config with top-level scalars before tables and stable key order.
 * Secret-looking fields and values are deliberately omitted.
 */
export function serializeConfig(config: CodexConfig): string {
  const root = config as Table;
  const lines: string[] = [];
  writeTable(lines, [], root, TOP_SCALARS);
  if (lines[lines.length - 1] !== "") lines.push("");

  const tables = orderKeys(
    Object.entries(root).filter(
      ([key, value]) => isPlainObject(value) && isEmittedValue(value) && !isSecret(key, value),
    ),
    TOP_TABLES,
  );
  for (const [key, value] of tables) {
    const table = value as Table;
    if (key === "model_providers") {
      for (const [providerId, provider] of orderKeys(Object.entries(table), [])) {
        if (isPlainObject(provider)) {
          writeTable(lines, ["model_providers", providerId], provider, PROVIDER_SCALARS);
        }
      }
    } else if (key === "agents") {
      writeTable(lines, ["agents"], table, AGENT_SCALARS);
    } else {
      writeTable(lines, [key], table, []);
    }
  }

  while (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  return lines.join("\n") + "\n";
}

/** Find a `model =` key accidentally written inside a provider table. */
export function findMisplacedModelKey(text: string): string | undefined {
  let current: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = stripComment(line).trim();
    if (trimmed.length === 0) continue;
    if (trimmed.startsWith("[")) {
      const end = trimmed.indexOf("]");
      if (end === -1) continue;
      current = splitTopLevel(trimmed.slice(1, end), ".")
        .map((part) => parseKey(part.trim()))
        .filter((part) => part.length > 0);
      continue;
    }
    const equals = findEquals(trimmed);
    if (equals === -1) continue;
    const key = parseKey(trimmed.slice(0, equals).trim());
    if (key === "model" && current[0] === "model_providers") {
      return `[${current.join(".")}]`;
    }
  }
  return undefined;
}

/** Read a Codex config from disk; a missing file is an empty config. */
export async function readConfig(filePath: string): Promise<CodexConfig> {
  try {
    return parseConfig(await readFile(filePath, "utf8"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

/** Atomically write a Codex config (Windows rename-over-existing fallback). */
export async function writeConfig(filePath: string, config: CodexConfig): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  try {
    await writeFile(tempPath, serializeConfig(config), "utf8");
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
