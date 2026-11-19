"""Loopback model fixture for exercising the real Agent, native MCP server and project editing tools."""
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

EXTENSION = '''"""Report the exact timestamps of FSDB transitions containing X or Z."""
import json
from pathlib import Path

from fsdb_edges import VerificationClient

workspace = Path(__file__).resolve().parents[1]
job = VerificationClient(workspace).run(
    "fsdb_wave", file="demo.fsdb", signals=["wave_demo.data"], start="8", end="12"
)
lane = job["result"]["lanes"][0]
assert lane["status"] == "ok" and lane.get("omittedAt") is None, lane
ticks = [tick for tick, value in lane["changes"] if any(bit in value.lower() for bit in "xz")]
report = {"jobId": job["id"], "count": len(ticks), "unknownTicks": ticks}
(workspace / "unknown-edges.json").write_text(json.dumps(report, indent=2) + "\\n", encoding="utf8")
print(json.dumps(report))
'''


def native_id(text):
    match = re.search(r'"(?:id|jobId)"\s*:\s*"([0-9a-f]{32})"', text)
    return match.group(1) if match else None


def route(body):
    messages = body["messages"]
    names = {t["function"]["name"].split("__")[-1]: t["function"]["name"] for t in body.get("tools", [])}
    user = " ".join(transport.strings([m.get("content") for m in messages if m.get("role") == "user"]))
    if not names or ("wave_report.py" not in user and "simv.kdb" not in user):
        return "Verification tools", []
    history = [c for msg in messages for c in msg.get("tool_calls", [])]
    by_id = {}
    selected = set()
    for c in history:
        method = c["function"]["name"].split("__")[-1]
        args = json.loads(c["function"].get("arguments") or "{}")
        if method == "DeferredToolCall":
            method = args["name"].split("__")[-1]
        if method == "LocalToolSearch" and args.get("query", "").startswith("select:"):
            selected.add(args["query"][7:])
        by_id[c["id"]] = method
    if len(history) > 100:
        return "Fixture exceeded its expected tool count", []
    replies = {}
    for m in messages:
        if m.get("role") == "tool":
            action = by_id.get(m.get("tool_call_id"))
            if action:
                replies[action] = " ".join(transport.strings(m.get("content")))

    def invoke(action, **args):
        if action not in names:
            selector = next((n for n in ("ToolSearch", "LocalToolSearch") if n in names), None)
            if not selector:
                print("MISSING", action, sorted(names), flush=True)
                return "Tool unavailable: " + action, []
            exact = action if action in ("Read", "Write", "Bash") else "mcp__verification__" + action
            if selector == "LocalToolSearch" and exact in selected and "DeferredToolCall" in names:
                args, action = {"name": exact, "input": args}, "DeferredToolCall"
                print("LOADED_METHOD", exact, flush=True)
            else:
                args, action = {"query": "select:" + exact, "max_results": 1}, selector
        print("CALL", action, flush=True)
        return "", [
            {
                "id": "call_" + str(len(history)),
                "type": "function",
                "function": {"name": names[action], "arguments": json.dumps(args)},
            }
        ]

    if "wave_report.py" in user:
        if "verification_tool_catalog" not in replies:
            return invoke("verification_tool_catalog", toolId="fsdb")
        if "fsdb_wave" not in replies["verification_tool_catalog"]:
            return "Missing FSDB method schema", []
        if "verification_tool_scaffold" not in replies:
            return invoke("verification_tool_scaffold", toolId="fsdb")
        match = re.search(
            r'"path"\s*:\s*"([^"]+/verification_extensions/fsdb_edges\.py)"',
            replies["verification_tool_scaffold"],
        )
        if not match:
            return "Missing project starter", []
        starter = Path(match.group(1))
        if "Read" not in replies:
            return invoke("Read", file_path=str(starter))
        if "VerificationClient" not in replies["Read"]:
            return "Cannot read the starter", []
        if "Write" not in replies:
            return invoke("Write", file_path=str(starter.with_name("wave_report.py")), content=EXTENSION)
        if "Bash" not in replies:
            return invoke(
                "Bash",
                command="python3 verification_extensions/wave_report.py",
                description="Run the project FSDB extension",
            )
        stdout = replies["Bash"]
        job = native_id(stdout)
        if not job or not re.search(r'"unknownTicks"\s*:\s*\[\s*"9"\s*\]', stdout):
            print("EXTENSION_OUTPUT", stdout[:700], flush=True)
            return "Extension did not produce a verified tick", []
        if "fsdb_get" not in replies:
            return invoke("fsdb_get", jobId=job)
        if "10xz0011" in replies["fsdb_get"] and native_id(replies["fsdb_get"]) == job:
            print("PROJECT_EXTENSION_VERIFIED", job, flush=True)
            return "TOOLKIT_AGENT_EXTENSION " + job, []
        return "Missing matching native evidence", []

    for action, poll, args, evidence in (
        (
            "design_query",
            "design_query_status",
            dict(operation="instances", definition="sender", kdb="build/simv.daidir/simv.kdb"),
            ("lane[0].u_tx", "lane[1].u_tx"),
        ),
        (
            "fsdb_wave",
            "fsdb_get",
            dict(file="demo.fsdb", signals=["wave_demo.data"], start="8", end="12"),
            ("10100101", "10xz0011"),
        ),
        ("coverage_extract", "coverage_get", dict(path="simv.vdb"), ("merged", "sqlitePath")),
    ):
        if action not in replies:
            return invoke(action, **args)
        result = replies.get(poll, replies[action])
        job = native_id(result)
        if job and (poll not in replies or re.search(r'"status"\s*:\s*"(queued|running)"', result)):
            time.sleep(0.5)
            return invoke(poll, jobId=job)
        if not job or not all(value in result for value in evidence):
            print("NATIVE_RESULT", action, result[:700], flush=True)
            return "Missing native evidence for " + action, []
    if "coverage_rows" not in replies:
        return invoke(
            "coverage_rows",
            jobId=native_id(replies["coverage_get"]),
            view="merged",
            metric="fsm",
            kind="TransBin",
            state="missed",
        )
    if "BUSY->IDLE" not in replies["coverage_rows"]:
        return "Missing FSM result", []
    ids = [native_id(replies[name]) for name in ("design_query_status", "fsdb_get", "coverage_get")]
    print("CHAT_VERIFIED", *ids, flush=True)
    return "TOOLKIT_ROUTED " + " ".join(ids), []


if __name__ == "__main__":
    transport.route = route
    HTTPServer(("127.0.0.1", int(sys.argv[1])), transport.Provider).serve_forever()
