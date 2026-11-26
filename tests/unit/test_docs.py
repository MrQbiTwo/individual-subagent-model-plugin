"""Contracts for the user-facing documentation files.

This module pins the badges, the config-file-only Configuration section, the
absence of every command/UI reference, the runner labels and ignore rules, and
the "Individual Subagent Model" display-name branding of the user-facing copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DISPLAY = "Individual Subagent Model"
TECHNICAL = "individual-subagent-model-plugin"
ISSUE_TEMPLATE_DIR = ".github/ISSUE_TEMPLATE"
BUG_TEMPLATE = f"{ISSUE_TEMPLATE_DIR}/ISSUE_TEMPLATE.md"
ENCHANTMENT_TEMPLATE = f"{ISSUE_TEMPLATE_DIR}/ENCHANTMENT_ISSUE_TEMPLATE.md"
ENHANCEMENT_TEMPLATE = f"{ISSUE_TEMPLATE_DIR}/ENHANCEMENT_ISSUE_TEMPLATE.md"
PR_TEMPLATE = "PR_TEMPLATE.md"
PR_TEMPLATE_AUTO = ".github/pull_request_template.md"
RELEASE_TEMPLATE = ".github/release-template.md"
PUBLISH_WORKFLOW = ".github/workflows/publish.yml"
RUNNERS = (
    "ubuntu-24.04",
    "ubuntu-24.04-arm",
    "windows-latest",
    "macos-latest",
    "windows-11-arm",
)

# The plugin exposes no commands or UI in this version. Every user-facing file
# must be free of command ids, command sections and picker/GUI wording.
COMMAND_FREE_DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    BUG_TEMPLATE,
    ENCHANTMENT_TEMPLATE,
    ENHANCEMENT_TEMPLATE,
    PR_TEMPLATE,
    PR_TEMPLATE_AUTO,
)
COMMAND_MARKERS = (
    "/subagent-models-allowed",
    "/subagent-models-allowed-global",
    "## Commands",
    "| Command |",
    "allowlist panel",
    "palette",
    "keymap",
    "Enable all",
    "Disable all",
)
CONFIG_ROOT_WINDOWS = "%APPDATA%\\individual-subagent-model-plugin\\"
CONFIG_ROOT_XDG = "${XDG_CONFIG_HOME:-~/.config}/individual-subagent-model-plugin/"


def _read(name: str) -> str:
    path = REPO_ROOT / name
    assert path.is_file(), f"{name} is missing"
    return path.read_text(encoding="utf-8")


def test_readme_badges_are_first() -> None:
    non_blank = [line for line in _read("README.md").splitlines() if line.strip()]
    assert len(non_blank) >= 5
    for line in non_blank[:5]:
        assert "img.shields.io" in line


def test_readme_required_content() -> None:
    readme = _read("README.md")
    for snippet in (
        "2.3.2",
        "MIT",
        "7.0",
        "npm install",
        "## Configuration",
        "global.json",
        "projects/",
        "agentDefaults",
        "deniedModels",
        "deniedProviders",
        "#variant",
        CONFIG_ROOT_WINDOWS,
        "APPDATA",
        "XDG_CONFIG_HOME",
        "subagent_models",
        "Desktop",
    ):
        assert snippet in readme, f"README.md is missing {snippet!r}"
    for forbidden in ("another agent", "WSL"):
        assert forbidden.lower() not in readme.lower()


def _section(markdown: str, heading: str) -> str:
    """Return the body of a top-level Markdown section (up to the next H2)."""
    marker = f"## {heading}"
    assert marker in markdown, f"missing section {marker!r}"
    return markdown.split(marker, 1)[1].split("\n## ", 1)[0]


def test_readme_configuration_section() -> None:
    readme = _read("README.md")
    section = _section(readme, "Configuration")
    assert CONFIG_ROOT_WINDOWS in section, "generic Windows config root must be spelled out"
    assert "%APPDATA%\\individual-subagent-model-plugin\\" in section
    assert CONFIG_ROOT_XDG in section
    # Only portable path forms may appear: no absolute user profile, machine-local
    # state, or a count of the selectors present on one developer's host.
    assert re.search(r"[A-Za-z]:\\Users\\", readme) is None, (
        "README must not contain an absolute Windows user path"
    )
    assert "this machine" not in readme.lower(), "README must not describe machine-local state"
    assert "present here" not in readme.lower(), "README must not state which files exist locally"
    selector_count = re.search(
        r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+free\b",
        readme,
        re.IGNORECASE,
    )
    assert selector_count is None, "README must not count specific free selectors"
    assert "global.json" in section
    assert "projects/" in section
    assert "<projectKey>" in section
    assert "default.json" in section
    # Bare JSON schema: every field, effort as a #variant suffix.
    for field in (
        '"models"',
        '"providers"',
        '"agentDefaults"',
        '"deniedModels"',
        '"deniedProviders"',
    ):
        assert field in section, f"schema field {field!r} is not documented"
    assert "#variant" in section
    # Deny wins, project over global, re-read on every call, no restart.
    assert "deny wins" in section.lower(), "deny-wins precedence must be documented"
    for token in ("override", "global", "project"):
        assert token in section, f"precedence token {token!r} is missing"
    assert "every call" in section
    assert "no restart" in section
    # Free models can now be explicitly denied, and a concrete example exists.
    assert "free models" in section.lower()
    assert "deny" in section.lower()
    assert "openrouter/deepseek/deepseek-chat" in section, "allow example is missing"
    assert "opencode-go" in section, "denied-provider example is missing"
    assert "subagent_models" in section
    assert "Desktop" in section
    assert "gui" not in section.lower()


def test_no_command_references_in_docs() -> None:
    for name in COMMAND_FREE_DOCS:
        text = _read(name)
        for marker in COMMAND_MARKERS:
            assert marker not in text, f"{name} still contains the command reference {marker!r}"
        assert re.search(r"/subagent-[a-z-]+", text) is None, (
            f"{name} still contains a slash-command id"
        )


def test_contributing_required_content() -> None:
    contributing = _read("CONTRIBUTING.md")
    for snippet in ("opencode/", "npm run build", "pytest", "untested", *RUNNERS):
        assert snippet in contributing, f"CONTRIBUTING.md is missing {snippet!r}"
    assert "another agent" not in contributing.lower()


def test_gitignore_required_rules() -> None:
    ignored = _read(".gitignore")
    for rule in ("node_modules/", "dist/", ".venv/", "__pycache__/"):
        assert rule in ignored, f".gitignore is missing {rule!r}"


_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://[^\s)>]+")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _prose(text: str) -> str:
    """Remove technical contexts (fences, inline code, URLs, comments)."""
    text = _HTML_COMMENT.sub("", text)
    text = _FENCE.sub("", text)
    text = _INLINE_CODE.sub("", text)
    return _URL.sub("", text)


def test_readme_first_heading_uses_display_name() -> None:
    non_blank = [line for line in _read("README.md").splitlines() if line.strip()]
    assert len(non_blank) >= 6
    # The five badge lines come first, so the H1 is the sixth non-blank line.
    assert non_blank[5] == f"# {DISPLAY}", "README H1 must be the branded display name"
    assert DISPLAY in "\n".join(non_blank[:20])


def test_readme_intro_and_configuration_use_display_name() -> None:
    readme = _read("README.md")
    assert f"**{DISPLAY}** is an OpenCode plugin" in readme
    section = _section(readme, "Configuration")
    assert f"**{DISPLAY}**" in section, "Configuration section must use the display name"


def test_readme_has_codex_support_section() -> None:
    section = _section(_read("README.md"), "Codex support")
    assert "codex/" in section, "Codex support must document the codex/ package"
    assert "0.153.4" in section, "Codex support must pin the supported CLI version"
    assert "no Codex subscription is required" in section


def test_contributing_structure_is_config_only() -> None:
    contributing = _read("CONTRIBUTING.md")
    for snippet in ("universal/", "adapters/opencode_cli/", "index.ts", "rpc.ts"):
        assert snippet in contributing, f"CONTRIBUTING structure is missing {snippet!r}"
    for stale in ("tui/", "gui.tsx", "command_ids", "commands.ts", "SolidJS", "Vite 7"):
        assert stale not in contributing, f"CONTRIBUTING still describes {stale!r}"


def test_contributing_uses_display_name() -> None:
    assert DISPLAY in _read("CONTRIBUTING.md")


def test_technical_id_confined_to_technical_contexts() -> None:
    for name in ("README.md", "CONTRIBUTING.md"):
        prose = _prose(_read(name))
        # Non-vacuous: the retained prose must still carry the branded copy.
        assert DISPLAY in prose, f"{name} prose lost the display name while stripping"
        assert TECHNICAL not in prose, (
            f"{name} prose must use '{DISPLAY}', not the technical id '{TECHNICAL}'"
        )


def test_readme_future_plans_section() -> None:
    readme = _read("README.md")
    assert "## Future plans" in readme, "README must have a dedicated Future plans section"
    section = readme.split("## Future plans", 1)[1].split("\n## ", 1)[0]
    for snippet in (
        "**Codex**",
        "**Claude Code**",
        "**Antigravity**",
        "**Other agents**",
        "And much more.",
    ):
        assert snippet in section, f"Future plans section is missing {snippet!r}"
    assert section.strip().endswith("And much more."), (
        "And much more. must close the Future plans section"
    )


def test_readme_reporting_and_feature_sections_link_templates() -> None:
    readme = _read("README.md")
    assert "## Reporting issues and requesting features" not in readme
    assert "## Reporting issues" in readme, "README must split out bug reporting"
    assert "## Requesting features" in readme, "README must split out feature requests"
    reporting = readme.split("## Reporting issues", 1)[1].split("\n## ", 1)[0]
    features = readme.split("## Requesting features", 1)[1].split("\n## ", 1)[0]
    assert BUG_TEMPLATE in reporting, "Reporting issues must link the bug template"
    assert ENCHANTMENT_TEMPLATE in features, "Requesting features must link the feature template"
    for text, label in ((reporting, "Reporting issues"), (features, "Requesting features")):
        assert "AI" in text, f"{label} must mention the AI disclosure"
        assert "model" in text, f"{label} must mention the model field"


def test_contributing_node_floor_and_wsl_block_removed() -> None:
    contributing = _read("CONTRIBUTING.md")
    assert "Node.js 22.0.0 is the minimum required version" in contributing, (
        "CONTRIBUTING must state the Node.js 22.0.0 minimum"
    )
    for removed in (
        "Optional Linux verification",
        "Windows Subsystem for Linux",
        "compatibility layer",
        "runs natively on Linux, macOS, and Windows",
    ):
        assert removed not in contributing, f"CONTRIBUTING still contains {removed!r}"
    assert "Semantic Versioning" in contributing, "SemVer guidance must be retained"
    assert "untested" in contributing
    assert "`main`" in contributing


def test_contributing_references_new_templates() -> None:
    contributing = _read("CONTRIBUTING.md")
    for token in (
        BUG_TEMPLATE,
        ENCHANTMENT_TEMPLATE,
        PR_TEMPLATE,
        PR_TEMPLATE_AUTO,
    ):
        assert token in contributing, f"CONTRIBUTING must reference {token!r}"


def _assert_ai_disclosure(text: str) -> None:
    assert "## AI disclosure (mandatory)" in text, "mandatory AI disclosure heading is missing"
    assert "- [ ] No AI was used" in text, "AI disclosure needs the No checkbox"
    assert "- [ ] AI was used" in text, "AI disclosure needs the Yes checkbox"
    assert "**AI model(s) used**" in text, "AI disclosure needs the model field"


def test_bug_report_template_contract() -> None:
    bug = _read(BUG_TEMPLATE)
    assert "name: Bug report" in bug
    assert 'title: "[Bug]: "' in bug
    assert "labels: bug, triage" in bug
    for section in (
        "## Steps to reproduce",
        "## Expected behavior",
        "## Actual behavior",
        "## Environment",
        "## Logs and screenshots",
    ):
        assert section in bug, f"Bug template is missing {section!r}"
    for field in (
        "Node.js version",
        "OpenCode version",
        "Operating system",
        "Plugin version",
    ):
        assert field in bug, f"Bug template environment is missing {field!r}"
    _assert_ai_disclosure(bug)


def test_feature_templates_are_identical_and_valid() -> None:
    enchantment = _read(ENCHANTMENT_TEMPLATE)
    enhancement = _read(ENHANCEMENT_TEMPLATE)
    assert enchantment == enhancement, "both feature-template spellings must be byte-identical"
    assert "name: Enhancement / feature request" in enchantment
    assert 'title: "[Enhancement]: "' in enchantment
    assert "labels: enhancement, triage" in enchantment
    for section in (
        "## Problem / use case",
        "## Proposed solution",
        "## Alternatives considered",
        "## Who benefits",
    ):
        assert section in enchantment, f"Feature template is missing {section!r}"
    assert "benefit" in enchantment.lower(), "Feature template must cover benefits"
    _assert_ai_disclosure(enchantment)


def test_pr_templates_are_identical_and_valid() -> None:
    canonical = _read(PR_TEMPLATE)
    auto = _read(PR_TEMPLATE_AUTO)
    assert canonical == auto, "PR_TEMPLATE.md and .github/pull_request_template.md must match"
    for section in (
        "## Related issue",
        "## What changed",
        "## How verified",
        "## Checklist",
    ):
        assert section in canonical, f"PR template is missing {section!r}"
    assert "draft this pull request description or its changes" in canonical
    _assert_ai_disclosure(canonical)


PLACEHOLDER_AGENTS = ("cline", "antigravity", "claudecode", "cursor")


def test_placeholder_agent_folders_are_code_free() -> None:
    for name in PLACEHOLDER_AGENTS:
        folder = REPO_ROOT / name
        assert folder.is_dir(), f"missing placeholder folder: {name}"
        entries = sorted(path.name for path in folder.iterdir())
        assert entries == [".gitkeep"], f"{name} must contain only .gitkeep, found {entries}"
        assert (folder / ".gitkeep").stat().st_size == 0, f"{name}/.gitkeep must be zero bytes"


def test_contributing_describes_repo_root_universal_core() -> None:
    contributing = _read("CONTRIBUTING.md")
    assert "├── universal/" in contributing, "repo-root universal/ tree entry is missing"
    assert "opencode/src/universal/" not in contributing, (
        "universal core is still described as living inside opencode/"
    )
    assert "reserved" in contributing.lower(), (
        "placeholder folders must be described as reservations"
    )
    for name in PLACEHOLDER_AGENTS:
        assert name in contributing, f"CONTRIBUTING must mention reserved folder {name!r}"


def test_readme_placeholder_note_is_non_committal() -> None:
    section = _section(_read("README.md"), "Future plans")
    assert "reserved" in section.lower(), (
        "Future plans must note that folders are reserved placeholders"
    )
    assert "no support" in section.lower(), "Future plans must state that no support is implied"
    for name in ("Cline", "Cursor"):
        assert name in section, f"Future plans must name {name}"


def test_readme_removes_gui_from_prose() -> None:
    readme = _read("README.md")
    # The word survives only as a bare Future plans bullet, never in prose.
    prose = readme.replace(_section(readme, "Future plans"), "")
    assert "gui" not in prose.lower(), "README prose must not mention GUI"


def test_readme_future_plans_lists_gui_bullet() -> None:
    section = _section(_read("README.md"), "Future plans")
    assert re.search(r"^- GUI,$", section, re.MULTILINE) is not None, (
        "Future plans must contain a bare '- GUI,' bullet"
    )


def test_release_template_has_required_sections_and_placeholders() -> None:
    template = _read(RELEASE_TEMPLATE)
    assert template.lstrip().startswith("<!--"), "template must open with a usage comment"
    for heading in (
        "## What's changed",
        "## New contributors",
        "## Tested with",
        "## Build toolchain",
        "## Full changelog",
    ):
        assert heading in template, f"release template is missing {heading!r}"
    for marker in (
        "{{CHANGES}}",
        "{{CONTRIBUTORS}}",
        "{{APP_VERSION}}",
        "{{CLI_VERSION}}",
        "{{NODE_VERSION}}",
        "{{TYPESCRIPT_VERSION}}",
        "{{FULL_CHANGELOG}}",
    ):
        assert marker in template, f"release template is missing {marker!r}"


def test_publish_workflow_generates_release_body_from_template() -> None:
    workflow = _read(PUBLISH_WORKFLOW)
    assert "tags: ['v*', '[0-9]*']" in workflow, "tag trigger must accept plain SemVer tags"
    assert re.search(r"^permissions:\s*\{\}", workflow, re.MULTILINE) is not None
    assert "id-token: write" not in workflow, "OIDC trusted publishing must stay removed"
    assert "NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}" in workflow, (
        "the publish step must authenticate with the NPM_TOKEN repository secret"
    )
    assert "npm install --global" not in workflow, "global npm installs must stay removed"
    assert "npm publish --access public" in workflow, "public npm publish must be retained"
    release = workflow.split("  create-github-release:", 1)[1].split("\n  on-failure:", 1)[0]
    assert "if: github.event_name == 'push'" in release
    assert "contents: write" in release, "creating a release needs contents: write"
    assert "release-template.md" in release
    assert "generate-notes" in release, "GitHub's generated notes must be used"
    assert "--notes-file" in release
    for action in re.findall(r"^\s+uses:\s*(\S+)", workflow, re.MULTILINE):
        assert re.search(r"@[0-9a-f]{40}$", action), f"action is not SHA-pinned: {action}"
