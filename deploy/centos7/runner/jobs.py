"""Persistent per-workspace jobs and one serial native EDA worker."""
import datetime
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from hashlib import sha256
from pathlib import Path

from engines import run_vcs
from formal_backends import engine_name, run_formal
from project import definition, inputs_digest, require


DONE = {"pass", "fail", "compile_error", "tool_error", "license_error",
        "timeout", "cancelled", "unknown", "bounded", "missing_result", "interrupted"}
STAGES = ("plan", "simulation", "formal", "report")


def timestamp():
    return datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def atomically(path, value):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temp), str(path))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def signal_group(process, sig):
    if os.name == "nt":
        # The adapter, SMTBMC and its solver all belong to this job.
        subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                        "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        return
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def process_start_ticks(pid):
    try:
        raw = Path("/proc/{}/stat".format(pid)).read_text()
        return raw.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def retain_fsdb(work, evidence, inputs):
    """Keep simulated FSDBs alongside run evidence without duplicating large files."""
    output = evidence / "fsdb"
    if output.exists() or output.is_symlink():
        output = evidence / ("fsdb-" + uuid.uuid4().hex)
    for directory, _, names in os.walk(str(work)):
        for name in names:
            if not name.lower().endswith(".fsdb"):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(work)
            original = inputs / relative
            if original.is_file():
                old, current = original.stat(), path.stat()
                if (old.st_mtime_ns, old.st_size) == (current.st_mtime_ns, current.st_size):
                    continue
            target = output / relative
            require(evidence in target.resolve().parents, "Invalid FSDB evidence location")
            target.parent.mkdir(parents=True, exist_ok=True)
            # The runner creates work and evidence inside the same per-run directory.
            os.link(str(path), str(target))


