import { createServiceDescriptor } from "../descriptors.js";
import type { CoverageFilter, CoverageJob, CoveragePage, CoverageRequest } from "./coverageContract.js";
import type { FsdbCatalog, FsdbJob, FsdbRequest } from "./fsdbContract.js";
import type { VerificationToolCatalog, VerificationToolId, VerificationToolStarter } from "./toolCatalogContract.js";

export interface DesignQueryRequest {
  readonly operation: "instances" | "signal";
  readonly definition?: string;
  readonly instance?: string;
  readonly scope?: string;
  readonly signal?: string;
  readonly direction?: "both" | "driver" | "load";
  readonly kdb: string;
  readonly limit?: number;
}

interface SourceLocation {
  readonly file: string;
  readonly line: number;
}

interface DesignEndpoint extends SourceLocation {
  readonly scope: string;
  readonly kind: string;
  readonly name: string;
  readonly related: readonly string[];
}

export interface DesignQueryResult {
  readonly outcome: "ok" | "no_matches" | "not_found" | "partial" | "unsupported";
  readonly signal?: { readonly requested: string; readonly canonical: string; readonly kind: string };
  readonly totals: Readonly<Record<"instances" | "drivers" | "loads" | "bindings" | "warnings", number>>;
  readonly truncated: boolean;
  readonly warnings: readonly string[];
  readonly instances: ReadonlyArray<SourceLocation & {
    readonly path: string; readonly definition: string; readonly definitionFile: string; readonly definitionLine: number;
  }>;
  readonly drivers: readonly DesignEndpoint[];
  readonly loads: readonly DesignEndpoint[];
  readonly bindings: ReadonlyArray<{
    readonly scope: string; readonly port: string; readonly modport: string; readonly direction: string; readonly interface: string;
  }>;
}

export interface DesignQueryJob {
  readonly id: string;
  readonly status: "queued" | "running" | "complete" | "tool_error" | "license_error" | "timeout" | "interrupted";
  // 旧查询可能来自源码展开；读取历史记录时保留原始来源。
  readonly query: Omit<DesignQueryRequest, "kdb"> & { readonly kdb?: string; readonly elaborationPath?: string };
  readonly evidenceDirectory: string;
  readonly result?: DesignQueryResult;
  readonly message?: string;
}

export interface IDesignQueryService {
  listTools(workspace: string, query?: string): Promise<VerificationToolCatalog>;
  scaffoldTool(workspace: string, toolId: VerificationToolId): Promise<VerificationToolStarter>;
  startCoverage(workspace: string, request: CoverageRequest): Promise<CoverageJob>;
  getCoverage(workspace: string, jobId: string): Promise<CoverageJob>;
  coverageRows(workspace: string, jobId: string, filter: CoverageFilter): Promise<CoveragePage>;
  start(workspace: string, request: DesignQueryRequest): Promise<DesignQueryJob>;
  get(workspace: string, jobId: string): Promise<DesignQueryJob>;
  listFsdb(workspace: string): Promise<FsdbCatalog>;
  fsdbArtifact(workspace: string, runId: string, name: string): Promise<{ readonly path: string }>;
  startFsdb(workspace: string, request: FsdbRequest): Promise<FsdbJob>;
  getFsdb(workspace: string, jobId: string): Promise<FsdbJob>;
  fsdbViewer(workspace: string, jobId: string): Promise<{ readonly html: string }>;
}

export const IDesignQueryService = createServiceDescriptor<IDesignQueryService>("designQuery");

