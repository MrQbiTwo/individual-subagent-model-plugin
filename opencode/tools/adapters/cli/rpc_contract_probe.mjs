// Pins the wire contract exposed by the OpenCode CLI RPC adapter. Every value
// comes from the compiled universal contract; the adapter source is checked
// only for the Rpc.define binding that cannot be observed at runtime here.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const contractUrl = pathToFileURL(
  path.join(root, "opencode", "dist", "universal", "rpc", "contract.js"),
).href;
const adapterSourcePath = path.join(
  root,
  "opencode",
  "dist",
  "adapters",
  "opencode_cli",
  "rpc.js",
);

const contract = await import(contractUrl);
const failures = [];
const check = (name, fn) => {
  try {
    fn();
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
  }
};

check("namespace is frozen", () =>
  assert.equal(contract.RPC_NAMESPACE, "subagent-models"));
check("method names are frozen and ordered", () =>
  assert.deepEqual([...contract.RPC_METHOD_NAMES], ["get_catalog", "get_policy", "set_policy"]));
check("event names are frozen and ordered", () =>
  assert.deepEqual([...contract.RPC_EVENT_NAMES], ["catalog_updated", "policy_updated"]));
check("contract object mirrors the constants", () => {
  assert.equal(contract.SUBAGENT_MODELS_CONTRACT.namespace, contract.RPC_NAMESPACE);
  assert.deepEqual(Object.keys(contract.SUBAGENT_MODELS_CONTRACT.methods), [
    ...contract.RPC_METHOD_NAMES,
  ]);
  assert.deepEqual(Object.keys(contract.SUBAGENT_MODELS_CONTRACT.events), [
    ...contract.RPC_EVENT_NAMES,
  ]);
});
check("HTTP path is unchanged", () =>
  assert.equal(
    `/api/rpc/${contract.RPC_NAMESPACE}/${contract.RPC_METHOD_NAMES[0]}`,
    "/api/rpc/subagent-models/get_catalog",
  ));
check("adapter binds the universal namespace into Rpc.define", () => {
  const source = fs.readFileSync(adapterSourcePath, "utf8");
  assert.match(source, /Rpc\.define\(/);
  assert.match(source, /RPC_NAMESPACE/);
  assert.match(source, /SUBAGENT_MODELS_CONTRACT/);
  for (const name of contract.RPC_METHOD_NAMES) {
    assert.match(source, new RegExp(`\\b${name}\\s*:`), `missing method ${name}`);
  }
  for (const name of contract.RPC_EVENT_NAMES) {
    assert.match(source, new RegExp(`\\b${name}\\s*:`), `missing event ${name}`);
  }
});

if (failures.length > 0) {
  console.log(JSON.stringify({ ok: false, failures }, null, 2));
  process.exit(1);
}
console.log(
  JSON.stringify({
    ok: true,
    namespace: contract.RPC_NAMESPACE,
    methods: [...contract.RPC_METHOD_NAMES],
    events: [...contract.RPC_EVENT_NAMES],
    http_path: `/api/rpc/${contract.RPC_NAMESPACE}/${contract.RPC_METHOD_NAMES[0]}`,
  }),
);
