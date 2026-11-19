"""Read-only native FSDB jobs, file discovery and portable waveform documents."""
import json
import os
from pathlib import Path
import re

from jobs import load
from project import require


def safe_text(value, label, maximum=2048):
    require(
        isinstance(value, str) and len(value) <= maximum and not any(ord(c) < 32 for c in value),
        "Invalid " + label,
    )
    return value


def tick(value, label, default=None):
    if value is None:
        return default
    require(type(value) in (str, int) and re.fullmatch(r"[0-9]{1,20}", str(value)), "Invalid tick: " + label)
    number = int(value)
    require(number < (1 << 64), "Tick exceeds FSDB range: " + label)
    return str(number)


def integer(value, name, maximum):
    require(type(value) is int and 1 <= value <= maximum, "{} must be 1–{}".format(name, maximum))
    return value


def fingerprint(path):
    info = path.stat()
    return "{}-{}-{}-{}".format(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def list_files(jobs, workspace):
    rows = []
    directories = [workspace]
    inspected = 0
    seen = set()
    skipped = False

    def add(path, label):
        try:
            if path.is_file() and path not in seen:
                rows.append(dict(path=str(path), label=label, bytes=path.stat().st_size))
                seen.add(path)
        except OSError:
            pass

    # Registered artifacts can be outside the source workspace.
    for record_path in jobs.records(workspace):
        for artifact in load(record_path).get("artifacts", []):
            name = artifact["name"]
            if name.lower().endswith(".fsdb"):
                add(record_path.parent / "evidence" / name, record_path.parent.name[:8] + "/" + name)
                if len(rows) >= 100:
                    return dict(files=rows, truncated=True)
    while directories:
        parent = directories.pop()
        try:
            with os.scandir(str(parent)) as entries:
                for entry in entries:
                    inspected += 1
                    if inspected > 40000 or len(rows) >= 100:
                        return dict(files=rows, truncated=True)
                    if entry.name.lower().endswith(".fsdb") and entry.is_file():
                        path = Path(entry.path)
                        add(path, str(path.relative_to(workspace)))
                    elif entry.name not in {".git", "node_modules"} and entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
        except OSError:
            skipped = True
    return dict(files=sorted(rows, key=lambda r: r["label"]), truncated=skipped)


def options(workspace, request):
    operation = request.get("operation")
    require(operation in ("signals", "wave"), "Unknown FSDB operation")
    file = safe_text(request.get("file"), "FSDB path", 4096)
    path = (workspace / file).resolve()
    require(file and path.is_file() and path.suffix.lower() == ".fsdb", "Select a readable .fsdb file")
    stamp = fingerprint(path)
    require(
        request.get("fingerprint") in (None, stamp), "FSDB changed after selection; search the updated file"
    )
    data = dict(
        file=str(path),
        operation=operation,
        fingerprint=stamp,
        timeoutSeconds=integer(request.get("timeoutSeconds", 180), "timeoutSeconds", 3600),
    )
    if operation == "signals":
        data.update(
            pattern=safe_text(request.get("pattern", "*"), "signal pattern"),
            limit=integer(request.get("limit", 100), "limit", 300),
        )
        return data
    names = request.get("signals")
    require(isinstance(names, list) and 1 <= len(names) <= 16, "Select 1–16 signals")
    require(
        all(safe_text(n, "signal name") and n.strip() for n in names) and len(set(names)) == len(names),
        "Use distinct hierarchical signal names",
    )
    data.update(signals=names, maxChanges=integer(request.get("maxChanges", 512), "maxChanges", 2048))
    start, end = tick(request.get("start"), "start"), tick(request.get("end"), "end")
    if start is not None:
        data["start"] = start
    if end is not None:
        data["end"] = end
    require(start is None or end is None or int(start) <= int(end), "End must be at or after start")
    if request.get("trigger") is not None:
        t = request["trigger"]
        require(start is None and end is None, "Use either an explicit interval or a trigger")
        require(
            isinstance(t, dict) and t.get("edge") in ("rising", "falling", "change"), "Invalid trigger edge"
        )
        signal = safe_text(t.get("signal"), "trigger signal")
        require(bool(signal.strip()), "Select a trigger signal")
        data["trigger"] = {
            "signal": signal,
            "edge": t["edge"],
            "from": tick(t.get("from"), "from", "0"),
            "before": tick(t.get("before"), "before", "0"),
            "after": tick(t.get("after"), "after", "0"),
        }
    return data


def check_source(query):
    require(
        fingerprint(Path(query["file"])) == query["fingerprint"], "FSDB changed during query; search again"
    )


def environment(query):
    names = query.get("signals", [])
    trigger = query.get("trigger", {})
    env = dict(
        FW_FILE=query["file"],
        FW_OP=query["operation"],
        FW_PATTERN=query.get("pattern", "*"),
        FW_LIMIT=str(query.get("limit", 100)),
        FW_MAX_CHANGES=str(query.get("maxChanges", 512)),
        FW_START=query.get("start", ""),
        FW_END=query.get("end", ""),
        FW_COUNT=str(len(names)),
        FW_TRIGGER=trigger.get("signal", ""),
        FW_EDGE=trigger.get("edge", ""),
        FW_FROM=trigger.get("from", "0"),
        FW_BEFORE=trigger.get("before", "0"),
        FW_AFTER=trigger.get("after", "0"),
    )
    env.update({"FW_SIG_" + str(i): name for i, name in enumerate(names)})
    return env


def parse(events):
    result = dict(signals=[], lanes=[], truncated=False)
    ended = False
    for tag, values in events:
        if tag == "file":
            result["minTime"], result["maxTime"], result["scale"] = values
        elif tag == "signal":
            name, width, kind = values
            result["signals"].append(dict(name=name, width=int(width), kind=kind))
        elif tag == "catalog":
            result["truncated"] = values[0] == "1"
        elif tag == "window":
            result["start"], result["end"] = values
        elif tag == "trigger" and values[1]:
            result["triggerTime" if values[0] == "ok" else "searchedThrough"] = values[1]
        elif tag == "lane":
            name, width, kind, status = values[:4]
            result["lanes"].append(
                dict(
                    name=name,
                    width=int(width),
                    kind=kind,
                    status=status,
                    initial=values[5] if len(values) > 5 and values[4] == "1" else None,
                    changes=[],
                )
            )
        elif tag == "change":
            result["lanes"][-1]["changes"].append(values)
        elif tag == "omitted":
            result["lanes"][-1]["omittedAt"] = values[0]
            result["truncated"] = True
        elif tag == "outcome":
            result["outcome"] = values[0]
        elif tag == "error":
            raise ValueError(values[0])
        elif tag == "end":
            ended = True
    require(ended and "outcome" in result and "scale" in result, "Verdi did not complete the FSDB read")
    return result


def viewer(record):
    require(
        record["status"] == "complete"
        and record["query"]["operation"] == "wave"
        and record["result"]["outcome"] == "ok",
        "This query has no waveform window",
    )
    data = dict(record["result"], id=record["id"], file=record["query"]["file"])
    # Escape markup boundaries even in signal names and recorded string values.
    payload = (
        json.dumps(data, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = Path(__file__).with_name("fsdb_viewer.html").read_text(encoding="utf-8")
    return template.replace("__FSDB_SAMPLES__", payload)
