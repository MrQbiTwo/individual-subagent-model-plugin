import type { AllowlistRule, ModelDescriptor, PolicyDecision, RuleMutation } from "./types.js";

/** Empty allowlist: no explicit models, providers, or agent defaults. */
export function emptyRule(): AllowlistRule {
  return { models: [], providers: [], agentDefaults: {} };
}

/** Union of global and project rules; project entries win on conflict. */
export function effectiveRule(global: AllowlistRule, project: AllowlistRule): AllowlistRule {
  const models = [...global.models];
  for (const selector of project.models) {
    if (!models.includes(selector)) models.push(selector);
  }
  const providers = [...global.providers];
  for (const providerID of project.providers) {
    if (!providers.includes(providerID)) providers.push(providerID);
  }

  // Deny unions are deduplicated. The keys are emitted only when non-empty so
  // rules without any deny still serialize to the original three-field shape.
  const deniedModels = [...(global.deniedModels ?? [])];
  for (const selector of project.deniedModels ?? []) {
    if (!deniedModels.includes(selector)) deniedModels.push(selector);
  }
  const deniedProviders = [...(global.deniedProviders ?? [])];
  for (const providerID of project.deniedProviders ?? []) {
    if (!deniedProviders.includes(providerID)) deniedProviders.push(providerID);
  }

  return {
    models,
    providers,
    agentDefaults: { ...global.agentDefaults, ...project.agentDefaults },
    ...(deniedModels.length > 0 ? { deniedModels } : {}),
    ...(deniedProviders.length > 0 ? { deniedProviders } : {}),
  };
}

/**
 * Decide against one rule (callers pass either global or the effective rule).
 * Deny is checked first so it beats both explicit allows and the free fallback.
 */
export function decide(model: ModelDescriptor, rule: AllowlistRule): PolicyDecision {
  if (
    rule.deniedModels?.includes(model.selector) ||
    rule.deniedProviders?.includes(model.providerID)
  ) {
    return { allowed: false, reason: "explicitly-denied" };
  }
  if (model.isFree) return { allowed: true, reason: "free-default" };
  if (rule.models.includes(model.selector)) return { allowed: true, reason: "global-model" };
  if (rule.providers.includes(model.providerID)) return { allowed: true, reason: "global-provider" };
  return { allowed: false, reason: "not-allowlisted" };
}

export function isAllowed(model: ModelDescriptor, rule: AllowlistRule): boolean {
  return decide(model, rule).allowed;
}

/**
 * Decide against both scopes, reporting which scope granted access.
 * Denies from either scope are honoured (union) and beat every allow and the
 * free fallback.
 */
export function decideWithScopes(
  model: ModelDescriptor,
  global: AllowlistRule,
  project: AllowlistRule,
): PolicyDecision {
  if (
    global.deniedModels?.includes(model.selector) ||
    project.deniedModels?.includes(model.selector) ||
    global.deniedProviders?.includes(model.providerID) ||
    project.deniedProviders?.includes(model.providerID)
  ) {
    return { allowed: false, reason: "explicitly-denied" };
  }
  if (global.models.includes(model.selector)) return { allowed: true, reason: "global-model" };
  if (global.providers.includes(model.providerID)) return { allowed: true, reason: "global-provider" };
  if (project.models.includes(model.selector)) return { allowed: true, reason: "project-model" };
  if (project.providers.includes(model.providerID)) return { allowed: true, reason: "project-provider" };
  if (model.isFree) return { allowed: true, reason: "free-default" };
  return { allowed: false, reason: "not-allowlisted" };
}

/** Pure rule mutation: always returns a new rule, never mutates the input. */
export function applyRuleMutation(rule: AllowlistRule, mutation: RuleMutation): AllowlistRule {
  switch (mutation.kind) {
    case "toggle-model": {
      const models = rule.models.includes(mutation.selector)
        ? rule.models.filter((selector) => selector !== mutation.selector)
        : [...rule.models, mutation.selector];
      return { ...rule, models };
    }
    case "set-model": {
      const present = rule.models.includes(mutation.selector);
      const models = mutation.enabled
        ? present ? [...rule.models] : [...rule.models, mutation.selector]
        : rule.models.filter((selector) => selector !== mutation.selector);
      return { ...rule, models };
    }
    case "set-provider": {
      const present = rule.providers.includes(mutation.providerID);
      const providers = mutation.enabled
        ? present ? [...rule.providers] : [...rule.providers, mutation.providerID]
        : rule.providers.filter((providerID) => providerID !== mutation.providerID);
      return { ...rule, providers };
    }
    case "set-agent-default": {
      const agentDefaults = { ...rule.agentDefaults };
      if (mutation.selectorWithVariant === undefined) {
        delete agentDefaults[mutation.agentID];
      } else {
        agentDefaults[mutation.agentID] = mutation.selectorWithVariant;
      }
      return { ...rule, agentDefaults };
    }
  }
}
