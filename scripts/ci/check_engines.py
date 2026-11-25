"""Engine-policy helper shared by CI workflows and native runner scripts.

The plugin targets Node >= 22.0.0. OpenTUI peers may declare a higher floor,
but OpenCode 2.3.2 bundles a compatible runtime, so strict engine checks stay
disabled (see opencode/.npmrc). This helper makes that policy explicit and
reports *why* a given version combination passes or fails.
"""

import re


def _parse_version(value: str) -> tuple[int, ...]:
    """Return the first three numeric components of a version string.

    Non-numeric prefixes such as ``>=`` or ``v`` are ignored, which lets the
    same parser handle an installed version ("24.16.0") and a declared range
    (">=22.0.0"). Missing components are padded with zeros.
    """
    numbers = re.findall(r"\d+", value)[:3]
    parts = tuple(int(number) for number in numbers)
    return parts + (0,) * (3 - len(parts))


def evaluate(node_version: str, declared_engine: str, engine_strict: str) -> dict:
    """Evaluate whether an installed Node version satisfies the engine policy.

    Args:
        node_version: Installed Node version, e.g. ``"24.16.0"``.
        declared_engine: Declared engine range, e.g. ``">=22.0.0"``.
        engine_strict: ``"true"`` treats EBADENGINE as fatal, ``"false"`` relaxes it.

    Returns:
        ``{"ok": bool, "node": str, "reason": str}``. ``reason`` is one of
        ``"engine_ok"``, ``"node_below_floor"`` or ``"engine_strict_enabled"``.
    """
    node = _parse_version(node_version)
    floor = _parse_version(declared_engine)

    if engine_strict == "true":
        return {"ok": False, "node": node_version, "reason": "engine_strict_enabled"}
    if node < floor:
        return {"ok": False, "node": node_version, "reason": "node_below_floor"}
    return {"ok": True, "node": node_version, "reason": "engine_ok"}


def main() -> None:
    """CLI entry point used by scripts/run_tests.sh and run_tests.ps1."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate the Node engine policy.")
    parser.add_argument("node_version", help='Installed version, e.g. "24.16.0"')
    parser.add_argument("declared_engine", help='Declared range, e.g. ">=22.0.0"')
    parser.add_argument("engine_strict", help='"true" or "false"')
    args = parser.parse_args()

    result = evaluate(args.node_version, args.declared_engine, args.engine_strict)
    print(result["reason"])
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
