/**
 * Wire-stable RPC contract: names, IO types and JSON-schema-shaped descriptors.
 *
 * This file never calls `Rpc.define`; adapters build the concrete transport
 * object from these host-neutral descriptors. The namespace and method names
 * are frozen because they determine the HTTP path
 * `/api/rpc/subagent-models/<method>`.
 */

import type {
  GetCatalogInput,
  GetCatalogOutput,
  GetPolicyInput,
  GetPolicyOutput,
  ScopeName,
  SetPolicyInput,
  SetPolicyOutput,
} from "../domain/types.js";

export const RPC_NAMESPACE = "subagent-models" as const;
export const RPC_METHOD_NAMES = ["get_catalog", "get_policy", "set_policy"] as const;
export type RpcMethodName = (typeof RPC_METHOD_NAMES)[number];
export const RPC_EVENT_NAMES = ["catalog_updated", "policy_updated"] as const;
export type RpcEventName = (typeof RPC_EVENT_NAMES)[number];

export interface SubagentModelsApi {
  get_catalog(input: GetCatalogInput): Promise<GetCatalogOutput>;
  get_policy(input: GetPolicyInput): Promise<GetPolicyOutput>;
  set_policy(input: SetPolicyInput): Promise<SetPolicyOutput>;
}

/** Adapter-facing event subscription surface. */
export interface RpcEventPort {
  onCatalogUpdated(handler: () => void): () => void;
  onPolicyUpdated(handler: (scope: ScopeName) => void): () => void;
}

/** Minimal, host-neutral stand-in for an RPC method definition object. */
export interface RpcMethodDescriptor {
  readonly input: Readonly<Record<string, unknown>>;
  readonly output: Readonly<Record<string, unknown>>;
}

/** Minimal, host-neutral stand-in for an RPC event definition object. */
export interface RpcEventDescriptor {
  readonly schema: Readonly<Record<string, unknown>>;
}

/** Concrete schemas. Adapters pass these straight into their RPC builder. */
export const RPC_METHOD_DESCRIPTORS: Readonly<Record<RpcMethodName, RpcMethodDescriptor>> = {
  get_catalog: {
    input: { type: "object", properties: {}, additionalProperties: false },
    output: {
      type: "object",
      properties: { catalog: { type: "object" } },
      required: ["catalog"],
    },
  },
  get_policy: {
    input: {
      type: "object",
      properties: { scope: { type: "string", enum: ["project", "global"] } },
      required: ["scope"],
    },
    output: {
      type: "object",
      properties: { rule: { type: "object" } },
      required: ["rule"],
    },
  },
  set_policy: {
    input: {
      type: "object",
      properties: {
        scope: { type: "string", enum: ["project", "global"] },
        rule: { type: "object" },
      },
      required: ["scope", "rule"],
    },
    output: {
      type: "object",
      properties: { rule: { type: "object" } },
      required: ["rule"],
    },
  },
};

export const RPC_EVENT_DESCRIPTORS: Readonly<Record<RpcEventName, RpcEventDescriptor>> = {
  catalog_updated: { schema: { type: "object", properties: {}, additionalProperties: false } },
  policy_updated: {
    schema: {
      type: "object",
      properties: { scope: { type: "string" } },
      required: ["scope"],
    },
  },
};

/** Complete transport-neutral contract, implemented by any adapter. */
export interface RpcContract {
  readonly namespace: string;
  readonly methods: Readonly<Record<RpcMethodName, RpcMethodDescriptor>>;
  readonly events: Readonly<Record<RpcEventName, RpcEventDescriptor>>;
}

export const SUBAGENT_MODELS_CONTRACT: RpcContract = {
  namespace: RPC_NAMESPACE,
  methods: RPC_METHOD_DESCRIPTORS,
  events: RPC_EVENT_DESCRIPTORS,
};
