import { createConnection } from "node:net";
import type { IVerificationService } from "./contract.js";

const MAX_RESPONSE_LENGTH = 8 * 1024 * 1024;

export function createVerificationService(socketPath: string | undefined): IVerificationService {
  async function request<T>(action: string, workspace?: string, fields: object = {}): Promise<T> {
    if (!socketPath) throw new Error("Verification runner is not configured");
    const payload = JSON.stringify({ ...fields, action, workspace }) + "\n";
    return new Promise<T>((resolve, reject) => {
      const socket = createConnection(socketPath);
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
  }

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
  };
}
