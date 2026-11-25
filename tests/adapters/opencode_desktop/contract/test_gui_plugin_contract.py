"""Desktop absence + shared-config contract.

There is no Desktop GUI plugin, no palette command and no GUI bundle in this
version. The Desktop app loads the same server plugin as the CLI and reads the
same sidecar config files, so this module asserts (a) the absence of every GUI
artifact and (b) that policy really comes from those shared files.

Contract-only: no headless Electron is launched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
OPENCODE = REPO_ROOT / "opencode"
UNIVERSAL = REPO_ROOT / "universal"
PACKAGE_JSON = OPENCODE / "package.json"
DISPLAY = "Individual Subagent Model"
EMPTY_RULE = {"models": [], "providers": [], "agentDefaults": {}}

ABSENT_PATHS = (
    "opencode/vite.config.ts",
    "opencode/src/adapters/opencode_desktop",
    "opencode/src/adapters/opencode_cli/tui",
    "universal/ui",
    "opencode/dist/adapters/opencode_desktop",
    "opencode/dist/adapters/opencode_cli/tui",
    "opencode/dist/universal/ui",
    "opencode/dist/gui-experimental.cjs",
    "opencode/dist/tui.js",
    "scripts/ci/check_gui_bundle.py",
)
COMMAND_PATTERNS = (
    re.compile(r"keymap\s*\.\s*layer\s*\("),
    re.compile(r"\bregisterCommands\b"),
    re.compile(r"\bcontext\s*\.\s*keymap\b"),
    re.compile(r"\bctx\s*\.\s*command\b"),
    re.compile(r"\bslash\s*:"),
    re.compile(r"\bpalette\s*:\s*true\b"),
    re.compile(r"\bctx\s*\.\s*add\s*\(\s*Command\b"),
    re.compile(r"subagent-models-allowed(?:-global)?"),
    re.compile(r"\ballowed-global\b"),
    re.compile(r"group\s*:\s*[\"']" + re.escape(DISPLAY) + r"[\"']"),
)


def _package() -> dict:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))


def test_desktop_gui_export_is_absent() -> None:
    package = _package()
    assert set(package["exports"]) == {".", "./rpc"}
    assert "./gui-experimental" not in package["exports"]
    assert "./tui" not in package["exports"]
    assert "dist" in package["files"]


def test_desktop_and_ui_artifacts_are_absent() -> None:
    present = [relative for relative in ABSENT_PATHS if (REPO_ROOT / relative).exists()]
    assert present == [], f"removed GUI/UI artifacts are still present: {present}"


def test_gui_command_probe_and_bundle_check_are_absent() -> None:
    probes = sorted(
        path.name
        for path in (OPENCODE / "tools").rglob("*.mjs")
        if "command_registration_probe" in path.name or "palette_section_probe" in path.name
    )
    assert probes == [], f"deleted GUI probes survived: {probes}"


def test_no_command_contribution_in_source_or_dist() -> None:
    roots = (OPENCODE / "src", OPENCODE / "dist")
    hits: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        suffixes = ("*.ts", "*.tsx") if root.name == "src" else ("*.js", "*.cjs", "*.mjs")
        files = {path for suffix in suffixes for path in root.rglob(suffix)}
        for path in sorted(files):
            if "node_modules" in path.parts or path.name.endswith(".map"):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                hits.extend(
                    f"{path.relative_to(REPO_ROOT)}:{number}: {pattern.pattern}"
                    for pattern in COMMAND_PATTERNS
                    if pattern.search(line)
                )
    assert hits == [], "command contribution survived the removal:\n" + "\n".join(hits)


def test_no_command_contribution_in_universal_source() -> None:
    assert UNIVERSAL.is_dir(), "universal source tree is missing"
    hits: list[str] = []
    files = sorted(UNIVERSAL.rglob("*.ts")) + sorted(UNIVERSAL.rglob("*.tsx"))
    assert files, "no universal TypeScript files found"
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hits.extend(
                f"{path.relative_to(REPO_ROOT)}:{number}: {pattern.pattern}"
                for pattern in COMMAND_PATTERNS
                if pattern.search(line)
            )
    assert hits == [], "command contribution survived in universal source:\n" + "\n".join(hits)


def test_desktop_reads_the_shared_config_files(rpc_call, config_files, any_two_models) -> None:
    """Desktop and CLI share one server policy store at the documented paths."""
    config_files.reset()
    rule = {"models": [any_two_models[0].primary.selector], "providers": [], "agentDefaults": {}}
    config_files.write_global(rule)
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == rule
    config_files.delete_global()
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == EMPTY_RULE
