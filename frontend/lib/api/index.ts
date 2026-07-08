"use client";

/**
 * Public surface of the API client, split by domain.
 *
 * Import from "@/lib/api" exactly as before the split — this barrel
 * re-exports everything the old lib/api.ts God-file exported.
 */

export { ApiError, MAX_REFINEMENTS, SLA_REVIEW_HOURS, apiPaths } from "./http";

export * from "./requests";
export * from "./counsel";
export * from "./notifications";
export * from "./reference";
export * from "./playbooks";
export * from "./assignments";
export * from "./metrics";
export * from "./dashboard";
export * from "./billing";
export * from "./tabular";
export * from "./account";
export * from "./sharing";

// DOM download utility now lives in lib/download.ts; re-exported here for
// backwards compatibility with existing `@/lib/api` importers.
export { triggerBlobDownload } from "@/lib/download";
