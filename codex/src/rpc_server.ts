/**
 * In-process server side of the frozen `subagent-models` contract. There is no
 * Codex RPC host to register with, so the three API methods and two event
 * subscriptions are exposed directly on a plain object.
 */

import type {
  GetCatalogOutput,
  GetPolicyInput,
  GetPolicyOutput,
  SetPolicyInput,
  SetPolicyOutput,
  ScopeName,
} from "#universal/domain/types";
import {
  RPC_EVENT_NAMES,
  RPC_METHOD_NAMES,
  SUBAGENT_MODELS_CONTRACT,
  type RpcContract,
  type RpcEventPort,
  type SubagentModelsApi,
} from "#universal/rpc/contract";

import type { CodexAdapter } from "./server.js";

export interface CodexRpcServer extends SubagentModelsApi, RpcEventPort {
  readonly contract: RpcContract;
  readonly methods: readonly string[];
  readonly events: readonly string[];
  dispose(): Promise<void>;
}

/** Create the RPC surface and forward adapter events to its subscribers. */
export function createCodexRpc(adapter: CodexAdapter): CodexRpcServer {
  const catalogHandlers = new Set<() => void>();
  const policyHandlers = new Set<(scope: ScopeName) => void>();

  const unsubscribe = adapter.subscribe((event) => {
    if (event.type === "catalog.updated") {
      for (const handler of catalogHandlers) handler();
    } else if (event.type === "policy.updated") {
      for (const handler of policyHandlers) handler(event.scope);
    }
  });

  return {
    contract: SUBAGENT_MODELS_CONTRACT,
    methods: RPC_METHOD_NAMES,
    events: RPC_EVENT_NAMES,

    async get_catalog(): Promise<GetCatalogOutput> {
      return { catalog: await adapter.getCatalog() };
    },
    async get_policy(input: GetPolicyInput): Promise<GetPolicyOutput> {
      return { rule: await adapter.getPolicy(input.scope) };
    },
    async set_policy(input: SetPolicyInput): Promise<SetPolicyOutput> {
      await adapter.setPolicy(input.scope, input.rule);
      return { rule: input.rule };
    },
    onCatalogUpdated(handler: () => void): () => void {
      catalogHandlers.add(handler);
      return () => {
        catalogHandlers.delete(handler);
      };
    },
    onPolicyUpdated(handler: (scope: ScopeName) => void): () => void {
      policyHandlers.add(handler);
      return () => {
        policyHandlers.delete(handler);
      };
    },
    async dispose(): Promise<void> {
      unsubscribe();
      catalogHandlers.clear();
      policyHandlers.clear();
    },
  };
}
