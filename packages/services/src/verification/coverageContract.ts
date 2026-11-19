export interface CoverageRequest {
  readonly path?: string;
  readonly runId?: string;
  readonly excludeFile?: string;
}

export interface CoverageJob {
  readonly id: string;
  readonly status:
    | "queued"
    | "running"
    | "complete"
    | "timeout"
    | "interrupted"
    | "license_error"
    | "tool_error";
  readonly query: { readonly database: string };
  readonly message?: string;
  readonly result?: {
    readonly rowCount: number;
    readonly sourceFiles: number;
    readonly xmlNodes: number;
    readonly xmlErrors: number;
    readonly views: ReadonlyArray<{
      readonly id: string;
      readonly name: string;
      readonly metrics: Readonly<
        Record<string, { readonly dataRecords: number }>
      >;
    }>;
    readonly jsonlPath: string;
    readonly sqlitePath: string;
    readonly xmlPath: string;
    readonly manifestPath: string;
    readonly sourceArchive: string;
  };
}

export interface CoverageFilter {
  readonly view?: string;
  readonly metric?: string;
  readonly kind?: string;
  readonly state?: string;
  readonly search?: string;
  readonly after?: number;
  readonly limit?: number;
}

export interface CoveragePage {
  readonly rows: ReadonlyArray<{
    readonly id: number;
    readonly parentId: number | null;
    readonly view: string;
    readonly metric: string;
    readonly relation: string;
    readonly kind: string;
    readonly name: string;
    readonly scope: string;
    readonly state: string;
    readonly flags?: readonly string[];
    readonly file?: string;
    readonly line?: number;
    readonly count?: number;
    readonly goal?: number;
    readonly covered?: number;
    readonly coverable?: number;
    readonly status?: number;
  }>;
  readonly nextAfter: number | null;
}
