import { createServiceDescriptor } from "../descriptors.js";

export type VerificationVariant = "normal" | "mutant";

export type VerificationStatus =
  | "queued" | "running" | "pass" | "fail" | "compile_error" | "tool_error"
  | "license_error" | "timeout" | "cancelled" | "unknown" | "bounded" | "missing_result" | "interrupted";

export interface VerificationProfile {
  readonly mode: "sv" | "uvm" | "formal";
  readonly top: string;
  readonly mutant?: boolean;
  readonly test?: string;
}

export interface VerificationArtifact {
  readonly name: string;
  readonly kind: "log" | "coverage" | "waveform";
  readonly bytes: number;
}

export interface VerificationRun {
  readonly id: string;
  readonly profileId: string;
  readonly profile: VerificationProfile;
  readonly variant: VerificationVariant;
  readonly seed: number;
  readonly engine: "VCS" | "IFV";
  readonly status: VerificationStatus;
  readonly createdAt: string;
  readonly inputDigest: string;
  readonly message?: string;
  readonly checksExecuted?: number;
  readonly uvmErrors?: number;
  readonly uvmFatals?: number;
  readonly rerunOf?: string;
  readonly artifacts: readonly VerificationArtifact[];
  readonly coverage?: {
    readonly functionalPercent?: number | null;
    readonly linePercent?: number;
    readonly conditionPercent?: number;
    readonly togglePercent?: number;
  };
  readonly properties?: ReadonlyArray<{
    readonly name: string;
    readonly kind: "assert" | "cover";
    readonly status: string;
    readonly depth?: number;
    readonly toolStatus?: string;
  }>;
}

export interface VerificationSnapshot {
  readonly name: string;
  readonly spec: string;
  readonly inputDigest: string;
  readonly profiles: Readonly<Record<string, VerificationProfile>>;
  readonly checks: ReadonlyArray<{
    readonly id: string;
    readonly title: string;
    readonly profiles: readonly string[];
    readonly property?: string;
  }>;
  readonly stages: ReadonlyArray<{
    readonly id: string;
    readonly completed: boolean;
    readonly missingProfiles: readonly string[];
  }>;
  readonly runs: readonly VerificationRun[];
}

export interface VerificationRunRequest {
  readonly profile: string;
  readonly seed: number;
  readonly variant: VerificationVariant;
  readonly requestId?: string;
}

export interface VerificationArtifactPage {
  readonly text: string;
  readonly nextOffset: number | null;
}

export interface IVerificationService {
  available(): Promise<boolean>;
  inspect(workspace: string): Promise<VerificationSnapshot>;
  submit(workspace: string, request: VerificationRunRequest): Promise<VerificationRun>;
  cancel(workspace: string, runId: string): Promise<VerificationRun>;
  rerun(workspace: string, runId: string): Promise<VerificationRun>;
  readArtifact(workspace: string, runId: string, name: string, offset: number): Promise<VerificationArtifactPage>;
  advance(workspace: string): Promise<VerificationSnapshot>;
}

export const IVerificationService = createServiceDescriptor<IVerificationService>("verification");
