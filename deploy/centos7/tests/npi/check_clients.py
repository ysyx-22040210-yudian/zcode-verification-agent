"""Submit through the native Agent's stdio MCP and reopen the result using the VM CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

runner = Path(sys.argv[1]).resolve()
workspace = str(Path(sys.argv[2]).resolve())
env = dict(os.environ, PYTHONIOENCODING="utf-8")
child = subprocess.Popen([sys.executable, str(runner / "mcp.py"), workspace], env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
count = 0


def rpc(method, params):
    global count
    count += 1
    child.stdin.write(json.dumps(dict(jsonrpc="2.0", id=count, method=method, params=params)) + "\n")
    child.stdin.flush()
    reply = json.loads(child.stdout.readline())
    assert reply["id"] == count and "result" in reply, reply
    return reply["result"]


def tool(name, args):
    reply = rpc("tools/call", dict(name=name, arguments=args))
    assert not reply.get("isError"), reply
    return json.loads(reply["content"][0]["text"])


try:
    rpc("initialize", dict(protocolVersion="2025-06-18"))
    names = {item["name"] for item in rpc("tools/list", {})["tools"]}
    assert {"design_query", "design_query_status"}.issubset(names)
    job = tool("design_query", dict(operation="signal", signal="npi_demo.lane[0].u_tx.port.valid",
                                    direction="both", kdb=sys.argv[3] if len(sys.argv) > 3 else "build/simv.daidir/simv.kdb"))
    deadline = time.monotonic() + 90
    while job["status"] in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(.4)
        job = tool("design_query_status", dict(jobId=job["id"]))
    assert job["status"] == "complete", job
    assert job["result"]["totals"]["drivers"] == 1 and job["result"]["totals"]["loads"] == 2, job
    data = subprocess.check_output([sys.executable, str(runner / "design-query.py"), "status",
                                    "--workspace", workspace, "--id", job["id"]], env=env)
    assert json.loads(data) == job
    print("MCP_CLI_SHARED_RESULT", job["id"], job["result"]["signal"]["canonical"])
finally:
    child.stdin.close()
    child.wait(timeout=10)

