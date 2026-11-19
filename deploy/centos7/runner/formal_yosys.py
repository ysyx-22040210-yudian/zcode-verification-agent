"""One flattened, assumption-preserving SMT model per declared top-level property."""
import json
import os
from pathlib import Path
import re
import tempfile

from engines import failure, log_text
from project import relative_file, require


def tool_paths():
    root = Path(os.environ.get("VERIFICATION_FORMAL_HOME",
                               str(Path(__file__).resolve().parents[1] / "formal-toolchain")))
    python = root / ("python/python.exe" if os.name == "nt" else "python/bin/python3.11")
    z3 = root / "bin" / ("z3.exe" if os.name == "nt" else "z3")
    require(python.is_file() and z3.is_file(), "Install the portable Formal kit or set VERIFICATION_FORMAL_HOME")
    return [str(python), "-I", "-X", "utf8", str(Path(__file__).with_name("formal_tool.py"))], str(z3)


def synthesis(job, work, folder):
    profile = job["profile"]
    sources = []
    for raw in relative_file(work, profile["filelist"]).read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        require(line in job["inputHashes"] and not re.search(r'[";\\\x00-\x1f]', line),
                "List one snapshotted RTL source per filelist line: " + line)
        relative_file(work, line)
        sources.append('"' + line + '"')
    require(sources, "Empty Formal filelist")
    top = profile["top"]
    options = " -DVERIFY_MUTANT" if job["variant"] == "mutant" else ""
    lines = ["read_verilog -formal -sv" + options + " " + " ".join(sources),
             "prep -flatten -top " + top, "write_json " + folder.name + "/clock-domains.json",
             "async2sync", "chformal -lower", "dffunmap", "design -save base"]
    for index, (name, kind) in enumerate(profile["properties"].items()):
        cell = top + "/" + name
        lines += ["design -load base", "select -assert-count 1 {} {}/t:${} %i".format(cell, top, kind),
                  "chformal -assert -cover -remove t:$assert t:$cover %u " + cell + " %d",
                  "write_smt2 -wires {}/{}.smt2".format(folder.name, index)]
    (folder / "build.ys").write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_clock_domain(netlist, top):
    # SMTBMC advances one implicit sample per step. Distinct edges cannot share that interpretation.
    module = json.loads(netlist.read_text(encoding="utf-8"))["modules"][top]
    clocks = set()
    inputs = {bit for port in module["ports"].values() if port["direction"] == "input" for bit in port["bits"]}
    for cell in module["cells"].values():
        ports, params = cell["connections"], cell["parameters"]
        require("latch" not in cell["type"].lower(), "The portable Formal profile requires an edge-clocked design")
        for port, enable, polarity in (("CLK", None, "CLK_POLARITY"), ("TRG", "TRG_ENABLE", "TRG_POLARITY"),
                                       ("RD_CLK", "RD_CLK_ENABLE", "RD_CLK_POLARITY"),
                                       ("WR_CLK", "WR_CLK_ENABLE", "WR_CLK_POLARITY")):
            if port not in ports:
                continue
            edges = int(params.get(polarity, "1"), 2)
            enabled = int(params.get(enable, "1"), 2)
            for index, net in enumerate(ports[port]):
                if enabled & (1 << index):
                    clocks.add((net, (edges >> index) & 1))
    require(len(clocks) <= 1 and all(net in inputs for net, _ in clocks),
            "The portable Formal profile supports one primary clock edge. Select a multiclock backend for this design.")


