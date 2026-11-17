import type { VerificationRunRequest } from "./contract.js";

export const fifoRegression = {
  profile: "uvm",
  seed: 42,
  variant: "normal",
} satisfies VerificationRunRequest;
