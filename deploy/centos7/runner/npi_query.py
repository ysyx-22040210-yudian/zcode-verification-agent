"""Durable native Verdi design queries shared by the desktop, MCP and local CLI."""
import hashlib
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import uuid

import fsdb
import coverage_source
import coverage_store
import sqlite3
import tempfile
import zipfile
from engines import LICENSE_ERROR
from jobs import atomically, load, process_start_ticks, signal_group, timestamp
from project import require

RUNNER = Path(__file__).resolve().parent
GROUPS = {"instance": "instances", "driver": "drivers", "load": "loads", "binding": "bindings", "warning": "warnings"}
ENDPOINT = ("scope", "kind", "file", "line", "name")
FIELDS = {"instance": ("path", "definition", "file", "line", "definitionFile", "definitionLine"),
          "binding": ("scope", "port", "modport", "direction", "interface"),
          "signal": ("requested", "canonical", "kind")}


def text_arg(request, key, default=""):
    value = request.get(key, default)
    require(isinstance(value, str) and len(value) <= 2048 and all(ord(c) >= 32 for c in value),
            "Invalid " + key)
    return value.strip()


def vcs_kdb_descriptor(path):
    # simv.kdb 是 VCS 构建说明；只读取 Design 标志，实际层次数据在同目录的 kdb.elab++。
    with path.open("rb") as stream:
        if not stream.readline(256).startswith(b"rc file Version "):
            return False
        section = b""
        for line in stream.read(65536).splitlines():
            line = line.strip()
            if line.startswith(b"["):
                section = line.lower()
            elif section == b"[design]":
                key, _, value = line.partition(b"=")
                if key.strip().upper() == b"KDB":
                    return value.strip().upper() == b"TRUE"
    return False


def elaboration_path(entry):
    require(entry.exists(), "KDB does not exist: " + str(entry))
    path = entry.resolve()
    if path.is_file():
        require(path.suffix.lower() == ".kdb" and vcs_kdb_descriptor(path),
                "Expected a VCS KDB-enabled .kdb file: " + str(entry))
        path = path.parent / "kdb.elab++"
    elif path.name.endswith(".daidir") or (path / "kdb.elab++").is_dir():
        path = path / "kdb.elab++"
    is_elaboration = path.name.endswith((".elab++", ".kdb")) or (path / "_stnElabDB").is_file()
    require(is_elaboration and path.is_dir() and next(path.iterdir(), None) is not None,
            "Missing or incomplete elaborated KDB at {}. Keep the compiled kdb.elab++ directory with the .kdb file.".format(path))
    return path.resolve()


def options(workspace, request):
    operation = request.get("operation")
    require(operation in ("instances", "signal"), "Choose instances or signal")
    direction = request.get("direction", "both")
    require(direction in ("driver", "load", "both"), "Choose driver, load or both")
    fields = {key: text_arg(request, key, default) for key, default in (
        ("definition", "*"), ("instance", "*"), ("scope", ""), ("signal", ""),
        ("kdb", ""))}
    require(operation != "signal" or fields["signal"], "Specify a hierarchical signal path")
    limit = request.get("limit", 50)
    require(type(limit) is int and 1 <= limit <= 200, "limit must be 1–200 per result group")
    timeout = request.get("timeoutSeconds", 300)
    require(type(timeout) is int and 1 <= timeout <= 3600, "timeoutSeconds must be 1–3600")
    fields.update(operation=operation, direction=direction, limit=limit, timeoutSeconds=timeout)
    require(fields["kdb"], "Choose a compiled KDB (simv.kdb, simv.daidir or kdb.elab++)")
    require(not any(key in request for key in ("filelist", "top", "profile")),
            "RTL queries use the selected KDB. Remove filelist, top and profile from this query.")
    entry = workspace / fields["kdb"]
    fields.update(kdb=str(entry), elaborationPath=str(elaboration_path(entry)))
    return fields


def read_events(path):
    with path.open(encoding="ascii") as stream:
        for line in stream:
            tag, *encoded = line.rstrip("\r\n").split("\t")
            yield tag, [bytes.fromhex(v).decode("utf8") for v in encoded]


