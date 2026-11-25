---
name: Bug report
about: Report a reproducible problem with Individual Subagent Model
title: "[Bug]: "
labels: bug, triage
assignees: ""
---

## Before you start

- [ ] I searched [existing issues](https://github.com/MrQbiTwo/individual-subagent-model-plugin/issues?q=is%3Aissue) and this is not a duplicate.
- [ ] This is not a security vulnerability (report those privately to the maintainers).
- [ ] This is a bug report. For a feature request, use the enhancement template.

## Summary

<!-- One or two sentences: what went wrong? -->

## AI disclosure (mandatory)

- [ ] No AI was used to draft this request.
- [ ] AI was used to draft or help write this request.

**AI model(s) used** *(mandatory if the second box is checked; write `N/A` otherwise)*:
<!-- Example: OpenCode hy4-flash-free. State "unknown" if you cannot identify the model. -->

## Environment

- Operating system and version:
- Node.js version (`node --version`):
- npm version (`npm --version`):
- OpenCode version (`opencode --version`):
- Plugin version (npm package or built commit):
- Install method: global npm / local source build
- Where it happened: OpenCode CLI / OpenCode Desktop
- Scope: project allowlist / global allowlist

## Configuration

<!-- Paste the relevant `opencode.json` plugin section and any allowlist settings. REDACT tokens, keys and private paths. -->

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-individual-subagent-model-plugin"]
}
```

## Steps to reproduce

1.
2.
3.

## Expected behavior

## Actual behavior

## Logs and screenshots

<!-- Paste relevant logs or error output. REDACT tokens, keys and private paths. -->

## Minimal reproducer

<!-- A minimal prompt or configuration that reproduces the problem is especially helpful. -->

## Workaround (if any)

## Additional context
