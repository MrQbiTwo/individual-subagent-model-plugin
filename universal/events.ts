/**
 * Core events emitted by adapters and observed by host integrations.
 *
 * Re-exported from the shared vocabulary so an adapter imports one stable
 * symbol instead of reaching into the domain folder. The definition itself
 * lives in `domain/types.ts` to keep the dependency graph acyclic.
 */

export type { CoreEvent } from "./domain/types.js";
