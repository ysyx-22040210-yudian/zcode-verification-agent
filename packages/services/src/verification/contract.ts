import type { KnowledgeArchiveProgress, KnowledgeSelection } from "./knowledgeFilingContract.js";
import { createServiceDescriptor } from "../descriptors.js";

export type VerificationVariant = "normal" | "mutant";

export type VerificationStatus =
  | "queued" | "running" | "pass" | "fail" | "compile_error" | "tool_error"
  | "license_error" | "timeout" | "cancelled" | "unknown" | "bounded" | "missing_result" | "interrupted";

export interface VerificationProfile {
  readonly mode: "sv" | "uvm" | "formal";
  readonly top: string;
  readonly backend?: string;
  readonly strategy?: "prove" | "bmc";
  readonly depth?: number;
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
  readonly engine: string;
  readonly toolVersions?: Readonly<Record<string, string>>;
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
    readonly trace?: string;
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

export interface KnowledgeSource {
  readonly id: string;
  readonly title: string;
  readonly version: string;
  readonly filename: string;
  readonly pageCount: number;
  readonly sha256: string;
  readonly pdfBytes: number;
  readonly textCharacters: number;
  readonly emptyPages: readonly number[];
  readonly chapters: ReadonlyArray<{ readonly title: string; readonly page: number }>;
  readonly archive?: KnowledgeArchiveProgress;
}

export interface KnowledgeSearchRequest {
  readonly query: string;
  readonly sourceId?: string;
  readonly sha256?: string;
  readonly limit?: number;
}

export interface KnowledgeSearchResult {
  readonly query: string;
  readonly terms: readonly string[];
  readonly total: number;
  readonly results: ReadonlyArray<{
    readonly sourceId: string;
    readonly title: string;
    readonly version: string;
    readonly sha256: string;
    readonly page: number;
    readonly pageLabel: string;
    readonly section: string;
    readonly excerpt: string;
    readonly origin?: "model_guide" | "page_text";
  }>;
}

export interface KnowledgeReadRequest extends KnowledgeSelection {
  readonly page: number;
  readonly count?: number;
}

export interface KnowledgeReadResult {
  readonly source: KnowledgeSource;
  readonly pages: ReadonlyArray<{
    readonly page: number;
    readonly pageLabel: string;
    readonly section: string;
    readonly text: string;
  }>;
}

export interface KnowledgePdfRangeRequest extends KnowledgeSelection {
  readonly offset: number;
  readonly length: number;
}

export interface IVerificationService {
  available(): Promise<boolean>;
  inspect(workspace: string): Promise<VerificationSnapshot>;
  submit(workspace: string, request: VerificationRunRequest): Promise<VerificationRun>;
  cancel(workspace: string, runId: string): Promise<VerificationRun>;
  rerun(workspace: string, runId: string): Promise<VerificationRun>;
  readArtifact(workspace: string, runId: string, name: string, offset: number): Promise<VerificationArtifactPage>;
  advance(workspace: string): Promise<VerificationSnapshot>;
  listKnowledge(): Promise<readonly KnowledgeSource[]>;
  searchKnowledge(request: KnowledgeSearchRequest): Promise<KnowledgeSearchResult>;
  readKnowledge(request: KnowledgeReadRequest): Promise<KnowledgeReadResult>;
  readKnowledgePdf(request: KnowledgePdfRangeRequest): Promise<{ readonly base64: string }>;
}

export const IVerificationService = createServiceDescriptor<IVerificationService>("verification");
export { IDesignQueryService } from "./designQueryContract.js";
export { IKnowledgeFilingService } from "./knowledgeFilingContract.js";
export type { KnowledgeArchiveProgress, KnowledgeGuide, KnowledgeImportReceipt, KnowledgeSelection } from "./knowledgeFilingContract.js";
