import type { KnowledgeSelection, VerificationRunRequest } from "./contract.js";

export const fifoRegression = {
  profile: "uvm",
  seed: 42,
  variant: "normal",
} satisfies VerificationRunRequest;

export const guideSelection = {
  sourceId: "example-manual",
  sha256: "a".repeat(64),
} satisfies KnowledgeSelection;