def parse_events(path):
    result = {key: [] for key in GROUPS.values()}
    ended = False
    for tag, values in read_events(path):
        if tag in ("instance", "binding", "signal", "driver", "load"):
            keys = FIELDS.get(tag, ENDPOINT)
            require(len(values) >= len(keys), "Incomplete NPI record")
            row = {k: int(v) if k in ("line", "definitionLine") else v for k, v in zip(keys, values)}
            if tag in ("driver", "load"):
                row["related"] = [v for v in values[len(keys):] if v]
            if tag == "signal":
                result[tag] = row
            else:
                result[GROUPS[tag]].append(row)
        elif tag == "warning":
            result["warnings"].append(values[0])
        elif tag == "totals":
            result["totals"] = dict(zip(("instances", "drivers", "loads", "bindings", "warnings"), map(int, values)))
        elif tag == "outcome":
            result["outcome"] = values[0]
        elif tag == "error":
            raise ValueError(values[0])
        elif tag == "end":
            ended = True
    require(ended and "outcome" in result and len(result.get("totals", {})) == len(GROUPS),
            "Verdi did not finish the NPI query")
    result["truncated"] = any(result["totals"][group] > len(result[group]) for group in GROUPS.values())
    return result


def log_tail(path):
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 12000))
        return stream.read().decode("utf8", "replace")


