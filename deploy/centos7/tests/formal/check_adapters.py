"""Exercise a site registration through the real queue; --ifv also runs Cadence."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))
from jobs import Jobs, load


def wait(path):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        record = load(path)
        if record["status"] not in ("queued", "running"):
            return record
        time.sleep(0.1)
    raise AssertionError("No terminal result")


def main(real_ifv):
    with tempfile.TemporaryDirectory(prefix="formal adapter ") as temporary:
        base = Path(temporary).resolve()
        workspace = base / "project"
        shutil.copytree(str(RUNNER.parent / "fifo"), str(workspace))
        import yaml
        config = yaml.safe_load((workspace / "verify.yaml").read_text())
        site = config["profiles"]["formal-ifv"]
        site["backend"] = "site-fpv"
        registry = base / "registry.json"
        os.environ["VERIFICATION_FORMAL_ADAPTERS"] = str(registry)
        fixture = base / "fixture.py"
        fixture.write_text("""import json,sys,time
from pathlib import Path
mode,request,result=sys.argv[1:]
r=json.loads(Path(request).read_text())
stage=Path(r["artifactsDir"])
(stage/"native.log").write_text("adapter protocol fixture")
d={"protocolVersion":1,"runId":r["runId"],"tool":{"name":"fixture","version":"1"},"artifacts":["native.log"],"properties":[]}
if mode=="bad-id": d["runId"]="wrong"
elif mode=="license": d["error"]={"status":"license_error","message":"fixture checkout failed"}
elif mode=="escape": d["artifacts"]=["../request.json"]
elif mode=="wait": time.sleep(60)
Path(result).write_text(json.dumps(d))
""", encoding="utf-8")
        jobs = Jobs(base / "runs")
        def submit(mode, expected, variant="normal"):
            real = mode == "ifv"
            command = [sys.executable, str(RUNNER / "formal_ifv_adapter.py")] if real else [sys.executable, str(fixture), mode]
            registry.write_text(json.dumps({"version": 1, "adapters": {"site-fpv": {"argv": command}}}))
            site["timeoutSeconds"] = 1 if expected == "timeout" else 100
            (workspace / "verify.yaml").write_text(json.dumps(config))
            with jobs.lock:
                run = jobs.submit(workspace, {"profile": "formal-ifv", "variant": variant})
            path = jobs.find(workspace, run["id"])
            if expected == "cancelled":
                for _ in range(100):
                    with jobs.lock:
                        if path in jobs.active:
                            jobs.cancel(path)
                            break
                    time.sleep(0.05)
            record = wait(path)
            assert record["status"] == expected, (expected, record)
            print(mode, record["id"], record["status"], record.get("toolVersions", {}), flush=True)
            return record
        for mode in ("omitted", "bad-id", "escape"):
            submit(mode, "missing_result")
        submit("license", "license_error")
        submit("wait", "timeout")
        submit("wait", "cancelled")
        if real_ifv:
            assert submit("ifv", "pass")["toolVersions"]["IFV"]
            result = submit("ifv", "fail", "mutant")
            assert any(a["kind"] == "waveform" for a in result["artifacts"])
        # Cancellation is immediately visible; wait for process cleanup before removing its run tree.
        for _ in range(100):
            with jobs.lock:
                if not jobs.active:
                    break
            time.sleep(0.05)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ifv", action="store_true")
    main(parser.parse_args().ifv)

