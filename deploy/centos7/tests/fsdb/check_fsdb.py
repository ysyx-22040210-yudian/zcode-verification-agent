"""Run against the native runner and compare FSDB samples with independently decoded VCD."""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import tempfile
import time

workspace = Path(sys.argv[1]).resolve()
fsdb = sys.argv[2] if len(sys.argv) > 2 else "demo.fsdb"
endpoint = os.environ.get("ZCODE_VERIFICATION_SOCKET", "/home/verification-agent/runtime/verification.sock")


def rpc(action, **fields):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(endpoint)
        sock.sendall((json.dumps(dict(fields, action=action, workspace=str(workspace))) + "\n").encode())
        reply = json.loads(sock.makefile("rb").readline())
    if "error" in reply:
        raise ValueError(reply["error"])
    return reply["result"]


def query(operation, file=fsdb, **fields):
    job = rpc("fsdbStart", operation=operation, file=file, **fields)
    until = time.monotonic() + 140
    while job["status"] in ("queued", "running"):
        assert time.monotonic() < until, job
        time.sleep(0.2)
        job = rpc("fsdbGet", jobId=job["id"])
    assert job["status"] == "complete", job
    print(job["id"], operation, job["result"]["outcome"], flush=True)
    return job


def independently_decoded():
    paths, waves, scopes = {}, {}, []
    tick = 0
    definitions_done = False
    for s in Path(sys.argv[3]).read_text().splitlines():
        s = s.strip()
        if s.startswith("$scope "):
            scopes.append(s.split()[2])
        elif s.startswith("$upscope "):
            scopes.pop()
        elif s.startswith("$var "):
            _, _, width, code, leaf = s.split()[:5]
            paths[".".join(scopes + [leaf])] = code
            waves.setdefault(code, [])
        elif s.startswith("$enddefinitions"):
            definitions_done = True
        elif not definitions_done:
            continue
        elif re.fullmatch(r"#\d+", s):
            tick = int(s[1:])
        elif re.match(r"[01xz]", s, re.I):
            waves[s[1:]].append([str(tick), s[0].lower()])
        elif s.startswith("b"):
            val, code = s[1:].split()
            waves[code].append([str(tick), val.lower()])
    return {p: waves[c] for p, c in paths.items()}


reference = independently_decoded()
files = rpc("fsdbFiles")
assert any(Path(row["path"]).name == Path(fsdb).name for row in files["files"]), files
found = query("signals", pattern="*observed")["result"]
assert {row["name"] for row in found["signals"]} == {
    "wave_demo.left_lane.observed",
    "wave_demo.right_lane.observed",
}
assert (found["minTime"], found["maxTime"], found["scale"]) == ("0", "25", "1ns"), found
assert query("signals", pattern="never_exists")["result"]["outcome"] == "no_matches"
assert query("signals", pattern="*", limit=1)["result"]["truncated"]
names = [
    "wave_demo." + s for s in ("clk", "valid", "data", "stable", "left_lane.observed", "right_lane.observed")
]
wave = query("wave", signals=names)
r = wave["result"]
for lane in r["lanes"]:
    assert lane["status"] == "ok" and not lane.get("omittedAt")
    assert [["0", lane["initial"]]] + lane["changes"] == reference[lane["name"]], lane
cut = query("wave", signals=names[:4], start="8", end="12")["result"]
assert cut["lanes"][2]["initial"] == "10100101" and cut["lanes"][2]["changes"] == [["9", "10xz0011"]]
assert cut["lanes"][1]["initial"] == "1" and cut["lanes"][1]["changes"] == [["12", "x"]]
assert cut["lanes"][3]["initial"] == "1" and not cut["lanes"][3]["changes"]
t = query(
    "wave",
    signals=names[:3],
    trigger={"signal": names[0], "edge": "rising", "from": "6", "before": "7", "after": "3"},
)["result"]
assert (t["triggerTime"], t["start"], t["end"]) == ("15", "8", "18"), t
t = query(
    "wave",
    signals=[names[1]],
    trigger={"signal": names[0], "edge": "falling", "from": "10", "before": "20", "after": "30"},
)["result"]
assert (t["triggerTime"], t["start"], t["end"]) == ("10", "0", "25"), t
t = query(
    "wave", signals=[names[1]], trigger={"signal": names[3], "edge": "change", "before": "3", "after": "2"}
)["result"]
assert t["outcome"] == "no_trigger"
cap = query("wave", signals=[names[0]], maxChanges=1)["result"]["lanes"][0]
assert cap["changes"] == [["5", "1"]] and cap["omittedAt"] == "10", cap
point = query("wave", signals=[names[1], "wave_demo.unknown"], start="15", end="15")["result"]
assert point["lanes"][0]["initial"] == "z" and point["lanes"][1]["status"] == "missing", point
assert rpc("fsdbGet", jobId=wave["id"])["result"] == r
with tempfile.TemporaryDirectory(prefix="波形 回归-") as shared:
    folder = Path(shared)
    folder.chmod(0o755)
    copied = folder / "总线 采样.fsdb"
    shutil.copyfile(str(workspace / fsdb), str(copied))
    copied.chmod(0o644)
    unicode_wave = query("wave", file=str(copied), signals=[names[2]], start="8", end="12")
    assert unicode_wave["result"]["lanes"] == [cut["lanes"][2]]
print("NATIVE_FSDB_REFERENCE_VERIFIED", wave["id"], flush=True)
