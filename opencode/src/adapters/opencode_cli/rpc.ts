/**
 * OpenCode CLI transport binding for the universal RPC contract.
 *
 * Wire names and IO types come from `universal/rpc/contract.ts`; this adapter
 * only builds the concrete `Rpc.define(...)` object the host requires. The
 * inline schemas mirror `RPC_METHOD_DESCRIPTORS` / `RPC_EVENT_DESCRIPTORS`
 * because the host's schema type demands inline literals.
 */

import { Rpc } from "@opencode/plugin/rpc";

import {
  RPC_NAMESPACE,
  SUBAGENT_MODELS_CONTRACT,
  type SubagentModelsApi,
} from "#universal/rpc/contract";

export { SUBAGENT_MODELS_CONTRACT, type SubagentModelsApi } from "#universal/rpc/contract";

export const SubagentModels = Rpc.define({
  id: RPC_NAMESPACE,
  methods: {
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
  },
  events: {
    catalog_updated: { schema: { type: "object", properties: {}, additionalProperties: false } },
    policy_updated: {
      schema: {
        type: "object",
        properties: { scope: { type: "string" } },
        required: ["scope"],
      },
    },
  },
});

// Referencing the contract object keeps the adapter honest: when a method or
// event is added to the universal contract it must also be mapped above.
void SUBAGENT_MODELS_CONTRACT;
