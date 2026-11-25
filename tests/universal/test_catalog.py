"""Catalog building with injected free-provider facts.

The universal catalog must not know which providers ship free models from any
particular host. The classification is driven entirely by `CatalogConfig`,
supplied by the adapter, so a future agent can classify its own providers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_MODULE = "opencode/dist/universal/domain/catalog.js"

HARNESS = """
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const mod = await import(pathToFileURL(resolve(process.argv[2])).href);
const raw = {
  id: "m1", modelID: "m1", providerID: "mystery", name: "Mystery",
  variants: [{ id: "low", settings: {} }],
  cost: [{ input: 0 }], enabled: true,
};
const noCost = { ...raw, cost: [] };
const paid = { ...raw, providerID: "paid", cost: [{ input: 5 }] };
const cfgMystery = { builtInFreeProviders: ["mystery"] };
const cfgOpenCode = { builtInFreeProviders: ["opencode", "opencode-go"] };

const out = {};
out.injectedFree = mod.isBuiltInFree(raw, cfgMystery);
out.notInjectedFree = mod.isBuiltInFree(raw, cfgOpenCode);
out.emptyCostNeverFree = mod.isBuiltInFree(noCost, cfgMystery);
out.paidNeverFree = mod.isBuiltInFree(paid, cfgMystery);
out.descriptor = mod.toModelDescriptor(raw, "Mystery Provider", cfgMystery);
out.catalog = mod.buildCatalog([raw, paid], [{ id: "mystery", name: "Mystery" }], cfgMystery);
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.universal
def test_free_provider_set_is_injected_not_hardcoded(run_node) -> None:
    result = run_node(HARNESS, CATALOG_MODULE)
    assert result["injectedFree"] is True
    assert result["notInjectedFree"] is False
    assert result["emptyCostNeverFree"] is False
    assert result["paidNeverFree"] is False
    assert result["descriptor"]["isFree"] is True
    assert result["descriptor"]["selector"] == "mystery/m1"
    assert [model["selector"] for model in result["catalog"]["models"]] == [
        "mystery/m1",
        "paid/m1",
    ]
    assert result["catalog"]["models"][1]["isFree"] is False


@pytest.mark.universal
def test_no_host_provider_id_is_hardcoded_in_universal() -> None:
    universal = REPO_ROOT / "universal"
    assert universal.is_dir(), "universal source tree is missing"
    leaks: list[str] = []
    for path in sorted(universal.rglob("*.ts")) + sorted(universal.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        if "opencode-go" in text:
            leaks.append(str(path.relative_to(REPO_ROOT)))
    assert leaks == [], f"host provider id leaked into universal core: {leaks}"
