/**
 * Universal-core barrel — the only import a new agent adapter needs.
 *
 * Pure TypeScript: no host SDK, no UI framework, no Node built-ins.
 */

export * from "./domain/types.js";
export * from "./domain/selector.js";
export * from "./domain/policy.js";
export * from "./domain/catalog.js";
export * from "./domain/config.js";
export * from "./domain/routing.js";
export * from "./services/catalog_service.js";
export * from "./events.js";
export * from "./ports.js";
export * from "./rpc/contract.js";
