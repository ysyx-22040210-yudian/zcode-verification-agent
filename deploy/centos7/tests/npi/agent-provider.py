"""Loopback test model for the native chat. Tools and their NPI results come from the real runner."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from http.server import HTTPServer

transport = importlib.util.spec_from_file_location("fixture_transport", str(Path(__file__).resolve().parents[1] / "knowledge-model.py"))
mock = importlib.util.module_from_spec(transport)
transport.loader.exec_module(mock)


def route(body):
    names = {t["function"]["name"].split("__")[-1]: t["function"]["name"] for t in body.get("tools", [])}
    if "design_query" not in names:
        return "RTL signal connectivity", []
    messages = body["messages"]
    calls = [c["function"]["name"] for m in messages for c in m.get("tool_calls", [])]
    latest = " ".join(mock.strings([m.get("content") for m in messages if m.get("role") == "tool"][-1:]))
    identity = re.search(r'"id"\s*:\s*"([a-f0-9]{32})"', latest)
    if not calls:
        action = "design_query"
        args = dict(operation="signal", direction="both", signal="npi_demo.lane[0].u_tx.port.valid",
                    kdb="build/simv.daidir/simv.kdb")
    elif identity and re.search(r'"status"\s*:\s*"(queued|running)"', latest):
        time.sleep(.7)
        action = "design_query_status"
        args = dict(jobId=identity.group(1))
    elif (identity and re.search(r'"status"\s*:\s*"complete"', latest) and
          all(x in latest for x in ("npi_demo.lane[0].bus.valid", "npi_demo.lane[0].u_rx", "npi_demo.lane[0].u_relay.u_tap"))
          and re.search(r'"drivers"\s*:\s*1', latest) and re.search(r'"loads"\s*:\s*2', latest)):
        print("REAL_NPI_RESULT", identity.group(1), flush=True)
        return "NPI_CHAT_JOB " + identity.group(1), []
    else:
        print("UNEXPECTED_NPI_RESPONSE", latest[:600], flush=True)
        return "Missing expected NPI evidence", []
    print("AGENT_TOOL_CALL", action, flush=True)
    return "", [{"id": "call_npi_" + str(len(calls)), "type": "function",
                 "function": {"name": names[action], "arguments": json.dumps(args)}}]


if __name__ == "__main__":
    mock.route = route
    HTTPServer(("127.0.0.1", int(sys.argv[1])), mock.Provider).serve_forever()

