"""Formal backend selection and the version-one commercial adapter protocol."""
import json
import os
from pathlib import Path
import shutil
import sys

from engines import failure
from project import formal_backend, relative_file, require

PROPERTY_STATES = {
    "assert": {"proven", "bounded_pass", "counterexample", "vacuous", "unknown"},
    "cover": {"reached", "unreachable", "unknown"},
}
ERRORS = {"license_error", "compile_error", "tool_error", "missing_result", "timeout"}


def summarize(properties):
    states = {item["status"] for item in properties}
    if "counterexample" in states:
        status, message = "fail", "An assertion has a counterexample"
    elif states and states <= {"proven", "reached"}:
        status, message = "pass", "All required assertions were proven and covers reached"
    elif states and states <= {"proven", "reached", "bounded_pass"}:
        status, message = "bounded", "Assertions checked only within the reported bound"
    else:
        status, message = "unknown", "At least one required property is inconclusive, vacuous or unreached"
    return {"status": status, "message": message, "properties": properties}


def engine_name(profile):
    if profile["mode"] != "formal":
        return "VCS"
    backend = formal_backend(profile)
    return {"yosys": "Yosys + Z3", "ifv": "IFV"}.get(backend, backend)


def read_json(path):
    require(path.stat().st_size <= 1024 * 1024, "Formal adapter JSON exceeds 1 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def adapter_command(backend):
    if backend == "ifv":
        return [sys.executable, str(Path(__file__).with_name("formal_ifv_adapter.py"))]
    registered = Path(os.environ.get("VERIFICATION_FORMAL_ADAPTERS", str(Path.home() / ".zcode/formal-adapters.json")))
    require(registered.is_file(), "Formal adapter is not registered: " + backend)
    data = read_json(registered)
    require(isinstance(data, dict) and data.get("version") == 1 and isinstance(data.get("adapters"), dict),
            "Invalid Formal adapter registry")
    entry = data["adapters"].get(backend)
    args = entry.get("argv") if isinstance(entry, dict) else None
    require(isinstance(args, list) and args and all(isinstance(v, str) and v and "\0" not in v for v in args)
            and Path(args[0]).is_absolute(), "Register an absolute executable and argv for " + backend)
    return args


def publish(report, job, staging, evidence, code):
    require(isinstance(report, dict) and report.get("protocolVersion") == 1 and report.get("runId") == job["id"],
            "Formal result protocol or run ID mismatch")
    artifacts = report.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) <= 512, "Invalid Formal artifact list")
    names = set()
    for name in artifacts:
        source = relative_file(staging, name)
        relative = Path(name)
        require(relative.as_posix() == name and name not in names, "Duplicated or non-canonical artifact name")
        target = evidence / relative
        require(evidence in target.resolve().parents and not target.exists(), "Duplicate evidence name")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(target))
        names.add(name)
    error = report.get("error")
    if error is not None:
        require(isinstance(error, dict) and error.get("status") in ERRORS and isinstance(error.get("message"), str),
                "Invalid Formal tool error")
        return {"status": error["status"], "message": error["message"]}
    tool = report.get("tool")
    require(isinstance(tool, dict) and all(isinstance(tool.get(k), str) and tool[k].strip()
            for k in ("name", "version")), "Adapter must identify its actual tool and version")
    require(code == 0 and any((evidence / n).stat().st_size for n in names), "Missing completed native report")
    expected = job["profile"]["properties"]
    received = report.get("properties")
    require(isinstance(received, list), "Missing property reports")
    props = {}
    for item in received:
        require(isinstance(item, dict), "Invalid property report")
        name, kind, state = item.get("name"), item.get("kind"), item.get("status")
        require(isinstance(name, str) and name in expected and name not in props and kind == expected[name]
                and state in PROPERTY_STATES[kind], "Unexpected or duplicate property report: " + str(name))
        if "depth" in item or state == "bounded_pass":
            depth = item.get("depth")
            require(type(depth) is int and depth >= (1 if state == "bounded_pass" else 0), "Invalid property depth")
        if "trace" in item:
            require(item["trace"] in names and (evidence / item["trace"]).stat().st_size, "Missing property trace")
        props[name] = {k: item[k] for k in ("name", "kind", "status", "depth", "trace", "toolStatus") if k in item}
    require(set(props) == set(expected), "Adapter omitted required properties: " + ", ".join(sorted(set(expected) - set(props))))
    return dict(summarize([props[k] for k in expected]), toolVersions={tool["name"]: tool["version"]})


def run_formal(job, work, evidence, call):
    backend = formal_backend(job["profile"])
    if backend == "yosys":
        from formal_yosys import run_yosys
        return run_yosys(job, work, evidence, call)
    argv = adapter_command(backend)
    exchange = work.parent / "formal-adapter"
    staging = exchange / "artifacts"
    staging.mkdir(parents=True)
    request = exchange / "request.json"
    result = exchange / "result.json"
    payload = {"protocolVersion": 1, "runId": job["id"], "backend": backend, "profile": job["profile"],
               "seed": job["seed"], "variant": job["variant"], "workDir": str(work),
               "inputsDir": str(work.parent / "inputs"), "inputDigest": job["inputDigest"],
               "inputHashes": job["inputHashes"], "artifactsDir": str(staging)}
    request.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    code = call("adapter.log", argv + [str(request), str(result)])
    if code in ("cancelled", "timeout") or (code != 0 and not result.is_file()):
        return failure(evidence / "adapter.log", code, backend)
    if not result.is_file() or result.is_symlink():
        return {"status": "missing_result", "message": "Formal adapter did not write its result"}
    try:
        return publish(read_json(result), job, staging, evidence, code)
    except (ValueError, TypeError, OSError, KeyError) as error:
        return {"status": "missing_result", "message": str(error)}

