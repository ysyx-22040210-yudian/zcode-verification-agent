"""Loopback-only model fixture. Native FSDB values and IDs must arrive through the Agent's MCP."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from http.server import HTTPServer

spec = importlib.util.spec_from_file_location(
    "transport", str(Path(__file__).resolve().parents[1] / "knowledge-model.py")
)
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def route(body):
    names = {t["function"]["name"].split("__")[-1]: t["function"]["name"] for t in body.get("tools", [])}
    if "fsdb_wave" not in names:
        return "FSDB waveform", []
    messages = body["messages"]
    calls = [c["function"]["name"].split("__")[-1] for m in messages for c in m.get("tool_calls", [])]
    latest = " ".join(transport.strings([m.get("content") for m in messages if m.get("role") == "tool"][-1:]))
    identity = re.search(r'"id"\s*:\s*"([a-f0-9]{32})"', latest)
    if not calls:
        action, args = "fsdb_files", {}
    elif calls[-1] == "fsdb_files" and "demo.fsdb" in latest:
        action, args = "fsdb_signals", {"file": "demo.fsdb", "pattern": "wave_demo.*"}
    elif identity and re.search(r'"status"\s*:\s*"(queued|running)"', latest):
        time.sleep(0.6)
        action, args = "fsdb_get", {"jobId": identity.group(1)}
    elif "fsdb_wave" not in calls and '"1ns"' in latest and "wave_demo.data" in latest:
        action, args = "fsdb_wave", {
            "file": "demo.fsdb",
            "signals": ["wave_demo.clk", "wave_demo.valid", "wave_demo.data", "wave_demo.stable"],
            "trigger": {
                "signal": "wave_demo.clk",
                "edge": "rising",
                "from": "6",
                "before": "7",
                "after": "3",
            },
        }
    elif (
        identity
        and re.search(r'"triggerTime"\s*:\s*"15"', latest)
        and "10xz0011" in latest
        and '"z"' in latest
    ):
        print("REAL_FSDB_RESPONSE", identity.group(1), flush=True)
        return "FSDB_CHAT_JOB " + identity.group(1), []
    else:
        print("UNEXPECTED_FSDB", latest[:600], flush=True)
        return "Missing expected FSDB tool result", []
    print("MODEL_TOOL", action, flush=True)
    return "", [
        {
            "id": "call_fsdb_" + str(len(calls)),
            "type": "function",
            "function": {"name": names[action], "arguments": json.dumps(args)},
        }
    ]


if __name__ == "__main__":
    transport.route = route
    HTTPServer(("127.0.0.1", int(sys.argv[1])), transport.Provider).serve_forever()
