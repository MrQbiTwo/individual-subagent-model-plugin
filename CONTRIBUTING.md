# Contributing

Thanks for helping improve **Individual Subagent Model**. This document covers the development setup, the layout of the code, the local checks you should run, and the branch policy the project follows. The technical identifier `individual-subagent-model-plugin` is used only for the repository, the on-disk configuration folder, and the npm package name; user-facing copy uses the display name.

## Development environment

- **Node.js and npm.** **Node.js 22.0.0 is the minimum required version**, matching the `engines` field in `opencode/package.json`. Use **Node.js 24** with its bundled npm for development; it is the tested toolchain. Building from source uses the TypeScript compiler only. No extra Node.js floor applies.
- **Python 3.12.3 or newer** for all test and CI helper scripts. Install dependencies either with [uv](https://docs.astral.sh/uv/) (`uv sync --project tests --all-groups`) or with a virtual environment plus `python -m pip install -r tests/requirements.txt`. The canonical dependency ranges live in `tests/pyproject.toml`; keep the two files in sync when you change a version.
- **OpenCode 2.3.2 or newer** on your `PATH` if you want to run the end-to-end tests, which launch a real client.
- **Codex CLI and Codex app 0.153.4** for the Codex integration checks. Check `codex --version` before using it; the offline contract tests need no account or subscription.

The plugin itself is written in TypeScript 7.0+; the version is pinned in `opencode/package.json`.

## Plugin structure

```
.
├── universal/                 # host-free core at the repository root: domain
│   │                          # rules, catalog service, ports, events, RPC
│   │                          # contract (pure TypeScript)
│   ├── tsconfig.json          # emits declarations into opencode/dist/universal
│   └── domain/ services/ rpc/ ports.ts events.ts index.ts
├── opencode/                  # the OpenCode plugin package (npm)
│   ├── src/
│   │   ├── adapters/
│   │   │   └── opencode_cli/  # OpenCode SDK bridge: host, config store,
│   │   │                      # routing, RPC, server setup
│   │   ├── index.ts           # server plugin entry point
│   │   └── rpc.ts             # RPC export (wire compatibility)
│   ├── tools/                 # dependency-free probes for tests
│   ├── dist/                  # build output (generated, not committed)
│   ├── package.json
│   └── tsconfig.json
├── codex/                     # the Codex CLI / Codex app package (npm)
│   ├── src/
│   │   └── index.ts           # Codex hook entry point
│   ├── dist/                  # build output (generated, not committed)
│   ├── package.json
│   └── tsconfig.json
├── tests/                     # unit, integration and end-to-end tests
├── scripts/                   # native Bash and PowerShell test runners + CI helpers
└── .github/workflows/         # CI, CodeQL, compatibility and release workflows
```

The split has one rule: the repo-root `universal/` never imports an `@opencode/*` package. All host interaction lives in `opencode/src/adapters/opencode_cli/`, which is the only layer that talks to the SDK. There is no UI or command layer: users control the plugin by editing its JSON config files, documented in the Configuration section of [README.md](README.md). Keep this boundary intact when adding features.

The `codex/` folder shown above is a real, buildable package for Codex. The repo-root `cline/`, `antigravity/`, `claudecode/` and `cursor/` folders are reserved placeholders for future agent integrations: each contains only a zero-byte `.gitkeep`, holds no code, and implies no support in this version.

## Build, typecheck, and tests

From the repository root:

```sh
npm run build --prefix opencode
npm run typecheck --prefix opencode
npm install --prefix codex
npm run build --prefix codex
```

Both OpenCode commands first emit the universal core declarations into `opencode/dist/universal/`, then compile the OpenCode adapters into `opencode/dist/`. `build` emits compiled JavaScript and declarations; `typecheck` runs the same compilers without emitting files. The Codex package builds from its own `codex/package.json`.

Run the full suite with the native runner for your platform:

```sh
# Linux and macOS
bash scripts/run_tests.sh
```

```powershell
# Windows (PowerShell)
pwsh ./scripts/run_tests.ps1
```

Each runner installs dependencies, builds the package, runs `pytest` over the `unit`, `integration`, and `e2e` markers, writes `reports/junit.xml`, and checks the Node engine policy. To run a single test file during development:

```sh
python -m pytest tests/unit/test_docs.py -v
# or, when using uv:
uv run --project tests python -m pytest tests/unit/test_docs.py -v
```

Continuous integration executes checks on `ubuntu-24.04`, `ubuntu-24.04-arm`, `windows-latest`, `macos-latest`, and `windows-11-arm`. A change is not ready to merge until it passes on all of them.

## Coding and organization standards

- Use clear, descriptive **English** identifiers. Name files and directories in lowercase with spaces replaced by underscores (for example `config_store.ts`, `catalog_service.ts`). System files, configuration files, and `README`-style documents are the only naming exceptions.
- Write comments in **English**. Make them detailed enough to explain *why* a non-obvious choice exists, and concise enough to avoid repetition and filler. Keep the entire codebase, including test names and messages, in English.
- Keep the directory structure logical: data and pure rules in `universal/`, side effects in `adapters/`. Do not add host imports to `universal/`.
- Prefer small, focused functions and immutable data. Add tests for every behavior change, covering both the normal path and relevant error cases.
- Follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). `opencode/package.json` holds a plain `X.Y.Z` version; release tags use `vX.Y.Z` and must match that version. Bump the major, minor, or patch component according to the compatibility impact of the change.

## Contribution procedure

This repository uses a two-branch flow. **All code, pull requests, and other contributions go to the `untested` branch first; they reach `main` only after CI is green.** The `main` branch is protected with required status checks and direct pushes are not accepted.

1. Search the issue tracker for an existing report, then open or pick an issue describing the change. Use the matching issue template — the [Bug report](.github/ISSUE_TEMPLATE/ISSUE_TEMPLATE.md) (`.github/ISSUE_TEMPLATE/ISSUE_TEMPLATE.md`) or the [Enhancement / feature request](.github/ISSUE_TEMPLATE/ENCHANTMENT_ISSUE_TEMPLATE.md) (`.github/ISSUE_TEMPLATE/ENCHANTMENT_ISSUE_TEMPLATE.md`); both require the mandatory AI disclosure naming the model used.
2. Create your working branch from `untested` and keep changes focused on that issue.
3. Implement the change together with tests. Run `npm run build`, `npm run typecheck`, and the test runner locally before submitting. For changes to the Codex package, also check the behavior against Codex CLI / Codex app 0.153.4; offline contract tests require no account.
4. Open a pull request **targeting `untested`**. Describe what changed, how you verified it, and link the issue. Fill in the body using [PR_TEMPLATE.md](PR_TEMPLATE.md) (`PR_TEMPLATE.md`, auto-applied from `.github/pull_request_template.md`), including the mandatory AI disclosure. CI runs across all five runner labels listed above.
5. Address review feedback by pushing more commits to the same branch. When every check passes, a maintainer merges the pull request into `untested`.
6. After the scheduled checks confirm the merged state is green, the change is promoted to `main`. If a check fails, the code stays in `untested` and is retested automatically until it passes.

CodeQL analysis runs on every change to `main` and on a recurring schedule. Please do not weaken a check to make a pull request pass; fix the underlying issue instead.