def solve(call, evidence, command, name, phase, bound, model):
    logfile = "{}-{}.log".format(name, phase)
    args = ["smtbmc", "-s", "z3", "-t", str(bound), "--noprogress", "--presat"]
    trace = None
    if phase == "induction":
        args.append("-i")
    else:
        if phase == "cover":
            args.append("-c")
        trace = evidence / (name + (".cover.vcd" if phase == "cover" else ".cex.vcd"))
        args.extend(["--dump-vcd", str(trace)])
    code = call(logfile, command + args + [str(model)])
    log = log_text(evidence / logfile)
    marker = re.findall(r"^##\s+\S+\s+Status:\s+(PASSED|FAILED|UNKNOWN|PREUNSAT)\s*$", log, re.M)
    if code in ("timeout", "cancelled") or not marker or code not in (0, 1):
        return None, failure(evidence / logfile, code, "SMTBMC " + phase)
    status = marker[-1]
    if (status == "PASSED") != (code == 0):
        return None, {"status": "tool_error", "message": "Inconsistent SMTBMC exit status: " + logfile}
    if phase == "cover" and status == "PASSED":
        hit = re.search(r"Reached cover statement in step (\d+)", log)
        if hit and trace.is_file() and trace.stat().st_size:
            return {"status": "reached", "depth": int(hit.group(1)), "trace": trace.name}, None
    elif phase == "base" and status == "FAILED":
        steps = re.findall(r"Checking assertions in step (\d+)", log)
        if steps and "Assert failed in " in log and trace.is_file() and trace.stat().st_size:
            return {"status": "counterexample", "depth": int(steps[-1]), "trace": trace.name}, None
    elif phase == "base" and status == "PASSED":
        return {"status": "bounded_pass", "depth": bound}, None
    elif phase == "induction" and status == "PASSED" and "Temporal induction successful." in log:
        return {"status": "proven"}, None
    elif status != "PASSED":
        return {"status": "unknown", "depth": bound, "toolStatus": phase + ": " + status}, None
    return None, {"status": "missing_result", "message": "Incomplete solver evidence: " + logfile}


def run_yosys(job, work, evidence, call):
    from formal_backends import summarize
    profile = job["profile"]
    command, z3 = tool_paths()
    command.append(str(work.parents[2] / ".formal-cache" / "wasmtime-21"))
    versions = {}
    for tool, argv, log in [("yosys", command + ["yosys", "-V"], "version.log"), ("z3", [z3, "--version"], "z3-version.log")]:
        code = call(log, argv)
        if code != 0:
            return failure(evidence / log, code, tool + " version probe")
        versions[tool] = log_text(evidence / log).strip().splitlines()[-1]
    folder = Path(tempfile.mkdtemp(prefix=".formal-", dir=str(work)))
    try:
        synthesis(job, work, folder)
    except ValueError as error:
        return {"status": "compile_error", "message": str(error), "toolVersions": versions}
    code = call("compile.log", command + ["yosys", "-Q", "-T", "-s", folder.name + "/build.ys"])
    if code != 0:
        result = failure(evidence / "compile.log", code, "Yosys elaboration")
        if code not in ("timeout", "cancelled") and "Assertion failed: selection" in log_text(evidence / "compile.log"):
            result.update(status="missing_result", message="Named Formal property is missing or has the wrong kind")
        return dict(result, toolVersions=versions)
    try:
        check_clock_domain(folder / "clock-domains.json", profile["top"])
    except ValueError as error:
        return {"status": "compile_error", "message": str(error), "toolVersions": versions}
    bound = profile.get("depth", 20)
    props = []
    for index, (name, kind) in enumerate(profile["properties"].items()):
        model = folder / ("{}.smt2".format(index))
        phase = "cover" if kind == "cover" else "base"
        result, error = solve(call, evidence, command, name, phase, bound, model)
        if error:
            return dict(error, properties=props, toolVersions=versions)
        if result["status"] == "bounded_pass" and profile.get("strategy", "prove") == "prove":
            induction, error = solve(call, evidence, command, name, "induction", bound, model)
            if error:
                return dict(error, properties=props, toolVersions=versions)
            if induction["status"] == "proven":
                result = induction
            else:
                result["toolStatus"] = induction["toolStatus"]
        props.append(dict(result, name=name, kind=kind))
    return dict(summarize(props), toolVersions=versions)

