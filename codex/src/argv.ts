/** Build `codex exec` argument arrays. Never produce a shell string. */

import { CodexError } from "./providers.js";

/** Quote a TOML value for use in `-c key="value"`. */
export function quoteTomlValue(value: string): string {
  return `"${value
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t")}"`;
}

export interface BuildExecArgsInput {
  model: string;
  providerId?: string;
  profile?: string;
  sandbox?: string;
  json?: boolean;
  ephemeral?: boolean;
  cwd?: string;
  extraConfig?: Record<string, string>;
  prompt: string;
}

function assertNoNul(field: string, value: string | undefined): void {
  if (value !== undefined && value.includes("\0")) {
    throw new CodexError("SHELL_METACHARACTER", `${field} contains a NUL byte`);
  }
}

/**
 * Produce argv in the frozen order used by the probe and by callers:
 * exec, flags, -m model, provider override, extra -c values, prompt last.
 */
export function buildExecArgs(input: BuildExecArgsInput): string[] {
  for (const [field, value] of Object.entries(input)) {
    if (typeof value === "string") assertNoNul(field, value);
  }
  for (const [key, value] of Object.entries(input.extraConfig ?? {})) {
    assertNoNul("extraConfig key", key);
    assertNoNul("extraConfig value", value);
  }

  const args: string[] = ["exec"];
  if (input.json) args.push("--json");
  if (input.ephemeral) args.push("--ephemeral");
  if (input.sandbox !== undefined) args.push("--sandbox", input.sandbox);
  if (input.profile !== undefined) args.push("--profile", input.profile);
  if (input.cwd !== undefined) args.push("--cd", input.cwd);
  args.push("-m", input.model);
  if (input.providerId !== undefined) {
    args.push("-c", `model_provider=${quoteTomlValue(input.providerId)}`);
  }
  for (const [key, value] of Object.entries(input.extraConfig ?? {})) {
    args.push("-c", `${key}=${quoteTomlValue(value)}`);
  }
  args.push(input.prompt);
  return args;
}
