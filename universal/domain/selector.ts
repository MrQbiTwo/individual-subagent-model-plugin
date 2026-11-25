import { CoreError, type ModelRef } from "./types.js";

/**
 * Parse a `providerID/id#variant` selector.
 *
 * The provider ends at the *first* `/`; the model id may itself contain `/`
 * (e.g. OpenRouter's `anthropic/claude-sonnet-5.5`). The variant follows the
 * *last* `#`. Malformed input throws `CoreError("invalid-model-ref")`.
 */
export function parseModelSelector(input: string): ModelRef {
  const providerEnd = input.indexOf("/");
  const providerID = input.slice(0, providerEnd);
  const rest = input.slice(providerEnd + 1);
  const hash = rest.lastIndexOf("#");
  const id = hash === -1 ? rest : rest.slice(0, hash);
  const variant = hash === -1 ? undefined : rest.slice(hash + 1);

  if (
    providerEnd <= 0 ||
    rest.length === 0 ||
    id.length === 0 ||
    (variant !== undefined && variant.length === 0)
  ) {
    throw new CoreError("invalid-model-ref", `Invalid model selector: ${JSON.stringify(input)}`);
  }

  return variant === undefined ? { providerID, id } : { providerID, id, variant };
}

/** Render a parsed reference back into the canonical selector string. */
export function formatModelRef(ref: ModelRef): string {
  const base = `${ref.providerID}/${ref.id}`;
  return ref.variant === undefined ? base : `${base}#${ref.variant}`;
}
