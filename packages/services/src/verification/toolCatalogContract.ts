export type VerificationToolId = "rtl" | "fsdb" | "coverage";

interface ToolText {
  readonly zh: string;
  readonly en: string;
}

export interface VerificationTool {
  readonly id: VerificationToolId;
  readonly title: ToolText;
  readonly summary: ToolText;
  readonly methods: readonly string[];
  readonly cli: string;
  readonly sources: readonly string[];
  readonly starter: string;
  readonly usage: string;
  readonly starterPurpose: ToolText;
}

export interface VerificationToolCatalog {
  readonly tools: readonly VerificationTool[];
  readonly sdkPath: string;
  readonly guidePath: string;
}

export interface VerificationToolStarter {
  readonly toolId: VerificationToolId;
  readonly created: boolean;
  readonly path: string;
  readonly relativePath: string;
}
