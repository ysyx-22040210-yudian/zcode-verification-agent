import type { useServices } from "@/hooks/useServices.js";

export interface VerificationFrameProps {
  readonly workspace: string;
}

export interface VerificationEntryProps extends VerificationFrameProps {
  readonly active: boolean;
  readonly onToggle: () => void;
  readonly toolsActive: boolean;
  readonly onToolsToggle: () => void;
  readonly fsdbActive: boolean;
  readonly onFsdbToggle: () => void;
  readonly designActive: boolean;
  readonly onDesignToggle: () => void;
  readonly knowledgeActive: boolean;
  readonly onKnowledgeToggle: () => void;
}


type DesignService = NonNullable<ReturnType<typeof useServices>["designQueryService"]>;
export type ToolCatalog = Awaited<ReturnType<DesignService["listTools"]>>;
export type VerificationTool = ToolCatalog["tools"][number];
export type ToolStarter = Awaited<ReturnType<DesignService["scaffoldTool"]>>;
export type CoverageJob = Awaited<ReturnType<DesignService["getCoverage"]>>;
export type CoverageFilter = Parameters<DesignService["coverageRows"]>[2];
export type CoveragePage = Awaited<ReturnType<DesignService["coverageRows"]>>;
export type FsdbJob = Awaited<ReturnType<DesignService["getFsdb"]>>;
export type FsdbRequest = Parameters<DesignService["startFsdb"]>[1];
export type FsdbFileList = Awaited<ReturnType<DesignService["listFsdb"]>>;
export type DesignQueryJob = Awaited<ReturnType<DesignService["get"]>>;
export type DesignQueryRequest = Parameters<DesignService["start"]>[1];

type VerificationService = NonNullable<ReturnType<typeof useServices>["verificationService"]>;
export type VerificationSnapshot = Awaited<ReturnType<VerificationService["inspect"]>>;
export type VerificationRun = VerificationSnapshot["runs"][number];
export type VerificationVariant = VerificationRun["variant"];
export type KnowledgeSource = Awaited<ReturnType<VerificationService["listKnowledge"]>>[number];
export type KnowledgeSearchResult = Awaited<ReturnType<VerificationService["searchKnowledge"]>>;
export type KnowledgeReadResult = Awaited<ReturnType<VerificationService["readKnowledge"]>>;
type FilingService = NonNullable<ReturnType<typeof useServices>["knowledgeFilingService"]>;
export type KnowledgeGuideResult = Awaited<ReturnType<FilingService["getKnowledgeGuide"]>>;

export interface KnowledgeLibraryProps {
  readonly startArchive: (prompt: string) => Promise<void>;
}
