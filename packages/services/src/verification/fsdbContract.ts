export interface FsdbRequest {
  readonly file: string;
  readonly operation: "signals" | "wave";
  readonly pattern?: string;
  readonly limit?: number;
  readonly signals?: readonly string[];
  readonly start?: string;
  readonly end?: string;
  readonly maxChanges?: number;
  readonly fingerprint?: string;
  readonly trigger?: { readonly signal: string; readonly edge: "rising" | "falling" | "change";
    readonly from?: string; readonly before?: string; readonly after?: string };
}

export interface FsdbCatalog {
  readonly files: ReadonlyArray<{ readonly path: string; readonly label: string; readonly bytes: number }>;
  readonly truncated: boolean;
}

export interface FsdbSignal {
  readonly name: string;
  readonly width: number;
  readonly kind: "digital" | "real" | "string";
}

export interface FsdbResult {
  readonly outcome: "ok" | "no_matches" | "no_trigger" | "trigger_limit" | "outside_range";
  readonly minTime: string;
  readonly maxTime: string;
  readonly scale: string;
  readonly start?: string;
  readonly end?: string;
  readonly triggerTime?: string;
  readonly searchedThrough?: string;
  readonly signals: readonly FsdbSignal[];
  readonly lanes: ReadonlyArray<FsdbSignal & {
    readonly status: "ok" | "missing" | "too_wide" | "unavailable";
    readonly initial: string | null; readonly changes: ReadonlyArray<readonly [string, string]>; readonly omittedAt?: string;
  }>;
  readonly truncated: boolean;
}

export interface FsdbJob {
  readonly id: string;
  readonly query: FsdbRequest;
  readonly status: "queued" | "running" | "complete" | "tool_error" | "license_error" | "interrupted" | "timeout";
  readonly evidenceDirectory: string;
  readonly viewerPath?: string;
  readonly message?: string;
  readonly result?: FsdbResult;
}