class Jobs:
    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.active = {}
        self.recover()
        threading.Thread(target=self.work, name="eda-worker", daemon=True).start()

    def recover(self):
        for path in self.root.glob("*/*/run.json"):
            record = load(path)
            if record["status"] == "queued":
                self.pending.put(path)
            elif record["status"] == "running":
                started = record.get("process")
                if started and started.get("ticks") and started["ticks"] == process_start_ticks(started["pid"]):
                    try:
                        os.killpg(started["pid"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                record.update(status="interrupted", message="Runner stopped during this job", finishedAt=timestamp())
                record.pop("process", None)
                atomically(path, record)

    def workspace(self, value):
        require(isinstance(value, str) and Path(value).is_absolute(), "Absolute local workspace path required")
        root = Path(value).resolve()
        require(root.is_dir(), "Local workspace is unavailable")
        return root

    def directory(self, workspace):
        return self.root / sha256(str(workspace).encode("utf-8")).hexdigest()

    def records(self, workspace):
        return sorted(self.directory(workspace).glob("*/run.json"), reverse=True,
                      key=lambda path: path.stat().st_mtime)

    def find(self, workspace, run_id):
        require(isinstance(run_id, str) and re.fullmatch(r"[a-f0-9]{32}", run_id), "Invalid run ID")
        path = self.directory(workspace) / run_id / "run.json"
        require(path.is_file(), "Run is not available in this workspace")
        return path

    def submit(self, workspace, request, previous=None):
        root = previous.parent / "inputs" if previous else workspace
        config = definition(root)
        old = load(previous) if previous else None
        profile_id = old["profileId"] if old else request.get("profile")
        require(isinstance(profile_id, str) and profile_id in config["profiles"], "Unknown profile")
        profile = config["profiles"][profile_id]
        seed = old["seed"] if old else request.get("seed", 42)
        require(type(seed) is int and 1 <= seed <= 2147483647, "Seed must be 1–2147483647")
        variant = old["variant"] if old else request.get("variant", "normal")
        require(variant == "normal" or (variant == "mutant" and profile.get("mutant") is True),
                "Profile does not enable this variant")

        token = request.get("requestId")
        if token is not None:
            require(isinstance(token, str) and 1 <= len(token) <= 128, "Invalid request ID")
            for candidate in self.records(workspace):
                prior = load(candidate)
                if prior.get("requestId") == token:
                    require((prior["profileId"], prior["variant"], prior["seed"], prior.get("rerunOf")) ==
                            (profile_id, variant, seed, old["id"] if old else None),
                            "Request ID was already used with different parameters")
                    return prior
        run_id = uuid.uuid4().hex
        directory = self.directory(workspace) / run_id
        directory.mkdir(parents=True)
        try:
            digest, inputs = inputs_digest(root, config, directory / "inputs")
            (directory / "evidence").mkdir()
            record = {
                "id": run_id, "workspace": str(workspace), "profileId": profile_id,
                "profile": profile, "variant": variant, "seed": seed, "test": profile.get("test"),
                "engine": engine_name(profile),
                "status": "queued", "createdAt": timestamp(), "commands": [],
                "inputDigest": digest, "inputHashes": inputs, "artifacts": [],
            }
            if old:
                record["rerunOf"] = old["id"]
            if token is not None:
                record["requestId"] = token
            path = directory / "run.json"
            atomically(path, record)
        except Exception:
            shutil.rmtree(str(directory))
            raise
        self.pending.put(path)
        return record

    def cancel(self, path):
        record = load(path)
        if record["status"] in DONE:
            return record
        record.update(status="cancelled", message="Cancelled", finishedAt=timestamp())
        if path in self.active:
            signal_group(self.active[path], signal.SIGTERM)
        atomically(path, record)
        return record

    def execute_command(self, path, cwd, evidence, logname, argv, deadline):
        log = evidence / logname
        with log.open("wb") as stream:
            with self.lock:
                record = load(path)
                if record["status"] == "cancelled":
                    return "cancelled"
                if time.monotonic() >= deadline:
                    return "timeout"
                record["commands"].append({"argv": argv, "cwd": str(cwd), "log": logname})
                try:
                    process = subprocess.Popen(
                        argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=stream,
                        stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as error:
                    stream.write(str(error).encode("utf-8"))
                    atomically(path, record)
                    return 127
                self.active[path] = process
                ticks = process_start_ticks(process.pid)
                if ticks:
                    record["process"] = {"pid": process.pid, "ticks": ticks}
                atomically(path, record)

            reason = None
            while process.poll() is None:
                with self.lock:
                    cancelled = load(path)["status"] == "cancelled"
                if cancelled or time.monotonic() >= deadline:
                    reason = "cancelled" if cancelled else "timeout"
                    signal_group(process, signal.SIGTERM)
                    try:
                        process.wait(2)
                    except subprocess.TimeoutExpired:
                        pass
                    if os.name != "nt":
                        signal_group(process, signal.SIGKILL)
                    process.wait()
                    break
                time.sleep(0.12)
            with self.lock:
                record = load(path)
                record.pop("process", None)
                atomically(path, record)
                self.active.pop(path, None)
                if record["status"] == "cancelled":
                    return "cancelled"
            return reason or process.returncode

    def work(self):
        while True:
            path = self.pending.get()
            with self.lock:
                record = load(path)
                if record["status"] != "queued":
                    continue
                record.update(status="running", startedAt=timestamp())
                atomically(path, record)
            evidence = path.parent / "evidence"
            work = path.parent / "work"
            deadline = time.monotonic() + record["profile"].get("timeoutSeconds", 180)
            try:
                shutil.copytree(str(path.parent / "inputs"), str(work))
                adapter = run_formal if record["profile"]["mode"] == "formal" else run_vcs

                def call(name, args):
                    return self.execute_command(path, work, evidence, name, args, deadline)

                result = adapter(record, work, evidence, call)
                if record["engine"] == "VCS":
                    retain_fsdb(work, evidence, path.parent / "inputs")
            except Exception as error:
                (evidence / "runner.log").write_text(str(error), encoding="utf-8")
                result = {"status": "tool_error", "message": str(error)}
            artifacts = []
            for item in sorted(evidence.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    relative = item.relative_to(evidence).as_posix()
                    kind = "waveform" if item.suffix.lower() in (".vcd", ".fsdb") else "coverage" if relative.startswith("coverage/") else "log"
                    artifacts.append({"name": relative, "kind": kind, "bytes": item.stat().st_size})
            with self.lock:
                record = load(path)
                if record["status"] != "cancelled":
                    record.update(result, finishedAt=timestamp())
                record["artifacts"] = artifacts
                atomically(path, record)

    def artifact(self, run_path, name, offset):
        record = load(run_path)
        files = {item["name"]: item for item in record["artifacts"]}
        require(isinstance(name, str) and name in files, "Unknown artifact")
        require(not name.lower().endswith(".fsdb"), "Open binary FSDB artifacts with the FSDB waveform tool")
        require(type(offset) is int and 0 <= offset <= files[name]["bytes"], "Invalid artifact offset")
        root = run_path.parent / "evidence"
        target = (root / name).resolve()
        require(root in target.parents, "Artifact escaped the run directory")
        with target.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(96000)
        return {"text": data.decode("utf-8", errors="replace"),
                "nextOffset": offset + len(data) if offset + len(data) < files[name]["bytes"] else None}

    def inspect(self, workspace, advance=False):
        config = definition(workspace)
        digest, _ = inputs_digest(workspace, config)
        runs = [load(path) for path in self.records(workspace)]
        current = {}
        for run in sorted(runs, key=lambda item: item["createdAt"], reverse=True):
            if run["inputDigest"] == digest and run["variant"] == "normal":
                current.setdefault(run["profileId"], run)
        requirements = {
            stage: [name for name, profile in config["profiles"].items()
                    if not (profile["mode"] == "formal" and profile.get("optional", False)) and
                    (stage == "report" or (stage == "formal") == (profile["mode"] == "formal"))]
            for stage in ("simulation", "formal", "report")
        }
        progress_path = self.directory(workspace) / "stages.json"
        progress = load(progress_path) if progress_path.is_file() else {}
        completed = progress.get("completed", []) if progress.get("inputDigest") == digest else []
        stages = []
        for stage in STAGES:
            missing = [item for item in requirements.get(stage, []) if current.get(item, {}).get("status") != "pass"]
            stages.append({"id": stage, "completed": stage in completed and not missing,
                           "missingProfiles": missing})
        if advance:
            first = next((item for item in stages if not item["completed"]), None)
            if first and not first["missingProfiles"]:
                completed = [item["id"] for item in stages if item["completed"]] + [first["id"]]
                first["completed"] = True
                progress_path.parent.mkdir(parents=True, exist_ok=True)
                atomically(progress_path, {"inputDigest": digest, "completed": completed})
        return {"name": config.get("name", workspace.name), "spec": config["spec"], "inputDigest": digest,
                "profiles": config["profiles"], "checks": config["checks"], "stages": stages,
                "runs": sorted(runs, key=lambda item: item["createdAt"], reverse=True)[:60]}
