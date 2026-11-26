[![npm version](https://img.shields.io/npm/v/opencode-individual-subagent-model-plugin.svg)](https://www.npmjs.com/package/opencode-individual-subagent-model-plugin)
[![npm downloads](https://img.shields.io/npm/dm/opencode-individual-subagent-model-plugin.svg)](https://www.npmjs.com/package/opencode-individual-subagent-model-plugin)
[![GitHub stars](https://img.shields.io/github/stars/MrQbiTwo/individual-subagent-model-plugin.svg)](https://github.com/MrQbiTwo/individual-subagent-model-plugin/stargazers)
![TypeScript 7.0](https://img.shields.io/badge/TypeScript-7.0-blue)
![OpenCode 2.3.2+](https://img.shields.io/badge/OpenCode-2.3.2%2B-green)

# Individual Subagent Model

**Individual Subagent Model** is an OpenCode plugin that lets the primary model choose the AI model used by each subagent it launches. When you ask [OpenCode](https://opencode.ai/) to spawn several subagents, the primary model can assign a different model, provider, and effort level to each one — for example a fast model for a coder subagent and a cheaper free model for a tester subagent.

> [!NOTE]
> **Individual Subagent Model** is the display name used throughout this documentation. The technical identifier `individual-subagent-model-plugin` is reserved for the repository, the on-disk configuration folder, and the npm package name, so it still appears in installation instructions, links, and package identifiers.

## What it does

- **Dynamic model catalog.** The plugin reads every model currently connected in OpenCode and exposes its ID, provider, display name, and effort levels (variants) to the primary model. Adding or removing a model or provider while OpenCode is running updates the catalog immediately.
- **Per-subagent selection.** The primary model can pick a model for a subagent in its prompt or through an agent default. A requested model must be available and permitted; otherwise the request falls back to an allowed built-in free model.
- **Provider and effort support.** Model references use the `providerID/modelID#variant` form (for example `openrouter/anthropic/claude-sonnet-5.5#max`), so a prompt can also name the provider and the desired effort level.
- **Allowlist enforcement.** Only permitted models can be assigned to subagents. Rules are stored per project and globally, with the project scope taking precedence, and are edited by hand as JSON files (see [Configuration](#configuration)).

## Configuration

**Individual Subagent Model** is controlled only by editing JSON config files — in this version there are no slash commands and no configuration panel. The server reads the rules on demand, so both the CLI and Desktop use the same files described below.

### Where the files live

The config root is platform-specific and portable:

- Windows: `%APPDATA%\individual-subagent-model-plugin\` (`APPDATA`, falling back to `%USERPROFILE%\AppData\Roaming`)
- Linux / macOS: `${XDG_CONFIG_HOME:-~/.config}/individual-subagent-model-plugin/`

Inside the root are `global.json` (rules for all projects) and `projects/<projectKey>.json` (rules for one workspace). `<projectKey>` is the OpenCode workspace ID with every character outside `A–Z a–z 0–9 _ -` replaced by `_`; when the host supplies no workspace ID the key is `default` (so the file is `projects/default.json`). The name is an opaque ID, not a project path. Both files are optional: a missing file means an empty rule for that scope ("allow nothing extra").

### File format — bare JSON

Each file is one bare rule object: no `version` key and no wrapper.

```json
{
  "models": ["openrouter/deepseek/deepseek-chat"],
  "providers": [],
  "agentDefaults": { "coder": "openrouter/deepseek/deepseek-chat#high" },
  "deniedModels": ["opencode/hy4-flash-free"],
  "deniedProviders": ["opencode-go"]
}
```

- `"models"` — allowlisted `providerID/modelID` selectors (no `#variant` here).
- `"providers"` — bare provider IDs; allows every model of that provider.
- `"agentDefaults"` — maps an agent id to `providerID/modelID#variant`. The `#variant` suffix is the effort level (for example `#high`, `#max`) and its values come from the live catalog.
- `"deniedModels"` / `"deniedProviders"` — optional deny lists. **Deny wins**: a denied model or provider is blocked even when an allow entry or the free default would permit it. Free models can now be denied explicitly.

The example allows `openrouter/deepseek/deepseek-chat` (at `high` effort for the `coder` agent) while denying `opencode/hy4-flash-free` and the whole `opencode-go` provider. Omit `deniedModels` and `deniedProviders` from a rule when you do not need them; existing three-field files stay valid.

### Precedence and live reload

1. An explicit deny (`deniedModels` / `deniedProviders`) wins everywhere.
2. For the same agent id, the project `agentDefaults` value overrides the global one.
3. Allow entries from `global.json` and the project file are combined (union of allows).
4. Otherwise a built-in free model may be used — unless it is explicitly denied.
5. Anything else is not permitted.

Rules are re-read from disk on **every call**, so an edit applies on the next subagent call — **no restart** is needed. Invalid JSON or a malformed rule is rejected; a missing file means an empty rule. Use the built-in `subagent_models` discovery tool to copy exact selectors and effort variants.

### Desktop

The Desktop app has no command or panel in this version. It loads the same server plugin, and the shared background service applies the same config files at the paths above. Edit the JSON and the next subagent call uses it; reload the Desktop plugin or restart the service only if the host does not refresh the server automatically.

## Installation

Requires **OpenCode 2.3.2 or newer**.

Add the plugin to your OpenCode configuration (`opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-individual-subagent-model-plugin"]
}
```

OpenCode resolves the package from npm on startup. You can also install it explicitly:

```sh
npm install -g opencode-individual-subagent-model-plugin
```

To build and install from a source checkout, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage example

A prompt can name the model, provider, and effort for each subagent:

> Launch a Coder subagent using Deepseek V4.1 Flash via OpenRouter at Max effort, and a Tester subagent using Beam Free from the built-in OpenCode provider.

The primary model matches these names against the live catalog, checks the allowlist, and launches each subagent with the resulting permitted model. If a name is unknown or not permitted, a built-in free model is used instead. You can also set a default model for an agent in a config file (see [Configuration](#configuration)) and omit the model from the prompt.

All model permissions come from the JSON files described in [Configuration](#configuration).

## Codex support

**Individual Subagent Model** also has a `codex/` package that applies the same rules to the Codex CLI and Codex app. It targets **Codex CLI and app 0.153.4** and has also been verified against 0.172.0 (the bundled catalog field shape is unchanged); check `codex --version` before use so that the behavior below matches your installed version.

From the repository root, install dependencies and build that package:

```sh
npm install --prefix codex
npm run build --prefix codex
```

The allowlist lives in the very same `global.json` / `projects/<key>.json` files described in [Configuration](#configuration). There is no second rule format: edit those files and the Codex integration applies the next call. The offline contract tests cover the wiring without an account, so **no Codex subscription is required** to run them.

### Provider configuration

Codex reads providers from `config.toml` in `[model_providers.<id>]` entries. A custom entry declares a wire protocol and an environment variable name:

```toml
[model_providers.my_provider]
base_url = "https://example.invalid/v1"
wire_api = "responses"
env_key = "MY_PROVIDER_API_KEY"
```

`wire_api = "responses"` is required: Codex talks to these providers through the Responses API, not the chat-completions API. `env_key` holds the **NAME of an environment variable**, never a secret — put the actual credential in your environment, not in `config.toml` or in the repository. The IDs `openai`, `ollama`, `lmstudio`, `amazon-bedrock`, `amazon-bedrock-runtime` and `gcp` are built-in reserved provider IDs in Codex; leave them to Codex instead of redefining them for custom endpoints.

Effort levels come from the model catalogue as `supported_reasoning_levels` (or the equivalent per-model variant IDs). Use the same effort/variant IDs that appear after `#variant` in the shared config, so a reference such as `my_provider/model#high` resolves to the same level on both hosts.

### How selection reaches Codex

- A `codex exec` run accepts `-m` and `-c` overrides; whichever model they select is still checked against the allowlist.
- A per-subagent provider override is **not supported** by Codex: agent files inherit the parent provider, so different subagents cannot select different providers there.
- The hooks are **observational** — they report the model a run actually used and never rewrite prompts or config.
- Rules are re-read for each call, so edits apply without a restart, just as with the OpenCode host.

## Future plans

The same model-selection rules should work everywhere. **Codex** is implemented as described above; planned implementation and support also includes:

- **Codex**
- **Claude Code**
- **Antigravity**
- **Cline**
- **Cursor**
- GUI,
- **Other agents** as the ecosystem grows

The `codex/` folder holds a working package; the `cline/`, `antigravity/`, `claudecode/` and `cursor/` folders remain reserved placeholders that contain no code and imply no support in this version.

The design goal is a universal core with thin per-agent adapters, so allowlists, model references, and effort levels stay consistent across runtimes.

And much more.

## Reporting issues

Please use the [issue tracker](https://github.com/MrQbiTwo/individual-subagent-model-plugin/issues) and check [existing issues](https://github.com/MrQbiTwo/individual-subagent-model-plugin/issues?q=is%3Aissue) before opening a new one. For bugs, use the [Bug report](.github/ISSUE_TEMPLATE/ISSUE_TEMPLATE.md) template (`.github/ISSUE_TEMPLATE/ISSUE_TEMPLATE.md`); it collects your OpenCode version, operating system, Node.js version, exact reproduction steps, expected and actual behavior, relevant configuration, and logs. The template also requires a mandatory AI disclosure naming the AI model used, if any. For questions about setup, include your `opencode.json` plugin section and the output of `opencode --version`.

## Requesting features

Open an issue with the [Enhancement / feature request](.github/ISSUE_TEMPLATE/ENCHANTMENT_ISSUE_TEMPLATE.md) template (`.github/ISSUE_TEMPLATE/ENCHANTMENT_ISSUE_TEMPLATE.md`) and describe the problem or use case, the proposed solution, alternatives you considered, and who benefits. The template requires the same mandatory AI disclosure: state whether AI was used to draft the request and, if so, which AI model produced it. Maintainers triage and label every request.

Code changes are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, branch policy, and the pull request template.

## License

Distributed under the **MIT** license. See [LICENSE](LICENSE) for the full text.
