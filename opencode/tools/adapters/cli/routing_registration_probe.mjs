// Drives the compiled OpenCode CLI routing adapter with a fake host context and
// asserts the four registration points plus the mutable subagent model input.
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const modulePath = path.join(
  process.cwd(),
  "opencode",
  "dist",
  "adapters",
  "opencode_cli",
  "routing.js",
);
const { registerRouting } = await import(pathToFileURL(modulePath).href);

const failures = [];
const check = async (name, fn) => {
  try {
    await fn();
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
  }
};

const calls = { registrations: [], reloads: [], hooks: {} };
const editor = { add: (value) => calls.registrations.push(["tool.add", value]) };
const ctx = {
  tool: {
    transform: async (fn) => {
      fn(editor);
      calls.registrations.push(["tool.transform"]);
      return { dispose: async () => {} };
    },
    reload: async () => {
      calls.reloads.push("tool");
    },
    hook: async (event, fn) => {
      calls.hooks[event] = fn;
      calls.registrations.push(["tool.hook", event]);
      return { dispose: async () => {} };
    },
  },
  session: {
    hook: async (event, fn) => {
      calls.hooks[`session.${event}`] = fn;
      calls.registrations.push(["session.hook", event]);
      return { dispose: async () => {} };
    },
    get: async () => ({ model: { providerID: "openai", id: "gpt" } }),
  },
  agent: {
    transform: async () => {
      calls.registrations.push(["agent.transform"]);
      return { dispose: async () => {} };
    },
    reload: async () => {
      calls.reloads.push("agent");
    },
  },
};

const model = {
  id: "beam-free",
  modelID: "beam-free",
  providerID: "opencode",
  providerName: "OpenCode",
  name: "Beam Free",
  variants: [],
  efforts: ["high"],
  enabled: true,
  isFree: true,
  selector: "opencode/beam-free",
};
const rule = { models: [], providers: [], agentDefaults: {} };
const deps = {
  modelService: {
    current: () => ({ generatedAt: 0, providers: [], models: [model] }),
  },
  configStore: {
    read: async () => rule,
  },
  projectKey: "probe",
  emit: async () => {},
};

let handle;
try {
  handle = await registerRouting(ctx, deps);
} catch (error) {
  failures.push(`registerRouting threw: ${error.message}`);
}

await check("discovery tool added", () =>
  assert.ok(calls.registrations.some(([kind]) => kind === "tool.add")));
await check("four registration points", () =>
  assert.deepEqual(
    calls.registrations.map(([kind]) => kind).sort(),
    ["agent.transform", "session.hook", "tool.add", "tool.hook", "tool.transform"],
  ));
await check("tool and agent reloads happen", () =>
  assert.deepEqual(calls.reloads.sort(), ["agent", "tool"]));
await check("session context hook is registered", () =>
  assert.equal(typeof calls.hooks["session.context"], "function"));
await check("execute.before mutates subagent input in place", async () => {
  const hook = calls.hooks["execute.before"];
  assert.equal(typeof hook, "function");
  const input = { agent: "general", description: "d", prompt: "p", model: "openai/gpt" };
  await hook({ tool: "subagent", input, sessionID: "s" });
  assert.equal(input.model, "opencode/beam-free#high");
});
await check("non-subagent tool is untouched", async () => {
  const hook = calls.hooks["execute.before"];
  const input = { agent: "general", description: "d", prompt: "p", model: "openai/gpt" };
  await hook({ tool: "other", input, sessionID: "s" });
  assert.equal(input.model, "openai/gpt");
});
await check("disposer is available", () => assert.equal(typeof handle?.dispose, "function"));

if (handle) {
  try {
    await handle.dispose();
  } catch (error) {
    failures.push(`dispose threw: ${error.message}`);
  }
}

if (failures.length > 0) {
  console.log(JSON.stringify({ ok: false, failures }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, registrations: calls.registrations.length }));
