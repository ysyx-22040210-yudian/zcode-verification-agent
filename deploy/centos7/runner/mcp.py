#!/usr/bin/env python3
"""MCP stdio adapter. All run and stage state is owned by the native service."""
import json
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "runtime" / "python"))
from server import call  # noqa: E402


STRING = {"type": "string"}
RUN_ID = {"type": "string", "description": "Run ID returned by verification_submit"}
REQUEST_ID = {"type": "string", "description": "Optional idempotency key for a retried submission"}
METHODS = {
    "verification_inspect": ("inspect", "List the project profiles, requirement checks, stages and runs.", {}, []),
    "verification_submit": (
        "submit", "Submit an actual SV, UVM or Formal job and return its run ID.",
        {"profile": STRING, "seed": {"type": "integer", "minimum": 1},
         "variant": {"enum": ["normal", "mutant"]}, "requestId": REQUEST_ID},
        ["profile"],
    ),
    "verification_get": ("get", "Read the current status of a run.", {"runId": RUN_ID}, ["runId"]),
    "verification_cancel": ("cancel", "Cancel an active or queued run.", {"runId": RUN_ID}, ["runId"]),
    "verification_rerun": ("rerun", "Run the existing snapshot and seed again.",
                           {"runId": RUN_ID, "requestId": REQUEST_ID}, ["runId"]),
    "verification_read_artifact": (
        "readArtifact", "Read a registered log, report or waveform excerpt from a run.",
        {"runId": RUN_ID, "name": STRING, "offset": {"type": "integer", "minimum": 0}},
        ["runId", "name"],
    ),
    "verification_complete_stage": ("advance", "Check the first pending stage and advance it if the evidence passes.",
                                    {}, []),
}
VERSIONS = {"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"}


def dispatch(method, params, workspace):
    if method == "initialize":
        requested = params.get("protocolVersion")
        return {"protocolVersion": requested if requested in VERSIONS else "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "zcode-verification", "version": "0.1.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [
            {"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": properties, "required": required,
                             "additionalProperties": False}}
            for name, (_, description, properties, required) in METHODS.items()]}
    if method == "tools/call":
        name = params["name"]
        if name not in METHODS:
            raise ValueError("Unknown tool: " + name)
        action, _, properties, required = METHODS[name]
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict) or set(arguments) - set(properties) or set(required) - set(arguments):
            raise ValueError("Invalid tool arguments")
        try:
            result = call(BASE / "runtime" / "verification.sock",
                          dict(arguments, action=action, workspace=workspace))
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        except (OSError, ValueError) as error:
            return {"isError": True, "content": [{"type": "text", "text": str(error)}]}
    raise LookupError("Method not found: " + method)


def main():
    workspace = str(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
    for line in sys.stdin:
        message = {}
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError("Invalid JSON-RPC request")
            if "id" not in message:
                continue
            output = {"result": dispatch(message["method"], message.get("params", {}), workspace)}
        except (KeyError, ValueError, TypeError, LookupError) as error:
            code = -32601 if isinstance(error, LookupError) and not isinstance(error, KeyError) else -32602
            output = {"error": {"code": code, "message": str(error)}}
        print(json.dumps(dict(output, jsonrpc="2.0", id=message.get("id") if isinstance(message, dict) else None),
                         ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
