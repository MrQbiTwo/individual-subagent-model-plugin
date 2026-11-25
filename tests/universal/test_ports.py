"""Universal-core purity guard.

The universal core must stay host-free: it may not import any OpenCode SDK,
SolidJS/OpenTUI runtime, or Node built-in module.  A third agent must be able
to add an adapter folder without any core file changing.  This test walks both
the TypeScript source and the compiled JavaScript so a stale `dist/` cannot
hide a leak.

Behaviour of the contract itself is pinned by asserting the wire-stable RPC
identifiers survive compilation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIVERSAL_SRC = REPO_ROOT / "universal"
UNIVERSAL_DIST = REPO_ROOT / "opencode" / "dist" / "universal"

CONTRACT_FILES = (
    "ports.ts",
    "rpc/contract.ts",
    "events.ts",
)

# Import forms that would bind the core to a specific host runtime.
FORBIDDEN_SOURCE = re.compile(
    r"""(?x)
      from\s+["'](?:@opencode/|solid-js|@opentui/|node:)
    | import\s*\(\s*["'](?:@opencode/|solid-js|@opentui/|node:)
    | import\s+["'](?:@opencode/|solid-js|@opentui/|node:)
    """
)
FORBIDDEN_COMPILED = re.compile(
    r"""(?x)
      (?:require|from)\s*\(?\s*["'](?:@opencode/|solid-js|@opentui/|node:)
    | import\s*\(\s*["'](?:@opencode/|solid-js|@opentui/|node:)
    """
)


@pytest.mark.universal
def test_contract_files_exist() -> None:
    for relative in CONTRACT_FILES:
        path = UNIVERSAL_SRC / relative
        assert path.is_file(), f"missing universal contract file: {path}"


@pytest.mark.universal
def test_universal_source_is_host_free() -> None:
    assert UNIVERSAL_SRC.is_dir(), "universal source tree is missing"
    sources = sorted(UNIVERSAL_SRC.rglob("*.ts")) + sorted(UNIVERSAL_SRC.rglob("*.tsx"))
    assert sources, "no universal TypeScript files found"
    leaks: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_SOURCE.search(line):
                leaks.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")
    assert leaks == [], "host import leaked into universal core:\n" + "\n".join(leaks)


@pytest.mark.universal
def test_compiled_universal_is_host_free() -> None:
    assert UNIVERSAL_DIST.is_dir(), (
        "compiled universal tree is missing (run npm run build --prefix opencode)"
    )
    sources = sorted(UNIVERSAL_DIST.rglob("*.js"))
    assert sources, "no compiled universal JavaScript found"
    leaks: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_COMPILED.search(line):
                leaks.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")
    assert leaks == [], "host import leaked into compiled universal core:\n" + "\n".join(leaks)


@pytest.mark.universal
def test_wire_constants_survive_compilation() -> None:
    contract = (UNIVERSAL_DIST / "rpc" / "contract.js").read_text(encoding="utf-8")
    assert '"subagent-models"' in contract
    assert '"get_catalog"' in contract
    assert '"get_policy"' in contract
    assert '"set_policy"' in contract
    assert '"catalog_updated"' in contract
    assert '"policy_updated"' in contract