class DesignQueries:
    def __init__(self, jobs):
        self.jobs = jobs
        self.pending = queue.Queue()
        for path in jobs.root.glob("*/design-queries/*/query.json"):
            record = load(path)
            if record["status"] == "queued":
                if record.get("kind", "rtl") == "rtl" and not record["query"].get("kdb"):
                    self.finish(path, record, "interrupted", "This pending source query requires a new submission with a compiled KDB.")
                else:
                    self.pending.put(path)
            elif record["status"] == "running":
                pid = record.get("pid")
                if pid and record.get("ticks") and record["ticks"] == process_start_ticks(pid):
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.finish(path, record, "interrupted", "Runner restarted during the Verdi query")
        threading.Thread(target=self.work, name="npi-worker", daemon=True).start()

    def get(self, workspace, job_id, kind="rtl"):
        require(isinstance(job_id, str) and re.fullmatch("[a-f0-9]{32}", job_id), "Invalid design query ID")
        path = self.jobs.directory(workspace) / "design-queries" / job_id / "query.json"
        require(path.is_file(), "Design query is not available in this workspace")
        record = load(path)
        require(record.get("kind", "rtl") == kind, "Select the corresponding RTL, FSDB or coverage query")
        if kind == "fsdb" and record["status"] == "complete" and record["query"]["operation"] == "wave" and record["result"]["outcome"] == "ok":
            record["viewerPath"] = str(path.parent / "waveform.html")
        return record

    def start(self, workspace, request, kind="rtl"):
        if kind == "coverage":
            query = coverage_source.database(workspace, self.jobs, request)
        else:
            query = fsdb.options(workspace, request) if kind == "fsdb" else options(workspace, request)
        job_id = uuid.uuid4().hex
        directory = self.jobs.directory(workspace) / "design-queries" / job_id
        directory.mkdir(parents=True, mode=0o700)
        record = {"id": job_id, "workspace": str(workspace), "query": query, "createdAt": timestamp(),
                  "status": "queued", "evidenceDirectory": str(directory)}
        if kind != "rtl":
            record["kind"] = kind
        path = directory / "query.json"
        atomically(path, record)
        self.pending.put(path)
        return record

    @staticmethod
    def finish(path, record, status, message=""):
        record.pop("pid", None)
        record.pop("ticks", None)
        record.update(status=status, finishedAt=timestamp(), message=message)
        atomically(path, record)

    def work(self):
        while True:
            path = self.pending.get()
            record = load(path)
            try:
                self.execute(path, record)
            except (OSError, ValueError, KeyError, IndexError, sqlite3.Error, zipfile.BadZipFile) as err:
                logs = log_tail(path.parent / "verdi.log") + "\n" + log_tail(path.parent / "verdiLog" / "compiler.log")
                status = "license_error" if LICENSE_ERROR.search(logs) else "tool_error"
                self.finish(path, record, status, (str(err) + "\n" + logs[-2400:]).strip())
            finally:
                self.pending.task_done()

    def execute(self, path, record):
        directory = path.parent
        query = record["query"]
        home = Path(os.environ["VERDI_HOME"])
        env = dict(os.environ, NQ_RUNNER=str(RUNNER), NQ_OUTPUT=str(directory / "events.tsv"))
        waveform = record.get("kind") == "fsdb"
        coverage = record.get("kind") == "coverage"
        if coverage:
            root = Path(query["database"])
            files = coverage_source.inventory(root)
            env.update(CV_DB=str(root), CV_EXCLUDE="")
            if query.get("excludeFile"):
                copied = directory / "exclusion.el"
                shutil.copyfile(query["excludeFile"], str(copied))
                env["CV_EXCLUDE"] = str(copied)
        elif waveform:
            fsdb.check_source(query)
            env.update(fsdb.environment(query))
        else:
            env.update({"NQ_" + k.upper(): str(v) for k, v in query.items()})
            database = str(elaboration_path(Path(query["kdb"])))
            require(database == query.get("elaborationPath", database), "Selected KDB path changed while queued")
            env["NQ_KDB"] = database
        script = {"coverage": "coverage_query.tcl", "fsdb": "fsdb_query.tcl"}.get(record.get("kind"), "npi_query.tcl")
        shutil.copyfile(str(home / "etc" / "novas.rc"), str(directory / "prefs.rc"))
        command = [str(home / "bin" / "verdi"), "-batch", "-nologo", "-guiConf", str(directory / "prefs.conf"),
                   "-rcFile", str(directory / "prefs.rc"), "-logdir", str(directory / "verdiLog"),
                   "-play", str(RUNNER / script)]
        record.update(status="running", startedAt=timestamp())
        atomically(path, record)
        with (directory / "verdi.log").open("wb") as log:
            proc = subprocess.Popen(command, cwd=str(directory) if coverage else record["workspace"], env=env, stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                record.update(pid=proc.pid, ticks=process_start_ticks(proc.pid))
                atomically(path, record)
                code = proc.wait(timeout=query["timeoutSeconds"])
            except subprocess.TimeoutExpired:
                signal_group(proc, signal.SIGKILL)
                proc.wait()
                self.finish(path, record, "timeout", "Verdi exceeded {} seconds".format(query["timeoutSeconds"]))
                return
            finally:
                if proc.poll() is None:
                    signal_group(proc, signal.SIGKILL)
                    proc.wait()
        require(code == 0, "Verdi exited with code " + str(code))
        if coverage:
            require(coverage_source.inventory(root) == files, "VDB changed during NPI extraction")
            final = directory / "export"
            with tempfile.TemporaryDirectory(dir=str(directory)) as staging:
                stage = Path(staging) / "export"
                stage.mkdir()
                result = coverage_store.save(stage, read_events(directory / "events.tsv"))
                result.update(coverage_source.export_source(root, stage, files))
                require(coverage_source.inventory(root) == files, "VDB changed during source export")
                for key in ("jsonlPath", "sqlitePath", "sourceArchive", "xmlPath", "manifestPath"):
                    result[key] = str(final / Path(result[key]).name)
                result["fingerprint"] = coverage_source.digest_inventory(files)
                if env["CV_EXCLUDE"]:
                    shutil.copyfile(env["CV_EXCLUDE"], str(stage / "exclusion.el"))
                    result["exclusionPath"] = str(final / "exclusion.el")
                    result["exclusionSha256"] = hashlib.sha256(Path(env["CV_EXCLUDE"]).read_bytes()).hexdigest()
                os.rename(str(stage), str(final))
            record["result"] = result
        elif waveform:
            fsdb.check_source(query)
            record["result"] = fsdb.parse(read_events(directory / "events.tsv"))
            if query["operation"] == "wave" and record["result"]["outcome"] == "ok":
                html = fsdb.viewer(dict(record, status="complete"))
                (directory / "waveform.html").write_text(html, encoding="utf-8")
        else:
            record["result"] = parse_events(directory / "events.tsv")
        self.finish(path, record, "complete")

