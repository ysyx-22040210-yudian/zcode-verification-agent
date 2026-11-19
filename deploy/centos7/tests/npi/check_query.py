"""Run against the licensed native service. Pass the query workspace and the path of the compiled example simv.kdb."""
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import sys
import time

workspace = os.path.realpath(sys.argv[1])
endpoint = os.environ.get("ZCODE_VERIFICATION_SOCKET", "/home/verification-agent/runtime/verification.sock")


def rpc(action, expect_error=False, **fields):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(endpoint)
        sock.sendall((json.dumps(dict(fields, workspace=workspace, action=action)) + "\n").encode())
        response = json.loads(sock.makefile("rb").readline())
    if expect_error:
        assert "KDB" in response.get("error", ""), response
        return
    assert "error" not in response, response
    return response["result"]


def run(design, **query):
    job = rpc("designQueryStart", **dict(design, **query))
    deadline = time.monotonic() + 150
    while job["status"] in ("queued", "running"):
        assert time.monotonic() < deadline, job
        time.sleep(.2)
        job = rpc("designQueryGet", jobId=job["id"])
    print(job["id"], query, job["status"], flush=True)
    assert job["status"] == "complete", job
    assert job["query"]["kdb"] == str(Path(workspace) / design["kdb"]), job
    assert Path(job["query"]["elaborationPath"]) == database.resolve(), job
    assert not {"filelist", "profile", "top"}.intersection(job["query"]), job
    log = (Path(job["evidenceDirectory"]) / "verdi.log").read_text(errors="replace")
    assert "NPI KDB: " + str(database.resolve()) in log, log
    return job["result"]


def check(design):
    base = "npi_demo.lane[0]."
    other = "npi_demo.lane[1]."
    instances = run(design, operation="instances", definition="sender")
    assert {row["path"] for row in instances["instances"]} == {base+"u_tx", other+"u_tx"}, instances
    limited = run(design, operation="instances", definition="sender", limit=1)
    assert len(limited["instances"]) == 1 and limited["totals"]["instances"] == 2 and limited["truncated"]
    scoped = run(design, operation="instances", instance="*u_t*", scope=base[:-1])
    assert {row["path"] for row in scoped["instances"]} == {base+"u_tx", base+"u_relay.u_tap"}, scoped

    def signal(path, **kw):
        return run(design, operation="signal", signal=path, **kw)

    def sites(result, side):
        assert result["outcome"] == "ok", result
        assert all(Path(row["file"]).name == "design.sv" for row in result[side]), result
        return {(row["scope"], row["line"]) for row in result[side]}

    multi = signal("npi_demo.multi")
    assert sites(multi, "drivers") == {("npi_demo", 38), ("npi_demo", 39)}, multi
    assert sites(multi, "loads") == {("npi_demo", 40)}, multi
    for prefix in [base+"bus.", base+"u_tx.port.", base+"u_relay.u_tap.sigs.", base+"bus.master."]:
        valid = signal(prefix+"valid")
        assert valid["signal"]["canonical"] == base+"bus.valid", valid
        assert sites(valid, "drivers") == {(base+"u_tx", 10)}, valid
        assert sites(valid, "loads") == {(base+"u_rx", 17), (base+"u_relay.u_tap", 21)}, valid
        assert {b["modport"] for b in valid["bindings"]} == {"", "master", "slave"}, valid
    ready = signal(other+"u_rx.rx.ready")
    assert sites(ready, "drivers") == {(other+"u_rx", 16)}, ready
    assert sites(ready, "loads") == {(other+"u_tx", 12)}, ready
    for bit in [1, 2]:
        word = signal(base+"bus.data["+str(bit)+"]")
        assert sites(word, "drivers") == {(base+"u_tx", 11)}, word
        assert sites(word, "loads") == ({(base+"u_rx", 17)} if bit == 1 else set()), word
    direct = signal(base+"bus.direct")
    assert sites(direct, "drivers") == {("npi_demo", 41)}, direct
    assert sites(direct, "loads") == {("npi_demo", 42)}, direct
    cond = signal("npi_demo.watched.direct")
    assert sites(cond, "loads") == {("npi_demo.u_cond", 51)}, cond
    array = signal("npi_demo.u_array.p.valid")
    assert array["signal"]["canonical"] == "npi_demo.banks[1].valid", array
    assert sites(array, "drivers") == {("npi_demo.u_array", 57)}, array
    assert not signal("npi_demo.banks[0].valid")["drivers"]
    for path in ("aliased.value", "u_writer.p.push", "aliased.writer.push"):
        alias = signal("npi_demo.u_array."+path)
        assert alias["signal"]["canonical"] == "npi_demo.u_array.aliased.value", alias
        assert sites(alias, "drivers") == {("npi_demo.u_array.u_writer", 68)}, alias
    gated = signal("npi_demo.u_array.aliased.enable")
    assert sites(gated, "loads") == {("npi_demo.u_array.u_writer", 68)}, gated
    assert signal(base+"bus.unknown")["outcome"] == "not_found"
    spare = signal("npi_demo.spare")
    assert spare["outcome"] == "ok" and not spare["drivers"] and not spare["loads"], spare
    assert run(design, operation="instances", definition="does_not_exist")["outcome"] == "no_matches"


entry = sys.argv[2] if len(sys.argv) > 2 else "build/simv.daidir/simv.kdb"
manifest = Path(workspace) / entry
database = manifest.parent / "kdb.elab++"
check({"kdb": entry})
for alias in (manifest.parent, database):
    result = run({"kdb": str(alias)}, operation="instances", definition="sender")
    assert {r["path"] for r in result["instances"]} == {"npi_demo.lane[0].u_tx", "npi_demo.lane[1].u_tx"}
for invalid in ({}, {"filelist": "design.f", "top": "npi_demo"}, {"profile": "sv"},
                {"kdb": "missing.kdb"}, {"kdb": entry, "filelist": "design.f"}):
    rpc("designQueryStart", expect_error=True, operation="instances", **invalid)
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    orphan = root / "simv.kdb"
    shutil.copy(str(manifest), str(orphan))
    rpc("designQueryStart", expect_error=True, operation="instances", kdb=str(orphan))
    (root / "kdb.elab++").mkdir()
    rpc("designQueryStart", expect_error=True, operation="instances", kdb=str(orphan))
    (root / "kdb.elab++").rmdir()
    (root / "kdb.elab++").symlink_to(database.resolve(), target_is_directory=True)
    orphan.write_text("unrelated text\n")
    rpc("designQueryStart", expect_error=True, operation="instances", kdb=str(orphan))
    unrelated = root / "design.f"
    unrelated.write_text("design.sv\n")
    rpc("designQueryStart", expect_error=True, operation="instances", kdb=str(unrelated))
print("NPI_NATIVE_QUERY_ACCEPTANCE_PASSED")

