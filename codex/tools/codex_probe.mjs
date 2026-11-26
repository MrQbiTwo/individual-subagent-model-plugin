// JSON-only probe for the compiled Codex adapter.
//
// Usage: node tools/codex_probe.mjs <case> [fixturePath]
// Every case writes exactly one JSON value to stdout and nothing else. The
// module under test is always the compiled code in ../dist, so the probe also
// doubles as a check that the two TypeScript build passes produced a usable
// package.

import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

const distUrl = (relativePath) => new URL(`../dist/${relativePath}`, import.meta.url).href;
const importDist = (relativePath) => import(distUrl(relativePath));

const emit = (value) => process.stdout.write(JSON.stringify(value));

const readText = async (fixturePath) => {
  if (!fixturePath) throw new Error("fixturePath is required for this case");
  return readFile(fixturePath, "utf8");
};

/** Return the stable code of a CodexError, or a marker when no error was thrown. */
const caughtCode = async (fn) => {
  try {
    await fn();
    return "NO_ERROR";
  } catch (error) {
    return error?.code ?? "NO_CODE";
  }
};

const CASE_RESERVED = {
  id: "openai",
  name: "Should Fail",
  baseUrl: "https://example.invalid/v1",
  envKey: "EXAMPLE_KEY",
};

const CASES = {
  async contract() {
    const contract = await importDist("universal/rpc/contract.js");
    return {
      namespace: contract.RPC_NAMESPACE,
      methods: [...contract.RPC_METHOD_NAMES],
      events: [...contract.RPC_EVENT_NAMES],
    };
  },

  async "reserved-provider"() {
    const { buildProvider } = await importDist("providers.js");
    return caughtCode(() => buildProvider(CASE_RESERVED));
  },

  async "chat-wire-api"() {
    const { buildProvider } = await importDist("providers.js");
    return caughtCode(() =>
      buildProvider({
        id: "myrouter",
        baseUrl: "https://example.invalid/v1",
        wireApi: "chat",
      }),
    );
  },

  async "secret-env-key"() {
    const { buildProvider } = await importDist("providers.js");
    return caughtCode(() =>
      buildProvider({
        id: "myrouter",
        baseUrl: "https://example.invalid/v1",
        envKey: "sk-1234567890abcdef",
      }),
    );
  },

  async "auth-env-conflict"() {
    const { buildProvider } = await importDist("providers.js");
    return caughtCode(() =>
      buildProvider({
        id: "myrouter",
        baseUrl: "https://example.invalid/v1",
        envKey: "MY_ROUTER_KEY",
        auth: { command: "/bin/get-token" },
      }),
    );
  },

  async "aws-custom"() {
    const { buildProvider } = await importDist("providers.js");
    return caughtCode(() =>
      buildProvider({
        id: "myrouter",
        baseUrl: "https://example.invalid/v1",
        aws: { region: "us-east-1" },
      }),
    );
  },

  async "unsupported-key"() {
    const { buildProvider } = await importDist("providers.js");
    return caughtCode(() =>
      buildProvider({
        id: "myrouter",
        baseUrl: "https://example.invalid/v1",
        extra: { model_catalog_url: "https://example.invalid/catalog.json" },
      }),
    );
  },

  async "toml-roundtrip"(fixturePath) {
    const { parseConfig, serializeConfig } = await importDist("config.js");
    const text = await readText(fixturePath);
    const serialized = serializeConfig(parseConfig(text));
    return parseConfig(serialized);
  },

  async "misplaced-model"(fixturePath) {
    const { findMisplacedModelKey } = await importDist("config.js");
    return findMisplacedModelKey(await readText(fixturePath)) ?? null;
  },

  async "exec-args"() {
    const { buildExecArgs } = await importDist("argv.js");
    return buildExecArgs({
      model: "my-model",
      providerId: "myrouter",
      json: true,
      prompt: "hi",
    });
  },

  async catalog(fixturePath) {
    const { parseBundledCatalog } = await importDist("catalog.js");
    return parseBundledCatalog(await readText(fixturePath));
  },

  async route(fixturePath) {
    const { resolveRoute } = await importDist("policy.js");
    const fixture = fixturePath
      ? JSON.parse(await readText(fixturePath))
      : {
          requestedModel: "myrouter/child",
          requestedProvider: "myrouter",
          parentModel: { providerID: "myrouter", id: "parent" },
          effort: "low",
          allowlist: { models: [], providers: ["myrouter"], agentDefaults: {} },
          catalog: {
            generatedAt: 0,
            providers: [{ id: "myrouter", name: "My Router", models: [] }],
            models: [
              {
                id: "child",
                modelID: "child",
                providerID: "myrouter",
                providerName: "My Router",
                name: "Child",
                variants: [{ id: "low", settings: {} }],
                efforts: ["low"],
                enabled: true,
                isFree: false,
                selector: "myrouter/child",
              },
            ],
          },
        };
    return resolveRoute(fixture);
  },

  async jsonl(fixturePath) {
    const { parseExecJsonl, parseAppServerMessage } = await importDist("rpc.js");
    const text = (await readText(fixturePath)).trim();
    const lines = text.startsWith("[") ? JSON.parse(text) : text.split(/\r?\n/).filter(Boolean);
    const result = [];
    for (const line of lines) {
      if (typeof line !== "string" && typeof line !== "object") continue;
      const raw = typeof line === "string" ? line : JSON.stringify(line);
      const parsed = raw.includes('"method"') && !raw.includes('"type"')
        ? parseAppServerMessage(raw)
        : parseExecJsonl(raw);
      result.push(parsed.type ?? parsed.method ?? null);
    }
    return result;
  },

  async ports() {
    const { CodexCatalogProvider, CodexConfigStore } = await importDist("ports.js");
    const { CODEX_FREE_PROVIDERS } = await importDist("codex_free_providers.js");
    const provider = new CodexCatalogProvider({ config: {} });
    const models = await provider.listModels();
    const providers = await provider.listProviders();
    const store = new CodexConfigStore(path.join(tmpdir(), `codex-probe-${process.pid}`));
    const rule = await store.read("global");
    const unsubscribe = await provider.subscribeInvalidation(() => {});
    unsubscribe();
    if (!Array.isArray(models) || !Array.isArray(providers) || !rule || !Array.isArray(rule.models)) {
      throw new Error("port instances failed verification");
    }
    return {
      catalogProvider: true,
      configStore: true,
      freeProviders: CODEX_FREE_PROVIDERS,
    };
  },
};

const [caseName, fixturePath] = process.argv.slice(2);
try {
  const handler = caseName ? CASES[caseName] : undefined;
  if (!handler) throw new Error(`Unknown case: ${String(caseName)}`);
  emit(await handler(fixturePath));
} catch (error) {
  emit({ error: { code: error?.code ?? "probe-error", message: error?.message ?? String(error) } });
}
