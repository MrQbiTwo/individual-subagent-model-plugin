"""Static pins for the repo-root universal source relocation.

The host-free core lives in the repo-root ``universal/`` folder; OpenCode code
stays under ``opencode/src/**``. Compiled output, probes and the published
package shape remain under ``opencode/`` (Plan A), so these guards deliberately
watch *source* roots and the single relocated CI path. They are pure/static and
xdist-safe: no server, no npm, no network.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Assembled from parts so this audit file does not match its own stale-path rule.
STALE_SOURCE = "opencode" + "/" + "src" + "/" + "universal"
RELOCATED_E2E = "tests/adapters/opencode_cli/e2e/test_config_file_control.py"
OLD_E2E = "tests/unit/test_config_file_control.py"

SCANNED_FILES = (
    *sorted((REPO_ROOT / "tests" / "universal").glob("*.py")),
    *sorted((REPO_ROOT / "tests" / "unit").glob("*.py")),
    *sorted((REPO_ROOT / "tests" / "adapters").rglob("*.py")),
    REPO_ROOT / "tests" / "conftest.py",
    *sorted((REPO_ROOT / "scripts" / "ci").glob("*.py")),
    REPO_ROOT / "scripts" / "run_tests.sh",
    REPO_ROOT / "scripts" / "run_tests.ps1",
    *sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")),
)
# test_docs.py is owned by the docs agent and asserts the old path negatively.
OWNED_BY_DOCS_AGENT = {"test_docs.py"}


def _owned_files() -> list[Path]:
    return [path for path in SCANNED_FILES if path.name not in OWNED_BY_DOCS_AGENT]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_no_stale_universal_source_paths_in_tests_ci_or_runners() -> None:
    hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}"
        for path in _owned_files()
        if STALE_SOURCE in _text(path)
    ]
    assert hits == [], f"stale universal source path in test/CI files: {hits}"


def test_universal_source_roots_point_at_repo_root() -> None:
    ports = _text(REPO_ROOT / "tests" / "universal" / "test_ports.py")
    catalog = _text(REPO_ROOT / "tests" / "universal" / "test_catalog.py")
    no_commands = _text(REPO_ROOT / "tests" / "unit" / "test_no_command_registrations.py")
    gui = _text(
        REPO_ROOT
        / "tests"
        / "adapters"
        / "opencode_desktop"
        / "contract"
        / "test_gui_plugin_contract.py"
    )
    assert 'UNIVERSAL_SRC = REPO_ROOT / "universal"' in ports
    assert 'universal = REPO_ROOT / "universal"' in catalog
    assert 'UNIVERSAL = REPO_ROOT / "universal"' in no_commands
    assert '"universal/ui"' in gui


def test_checker_scans_the_repo_root_universal_source() -> None:
    checker = _text(REPO_ROOT / "scripts" / "ci" / "check_no_commands.py")
    assert 'UNIVERSAL = REPO_ROOT / "universal"' in checker
    assert "_scan_text_files(UNIVERSAL, SOURCE_SUFFIXES, matches)" in checker


def test_config_file_control_e2e_lives_under_the_adapter() -> None:
    assert (REPO_ROOT / RELOCATED_E2E).is_file(), f"missing relocated E2E: {RELOCATED_E2E}"
    assert not (REPO_ROOT / OLD_E2E).exists(), f"old E2E path survived: {OLD_E2E}"


def test_ci_pins_the_relocated_config_file_control_e2e() -> None:
    ci = _text(REPO_ROOT / ".github" / "workflows" / "ci.yml")
    assert RELOCATED_E2E in ci, "config-file control E2E is not invoked at its adapter path"
    assert OLD_E2E not in ci, "workflow still invokes the pre-move E2E path"
