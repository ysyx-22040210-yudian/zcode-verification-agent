import { createConnection } from "node:net";
import { readFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import type { IDesignQueryService, IKnowledgeFilingService, IVerificationService } from "./contract.js";

const MAX_RESPONSE_LENGTH = 8 * 1024 * 1024;

function runnerClient(socketPath: string | undefined) {
  return async function request<T>(action: string, workspace?: string, fields: object = {}): Promise<T> {
    if (!socketPath) throw new Error("Verification runner is not configured");
    const local = socketPath.endsWith(".json")
      ? JSON.parse(await readFile(socketPath, "utf8")) as { version: number; port: number; token: string }
      : undefined;
    if (local && (local.version !== 1 || !Number.isInteger(local.port) || typeof local.token !== "string")) {
      throw new Error("Invalid local verification endpoint");
    }
    const payload = JSON.stringify({ ...fields, action, workspace, auth: local?.token }) + "\n";
    return new Promise<T>((resolve, reject) => {
      const socket = local ? createConnection(local.port, "127.0.0.1") : createConnection(socketPath);
      let buffer = "";
      socket.setEncoding("utf8").setTimeout(20_000);
      socket.once("connect", () => socket.write(payload));
      socket.once("error", reject);
      socket.once("close", () => reject(new Error("Verification runner closed before responding")));
      socket.once("timeout", () => socket.destroy(new Error("Verification service request timed out")));
      socket.on("data", (chunk: string) => {
        buffer += chunk;
        if (buffer.length > MAX_RESPONSE_LENGTH) {
          socket.destroy(new Error("Verification response is too large"));
          return;
        }
        const end = buffer.indexOf("\n");
        if (end === -1) return;
        try {
          const reply = JSON.parse(buffer.slice(0, end)) as { result?: T; error?: string };
          if (typeof reply.error === "string") {
            reject(new Error(reply.error));
          } else if (reply.result !== undefined) {
            resolve(reply.result);
          } else {
            reject(new Error("Verification runner returned an invalid response"));
          }
        } catch (error) {
          reject(error);
        } finally {
          socket.destroy();
        }
      });
    });
  };
}

export function createVerificationService(socketPath: string | undefined): IVerificationService {
  const request = runnerClient(socketPath);
  return {
    async available() {
      if (!socketPath) return false;
      try {
        const state = await request<{ ok: boolean }>("health");
        return state.ok;
      } catch {
        return false;
      }
    },
    inspect: (workspace) => request("inspect", workspace),
    submit: (workspace, run) => request("submit", workspace, run),
    cancel: (workspace, runId) => request("cancel", workspace, { runId }),
    rerun: (workspace, runId) => request("rerun", workspace, { runId }),
    readArtifact: (workspace, runId, name, offset) =>
      request("readArtifact", workspace, { runId, name, offset }),
    advance: (workspace) => request("advance", workspace),
    listKnowledge: () => request("knowledgeList"),
    searchKnowledge: (query) => request("knowledgeSearch", undefined, query),
    readKnowledge: (selection) => request("knowledgeRead", undefined, selection),
    readKnowledgePdf: (range) => request("knowledgePdfRange", undefined, range),
  };
}

export function createDesignQueryService(socketPath: string | undefined): IDesignQueryService {
  const request = runnerClient(socketPath);
  return {
    listTools: (workspace, query) => request("toolCatalog", workspace, { query }),
    scaffoldTool: (workspace, toolId) => request("toolScaffold", workspace, { toolId }),
    start: (workspace, query) => request("designQueryStart", workspace, query),
    get: (workspace, jobId) => request("designQueryGet", workspace, { jobId }),
    startCoverage: (workspace, input) => request("coverageStart", workspace, input),
    getCoverage: (workspace, jobId) => request("coverageGet", workspace, { jobId }),
    coverageRows: (workspace, jobId, filter) => request("coverageRows", workspace, { ...filter, jobId }),
    listFsdb: (workspace) => request("fsdbFiles", workspace),
    fsdbArtifact: (workspace, runId, name) => request("fsdbArtifact", workspace, { runId, name }),
    startFsdb: (workspace, query) => request("fsdbStart", workspace, query),
    getFsdb: (workspace, jobId) => request("fsdbGet", workspace, { jobId }),
    fsdbViewer: (workspace, jobId) => request("fsdbViewer", workspace, { jobId }),
  };
}

export function createKnowledgeFilingService(socketPath: string | undefined): IKnowledgeFilingService {
  const request = runnerClient(socketPath);
  return {
    async importKnowledge(path) {
      if (!socketPath) throw new Error("Verification runner is not configured");
      const adapter = join(dirname(socketPath), "..", "runner", "knowledge_import.py");
      const staged = await promisify(execFile)("python3", [adapter, path], { maxBuffer: 16_384 });
      return request("knowledgeImportStatus", undefined, { jobId: staged.stdout.trim() });
    },
    knowledgeImportStatus: (jobId) => request("knowledgeImportStatus", undefined, { jobId }),
    getKnowledgeGuide: (selection) => request("knowledgeGuide", undefined, selection),
  };
}
