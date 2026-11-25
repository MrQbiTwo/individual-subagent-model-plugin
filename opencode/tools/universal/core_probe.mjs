// JSON probe for the compiled core.
//
// Reads one JSON object from stdin: {"op": "<name>", "args": { ... }}.
// Dispatches to compiled modules in ../dist/, then prints either
// {"result": <value>} or {"error": {"code": ..., "message": ...}} and exits 0.
// It never imports @opencode/*, so it runs with only the compiled core present.
// Operation output shapes are part of the test contract and stay stable.

const distUrl = (relativePath) => new URL(`../../dist/${relativePath}`, import.meta.url).href;
const importDist = (relativePath) => import(distUrl(relativePath));

/** Read and JSON-decode the single request object written to stdin. */
async function readRequest() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString("utf8").trim();
  return text ? JSON.parse(text) : {};
}

// Last-run listener count, exposed on request for the event-refresh test.
let lastListenerCalls = 0;

const OPS = {
  parse_selector: async (args) => {
    const { parseModelSelector } = await importDist("universal/domain/selector.js");
    return parseModelSelector(args.input);
  },

  build_catalog: async (args) => {
    const { buildCatalog } = await importDist("universal/domain/catalog.js");
    const { OPENCODE_CATALOG_CONFIG } = await importDist(
      "adapters/opencode_cli/opencode_free_providers.js",
    );
    return buildCatalog(args.models, args.providers, args.config ?? OPENCODE_CATALOG_CONFIG);
  },

  find_by_selector: async (args) => {
    const { findBySelector } = await importDist("universal/domain/catalog.js");
    return findBySelector(args.catalog, args.selector) ?? null;
  },

  // Verifies that an empty-data invalidation event triggers exactly one
  // committed refresh. The fake host grows its catalog on every modelList()
  // call, so the two returned counts are 1 (initial) and 2 (after the event).
  service_refresh_sequence: async (args) => {
    const { createModelService } = await importDist("universal/services/catalog_service.js");
    const { OPENCODE_CATALOG_CONFIG } = await importDist(
      "adapters/opencode_cli/opencode_free_providers.js",
    );
    let callCount = 0;
    let emitEvent = () => {};

    const provider = {
      async listModels() {
        callCount += 1;
        return Array.from({ length: callCount }, (_, index) => ({
          id: `m${callCount}_${index}`,
          modelID: `model-${index}`,
          providerID: "opencode",
          name: `Model ${index}`,
          variants: [],
          cost: [{ input: 0 }],
          enabled: true,
        }));
      },
      async listProviders() {
        return [{ id: "opencode", name: "OpenCode" }];
      },
      async subscribeInvalidation(handler) {
        // The real events carry empty data; pass the same shape here.
        emitEvent = () => handler({ data: {} });
        return () => {};
      },
    };

    lastListenerCalls = 0;
    const service = await createModelService(
      provider,
      undefined,
      args.config ?? OPENCODE_CATALOG_CONFIG,
    );
    service.subscribe(() => {
      lastListenerCalls += 1;
    });
    const first = service.current().models.length;

    emitEvent();
    // Let the detached, guard-protected refresh settle before reading state.
    for (let attempt = 0; attempt < 50 && service.current().models.length === first; attempt += 1) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    const after = service.current().models.length;
    await service.dispose();

    // Returns the catalog sizes before and after the refresh; an explicit
    // flag also includes the listener count.
    return args.includeListenerCount ? [first, after, lastListenerCalls] : [first, after];
  },

  service_listener_calls: async () => lastListenerCalls,

  // Policy decision. With `rule` this calls decide(); with `global`
  // and `project` it calls decideWithScopes() so both reason sets are testable.
  decide: async (args) => {
    const policy = await importDist("universal/domain/policy.js");
    if (args.global && args.project) {
      return policy.decideWithScopes(args.model, args.global, args.project);
    }
    return policy.decide(args.model, args.rule);
  },

  // Pure allowlist mutation. `mutation` is the normal shape; a bare
  // `kind` plus fields is also accepted for compact test fixtures.
  apply_mutation: async (args) => {
    const { applyRuleMutation } = await importDist("universal/domain/policy.js");
    const mutation = args.mutation ?? (({ kind, ...rest }) => ({ kind, ...rest }))(args);
    return applyRuleMutation(args.rule, mutation);
  },

  // Config validation. Accepts raw text or a config object to stringify.
  parse_config: async (args) => {
    const { parsePluginConfig } = await importDist("universal/domain/config.js");
    const text = typeof args.text === "string" ? args.text : JSON.stringify(args.config);
    return parsePluginConfig(text);
  },

  // Pretty-printed, newline-terminated config serialization.
  serialize_config: async (args) => {
    const { serializePluginConfig } = await importDist("universal/domain/config.js");
    return serializePluginConfig(args.config);
  },

  // Workspace-id sanitization used for project config file names.
  project_key: async (args) => {
    const { projectKey } = await importDist("universal/domain/config.js");
    return projectKey(args.workspaceID);
  },

  // Subagent model route selection. Returns null when no route exists.
  resolve_route: async (args) => {
    const { resolveSubagentRoute } = await importDist("universal/domain/routing.js");
    // JSON fixtures may carry an explicit null/empty model; treat both as absent.
    const input = { ...args.input };
    if (input.model === null || input.model === "") {
      delete input.model;
    }
    return (
      resolveSubagentRoute(
        input,
        args.catalog,
        args.global,
        args.project,
        args.parentModel,
      ) ?? null
    );
  },

  // Compact permitted-model note injected into the primary model's context.
  catalog_note: async (args) => {
    const { buildCatalogNote } = await importDist("universal/domain/routing.js");
    return buildCatalogNote(args.catalog, args.global, args.project);
  },
};

try {
  const request = await readRequest();
  const handler = OPS[request.op];
  if (!handler) {
    const error = new Error(`Unknown op: ${String(request.op)}`);
    error.code = "unknown-op";
    throw error;
  }
  const result = await handler(request.args ?? {});
  process.stdout.write(JSON.stringify({ result }));
} catch (error) {
  process.stdout.write(
    JSON.stringify({
      error: {
        code: error?.code ?? "probe-error",
        message: error?.message ?? String(error),
      },
    }),
  );
}
