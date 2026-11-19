import { createServiceDescriptor } from "../descriptors.js";
export interface KnowledgeArchiveProgress {
  readonly status: "pending" | "partial" | "filed" | "needs_review";
  readonly filedPages: number;
  readonly totalPages: number;
  readonly topicCount: number;
  readonly reviewCount: number;
}

export interface KnowledgeGuide extends KnowledgeArchiveProgress {
  readonly topics: ReadonlyArray<{
    readonly title: string; readonly summary: string; readonly keywords: readonly string[];
    readonly page: number; readonly quote?: string; readonly visual?: boolean;
  }>;
  readonly nextOffset: number | null;
  readonly reviewPages: readonly number[];
}

export interface KnowledgeSelection {
  readonly sourceId: string;
  readonly sha256?: string;
}

export type KnowledgeImportReceipt =
  | { readonly jobId: string; readonly status: "indexing" }
  | { readonly jobId: string; readonly status: "failed"; readonly error: string }
  | { readonly jobId: string; readonly status: "indexed"; readonly sourceId: string; readonly sha256: string };

export interface IKnowledgeFilingService {
  importKnowledge(path: string): Promise<KnowledgeImportReceipt>;
  knowledgeImportStatus(jobId: string): Promise<KnowledgeImportReceipt>;
  getKnowledgeGuide(request: KnowledgeSelection & { readonly offset?: number }): Promise<KnowledgeGuide>;
}

export const IKnowledgeFilingService = createServiceDescriptor<IKnowledgeFilingService>("knowledgeFiling");

