<!--
  Release-notes template used by .github/workflows/publish.yml.

  On a tag push the create-github-release job renders this file through
  scripts/ci/release_notes.py, replacing every {{PLACEHOLDER}} with commit
  messages, first-time contributors, the tested app/CLI versions, the build
  toolchain, and GitHub's generated release notes. The rendered Markdown is
  passed to `gh release create --notes-file`. Do not edit placeholders by hand.
-->

## What's changed

{{CHANGES}}

## New contributors

{{CONTRIBUTORS}}

## Tested with

- Application: {{APP_VERSION}}
- OpenCode CLI: {{CLI_VERSION}}

## Build toolchain

- Node.js: {{NODE_VERSION}}
- TypeScript: {{TYPESCRIPT_VERSION}}

## Full changelog

{{FULL_CHANGELOG}}
