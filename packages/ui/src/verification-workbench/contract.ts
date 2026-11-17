import type { useServices } from "@/hooks/useServices.js";

export interface VerificationFrameProps {
  readonly workspace: string;
}

export interface VerificationEntryProps extends VerificationFrameProps {
  readonly active: boolean;
  readonly onToggle: () => void;
}


type VerificationService = NonNullable<ReturnType<typeof useServices>["verificationService"]>;
export type VerificationSnapshot = Awaited<ReturnType<VerificationService["inspect"]>>;
export type VerificationRun = VerificationSnapshot["runs"][number];
export type VerificationVariant = VerificationRun["variant"];
