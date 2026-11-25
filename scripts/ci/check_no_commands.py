#!/usr/bin/env python3
"""Zero-command static guard for the Individual Subagent Model plugin.

The plugin is a server + RPC + config-only product: no CLI slash commands, no
Desktop GUI commands, no UI adapters and no UI package exports may remain.
This guard scans the OpenCode source, the repo-root ``universal`` host-free
source, the generated ``dist`` bundles, the Node probes and the package exports.
It prints a JSON report on stdout and exits 1 when any command/UI contribution is
still present.

Paths resolve from ``__file__`` so the guard is CI- and pytest-xdist-safe.

Allowlist (never flagged): the host readiness route ``/api/command``, the
``subagent_models`` discovery tool, the RPC method names and a bare ``Command``
TypeScript type import. Only host-visible command contributions are violations.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OPENCODE = REPO_ROOT / "opencode"
SRC = OPENCODE / "src"
DIST = OPENCODE / "dist"
TOOLS = OPENCODE / "tools"
UNIVERSAL = REPO_ROOT / "universal"
PACKAGE_JSON = OPENCODE / "package.json"

# Tokens that are allowed to contain command-shaped words without being
# command registrations. A hit is suppressed only when the *matched token*
# itself contains one of these, so real violations (e.g. the command id
# "subagent-models-allowed", which starts with the RPC namespace) are never
# accidentally allowlisted by the "subagent-models" namespace itself.
ALLOWLIST_TOKENS = (
    "/api/command",
    "subagent_models",
    "get_catalog",
    "get_policy",
    "set_policy",
)

# (label, regex) pairs applied to source and dist text files.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("keymap.layer", re.compile(r"keymap\s*\.\s*layer\s*\(")),
    ("registerCommands", re.compile(r"\bregisterCommands\b")),
    ("context.keymap", re.compile(r"\bcontext\s*\.\s*keymap\b")),
    ("ctx.command", re.compile(r"\bctx\s*\.\s*command\b")),
    ("command.register", re.compile(r"\bcommand\s*\.\s*register\b")),
    ("slash:", re.compile(r"\bslash\s*:")),
    ("palette: true", re.compile(r"\bpalette\s*:\s*true\b")),
    ("ctx.add(Command", re.compile(r"\bctx\s*\.\s*add\s*\(\s*Command\b")),
    (
        "command id subagent-models-allowed",
        re.compile(r"subagent-models-allowed-global|subagent-models-allowed\b"),
    ),
    ("command id PROJECT_COMMAND_ID", re.compile(r"\bPROJECT_COMMAND_ID\b")),
    ("command id GLOBAL_COMMAND_ID", re.compile(r"\bGLOBAL_COMMAND_ID\b")),
    ("command id allowed-global", re.compile(r"\ballowed-global\b")),
    ("command group", re.compile(r"group\s*:\s*[\"']Individual Subagent Model[\"']")),
    ("gui-experimental export", re.compile(r"gui-experimental")),
    ("./tui export", re.compile(r"\./tui\b")),
)

# Probe files that only existed to exercise the deleted command/UI code.
BANNED_PROBES = frozenset(
    {
        "tui_command_registration_probe.mjs",
        "palette_section_probe.mjs",
        "model_picker_interaction_probe.mjs",
        "model_picker_probe.mjs",
        "picker_slot_color_probe.mjs",
        "gui_command_registration_probe.mjs",
    }
)

# Package exports that make the command/UI plugins host-loadable.
BANNED_EXPORTS = ("./tui", "./gui-experimental")

SOURCE_SUFFIXES = ("*.ts", "*.tsx")
DIST_SUFFIXES = ("*.js", "*.cjs", "*.mjs")


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _allowlisted(token: str) -> bool:
    return any(item in token for item in ALLOWLIST_TOKENS)


def _scan_text_files(root: Path, suffixes: tuple[str, ...], matches: list[str]) -> None:
    if not root.is_dir():
        return
    files: set[Path] = set()
    for suffix in suffixes:
        files.update(root.rglob(suffix))
    for path in sorted(files):
        if "node_modules" in path.parts or path.name.endswith(".map"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, regex in PATTERNS:
                for found in regex.finditer(line):
                    token = found.group(0)
                    if _allowlisted(token):
                        continue
                    matches.append(f"{_relative(path)}:{lineno}: {label}")


def _scan_probes(matches: list[str]) -> None:
    if not TOOLS.is_dir():
        return
    for path in sorted(TOOLS.rglob("*.mjs")):
        if path.name in BANNED_PROBES:
            matches.append(f"{_relative(path)}:0: banned command/UI probe")


def _scan_exports(matches: list[str]) -> None:
    if not PACKAGE_JSON.is_file():
        return
    try:
        data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    exports = data.get("exports")
    if not isinstance(exports, dict):
        return
    for key in BANNED_EXPORTS:
        if key in exports:
            matches.append(f"{_relative(PACKAGE_JSON)}:0: banned export {key!r}")


def main() -> int:
    matches: list[str] = []
    _scan_text_files(SRC, SOURCE_SUFFIXES, matches)
    _scan_text_files(UNIVERSAL, SOURCE_SUFFIXES, matches)
    _scan_text_files(DIST, DIST_SUFFIXES, matches)
    _scan_probes(matches)
    _scan_exports(matches)

    # De-duplicate while keeping scan order.
    seen: set[str] = set()
    unique: list[str] = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            unique.append(match)

    report = {
        "ok": not unique,
        "matches": unique,
        "failures": [] if not unique else ["command/UI contributions still present"],
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not unique else 1


if __name__ == "__main__":
    sys.exit(main())
