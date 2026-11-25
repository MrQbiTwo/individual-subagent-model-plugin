/**
 * Runtime-neutral routing decisions for `subagent` tool overrides.
 *
 * This module never imports `@opencode/*`. It turns a requested model/provider/
 * effort override into a validated, allowlisted `provider/id#variant` selector,
 * falling back to the parent model and finally to a free built-in model.
 */

import { findBySelector } from "./catalog.js";
import { decideWithScopes } from "./policy.js";
import { formatModelRef, parseModelSelector } from "./selector.js";
import {
  CoreError,
  type AllowlistRule,
  type Catalog,
  type ModelRef,
  type ResolvedSubagentModel,
  type SubagentToolInput,
} from "./types.js";

type CandidateSource = ResolvedSubagentModel["source"];

interface Candidate {
  readonly ref: ModelRef;
  readonly source: CandidateSource;
}

/** Parse a candidate selector; malformed references are skipped, not fatal. */
function parseCandidate(value: string | undefined): ModelRef | undefined {
  if (value === undefined || value.length === 0) return undefined;
  try {
    return parseModelSelector(value);
  } catch (error) {
    if (error instanceof CoreError) return undefined;
    throw error;
  }
}

/** Validate one candidate against catalog, effort list and both allowlist scopes. */
function resolveCandidate(
  ref: ModelRef,
  source: CandidateSource,
  catalog: Catalog,
  global: AllowlistRule,
  project: AllowlistRule,
): ResolvedSubagentModel | undefined {
  const withoutVariant = formatModelRef({ providerID: ref.providerID, id: ref.id });
  const descriptor = findBySelector(catalog, withoutVariant);
  if (descriptor === undefined) return undefined;
  if (ref.variant !== undefined && !descriptor.efforts.includes(ref.variant)) return undefined;
  if (!decideWithScopes(descriptor, global, project).allowed) return undefined;

  return { ref, descriptor, selectorWithVariant: formatModelRef(ref), source };
}

/**
 * Choose the model a spawned subagent must use.
 *
 * Precedence: explicit tool override, then the agent's persisted default
 * (project beats global), then the parent session model when it is permitted.
 * A free built-in model with at least one effort is the last-resort fallback.
 */
export function resolveSubagentRoute(
  input: SubagentToolInput,
  catalog: Catalog,
  global: AllowlistRule,
  project: AllowlistRule,
  parentModel: ModelRef,
): ResolvedSubagentModel | undefined {
  const candidates: Candidate[] = [];

  const explicit = parseCandidate(input.model);
  if (explicit !== undefined) candidates.push({ ref: explicit, source: "explicit" });

  // Project defaults override global ones for the same agent id.
  const agentDefault = project.agentDefaults[input.agent] ?? global.agentDefaults[input.agent];
  const fromAgent = parseCandidate(agentDefault);
  if (fromAgent !== undefined) candidates.push({ ref: fromAgent, source: "agent-default" });

  const parent = parseCandidate(formatModelRef(parentModel));
  if (parent !== undefined) {
    const parentSelector = formatModelRef({ providerID: parent.providerID, id: parent.id });
    const parentDescriptor = findBySelector(catalog, parentSelector);
    if (parentDescriptor !== undefined && decideWithScopes(parentDescriptor, global, project).allowed) {
      candidates.push({ ref: parent, source: "parent" });
    }
  }

  for (const candidate of candidates) {
    const resolved = resolveCandidate(candidate.ref, candidate.source, catalog, global, project);
    if (resolved !== undefined) return resolved;
  }

  // Fail closed to a permitted free built-in model; a denied free model (by
  // selector or provider) must never become the last-resort subagent route.
  for (const model of catalog.models) {
    const firstEffort = model.efforts[0];
    if (
      model.isFree &&
      firstEffort !== undefined &&
      decideWithScopes(model, global, project).allowed
    ) {
      const ref: ModelRef = { providerID: model.providerID, id: model.id, variant: firstEffort };
      return {
        ref,
        descriptor: model,
        selectorWithVariant: formatModelRef(ref),
        source: "free-default",
      };
    }
  }
  return undefined;
}

/** Compact `selector [effort, ...]` list injected into the primary model's context. */
export function buildCatalogNote(
  catalog: Catalog,
  global: AllowlistRule,
  project: AllowlistRule,
): string {
  const lines: string[] = [];
  for (const model of catalog.models) {
    if (!decideWithScopes(model, global, project).allowed) continue;
    const efforts = model.efforts.length > 0 ? ` [${model.efforts.join(", ")}]` : "";
    lines.push(`${model.selector}${efforts}`);
  }
  return lines.join("\n");
}
