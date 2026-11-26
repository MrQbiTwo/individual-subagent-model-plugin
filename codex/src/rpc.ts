/**
 * Parsers for the two documented Codex 0.153.4 wire surfaces: `codex exec`
 * JSONL events and `codex app-server` JSON-RPC 2.0 messages (which omit the
 * `jsonrpc` field on the wire).
 */

import { CodexError } from "./providers.js";

export type ExecJsonlEvent =
  | { type: "thread.started"; thread_id?: string; [key: string]: unknown }
  | { type: "turn.started"; [key: string]: unknown }
  | {
      type: "item.started" | "item.completed" | "item.updated";
      item?: Record<string, unknown>;
      [key: string]: unknown;
    }
  | { type: "turn.completed"; usage?: unknown; [key: string]: unknown }
  | { type: "turn.failed"; error?: unknown; [key: string]: unknown }
  | { type: "error"; message?: string; [key: string]: unknown }
  | { type: string; [key: string]: unknown };

export interface AppServerMessage {
  method?: string;
  id?: string | number;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: unknown;
  [key: string]: unknown;
}

function parseLine(line: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    throw new CodexError("invalid-jsonl", "line is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new CodexError("invalid-jsonl", "line is not a JSON object");
  }
  return parsed as Record<string, unknown>;
}

/** Parse one `codex exec --json` envelope. */
export function parseExecJsonl(line: string): ExecJsonlEvent {
  const parsed = parseLine(line);
  if (typeof parsed.type !== "string" || parsed.type.length === 0) {
    throw new CodexError("invalid-jsonl", "exec event has no type discriminator");
  }
  return parsed as ExecJsonlEvent;
}

/** Parse one `codex app-server` message or notification. */
export function parseAppServerMessage(line: string): AppServerMessage {
  const parsed = parseLine(line);
  const hasMethod = typeof parsed.method === "string" && parsed.method.length > 0;
  const hasResponse = "result" in parsed || "error" in parsed;
  if (!hasMethod && !hasResponse) {
    throw new CodexError("invalid-jsonl", "app-server message has no method discriminator");
  }
  return parsed as AppServerMessage;
}
