"""Run all catalog starters against a disposable VM project containing real RTL, FSDB and VDB."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

work = Path(sys.argv[1]).resolve()
runner = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(runner))
import mcp


def rpc(name, **kw):
    reply = mcp.dispatch("tools/call", {"name": name, "arguments": kw}, str(work))
    assert not reply.get("isError"), reply
    return json.loads(reply["content"][0]["text"])


def script(name, *args):
    run = subprocess.run(
        [sys.executable, str(paths[name]), *args],
        cwd="/",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=220,
    )
    assert run.returncode == 0, run.stderr.decode()
    return run.stdout.decode("utf8"), run.stderr.decode("utf8")


cards = rpc("verification_tool_catalog")["tools"]
assert {r["id"] for r in cards} == {"rtl", "fsdb", "coverage"}
listed = {t["name"]: t["inputSchema"] for t in mcp.dispatch("tools/list", {}, str(work))["tools"]}
assert "kdb" in listed["design_query"]["required"]
assert not {"filelist", "profile", "top"}.intersection(listed["design_query"]["properties"])
for row in cards:
    detail = rpc("verification_tool_catalog", toolId=row["id"])
    assert all(listed[name] == schema for name, schema in detail["schemas"].items())
    assert set(detail["schemas"]) == set(row["methods"])
    assert all(Path(name).is_file() for name in (detail["sdkPath"], detail["guidePath"], row["cli"], *row["sources"]))
for term, tool in (
    ("负载", "rtl"),
    ("modport", "rtl"),
    ("simv.kdb", "rtl"),
    ("loader", "rtl"),
    ("fsdb_wave", "fsdb"),
    ("触发前", "fsdb"),
    ("covergroup", "coverage"),
    ("覆盖率", "coverage"),
):
    assert [r["id"] for r in rpc("verification_tool_catalog", query=term)["tools"]] == [tool]
assert len(rpc("verification_tool_catalog", query="Verdi NPI")["tools"]) == 3
assert not rpc("verification_tool_catalog", query="nothing-matches-xyz")["tools"]
paths = {}
for row in cards:
    with ThreadPoolExecutor(4) as pool:
        receipts = list(pool.map(lambda _: rpc("verification_tool_scaffold", toolId=row["id"]), range(4)))
    assert len({r["path"] for r in receipts}) == 1 and sum(r["created"] for r in receipts) <= 1
    receipt = receipts[0]
    paths[row["id"]] = Path(receipt["path"])
    assert paths[row["id"]].parent == work / "verification_extensions"
rtl, trace = script(
    "rtl", "--signal", "npi_demo.lane[0].u_tx.port.valid", "--kdb", "build/simv.daidir/simv.kdb"
)
assert {r["direction"] for r in csv.DictReader(io.StringIO(rtl))} == {"driver", "load"}, rtl
assert "query" in trace.lower()
waves, _ = script(
    "fsdb", "--file", "demo.fsdb", "--signal", "wave_demo.data", "--start", "8", "--end", "12"
)
waves = json.loads(waves)
assert waves["signals"][0]["initial"] == "10100101" and waves["signals"][0]["changes"] == 1
assert rpc("fsdb_get", jobId=waves["jobId"])["result"]["lanes"][0]["changes"] == [["9", "10xz0011"]]
gaps, _ = script(
    "coverage", "--database", "simv.vdb", "--metric", "fsm", "--kind", "TransBin", "--page-size", "1"
)
gaps = json.loads(gaps)
assert gaps["count"] == 1 and any("BUSY->IDLE" in s for s in gaps["examples"]), gaps
assert rpc("coverage_get", jobId=gaps["jobId"])["status"] == "complete"
# A user's edits survive simultaneous UI/MCP retries.
with paths["fsdb"].open("a", encoding="utf8") as f:
    f.write("\n# kept project customization\n")
before = paths["fsdb"].read_bytes()
with ThreadPoolExecutor(4) as pool:
    attempts = list(pool.map(lambda _: rpc("verification_tool_scaffold", toolId="fsdb"), range(6)))
assert all(not r["created"] for r in attempts) and paths["fsdb"].read_bytes() == before
print("VERIFIED_CATALOG_STARTERS", len(cards), waves["jobId"], gaps["jobId"], flush=True)
