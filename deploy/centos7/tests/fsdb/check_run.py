"""Verify a real SV job's binary FSDB evidence can be opened and searched."""
import json
import os
from pathlib import Path
import sys
import time

base = Path("/home/verification-agent")
sys.path[:0] = [str(base / "runner"), str(base / "runtime" / "python")]
from server import call

workspace = str(Path(sys.argv[1]).resolve())
endpoint = os.environ.get("ZCODE_VERIFICATION_SOCKET", str(base / "runtime" / "verification.sock"))


def rpc(action, **fields):
    return call(endpoint, dict(fields, action=action, workspace=workspace))


job = rpc("submit", profile="sv", seed=42, variant="normal")
deadline = time.monotonic() + 140
while job["status"] in ("queued", "running"):
    assert time.monotonic() < deadline, job
    time.sleep(0.4)
    job = rpc("get", runId=job["id"])
assert job["status"] == "pass", job
asset = next(a for a in job["artifacts"] if a["name"].lower().endswith("demo.fsdb"))
assert asset["kind"] == "waveform" and asset["bytes"] > 0
selected = rpc("fsdbArtifact", runId=job["id"], name=asset["name"])["path"]
assert selected in [row["path"] for row in rpc("fsdbFiles")["files"]]
try:
    rpc("readArtifact", runId=job["id"], name=asset["name"])
except ValueError as err:
    assert "FSDB" in str(err)
else:
    raise AssertionError("Binary FSDB reached the text log reader")
query = rpc("fsdbStart", operation="wave", file=selected, signals=["wave_demo.data"])
while query["status"] in ("queued", "running"):
    assert time.monotonic() < deadline, query
    time.sleep(0.4)
    query = rpc("fsdbGet", jobId=query["id"])
assert query["result"]["lanes"][0]["initial"] == "00010010" and Path(query["viewerPath"]).is_file(), query
print("NATIVE_RUN_FSDB_VERIFIED", job["id"], asset["name"], query["id"])
