---
name: codex-subagent-routing
description: Inspect or verify the Individual Subagent Model allowlist and per-subagent model routing for Codex CLI/app using offline contract probes, without an account or model call.
---

# Codex subagent routing

This plugin packages the Codex adapter for the Individual Subagent Model rules. Use it when you need to inspect or verify how a Codex subagent model is chosen, without spending tokens or contacting a model.

## Offline verification (preferred)

From the repository root:

```sh
npm ci --prefix codex
npm run build --prefix codex
node codex/tools/codex_probe.mjs contract
node codex/tools/codex_probe.mjs ports
node codex/tools/codex_probe.mjs exec-args
```

The probe prints exactly one JSON value. `contract` shows the frozen RPC names; `ports` confirms the adapter implements the host-free catalog/config ports with free models failing closed; `exec-args` shows the exact `codex exec` argument array.

## Rules to preserve

- The allowlist is the shared `global.json` / `projects/<key>.json` files. Do not create a second rule format.
- A selector has the shape `providerID/modelID#variant`; the suffix is a reasoning-effort variant.
- `wire_api` must be `responses` for a custom provider. Never write `chat`, and never put an API key in `env_key` — it holds the name of an environment variable.
- Reserved provider IDs (`openai`, `ollama`, `lmstudio`, `amazon-bedrock`, `amazon-bedrock-runtime`, `gcp`) are managed by Codex; do not redefine them.
- Codex subagents inherit the parent's provider. A per-subagent provider override is not supported; only model and effort can be routed.
- Hooks are observational for model requests. Do not treat them as a policy-enforcement boundary.
- Check `codex --version` before relying on version-specific behavior. The adapter's contract tests are offline and need no Codex subscription.

Do not ask the user for credentials and do not make model calls for these checks.
