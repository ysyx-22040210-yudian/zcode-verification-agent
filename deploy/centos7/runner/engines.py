"""Native SV/UVM and IFV adapters. The runner owns process lifetime and evidence."""
import os
import re
from pathlib import Path


LICENSE_ERROR = re.compile(
    r"license (?:checkout|check[- ]?out) fail|fail(?:ed|ure)? to (?:obtain|check out) (?:a |the )?license|"
    r"(?:cannot|could not|unable to) (?:obtain|check out|connect to) (?:a |the )?license|"
    r"fatal license error|license server machine is down|licens(?:e|ing).*no (?:such|valid|available) feature|"
    r"\*F,NO(?:V|I|L)LIC|failed to check out.*(?:licen[cs]e|feature)|license not available",
    re.IGNORECASE,
)


def log_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def failure(path, status, message):
    if status == "timeout":
        return {"status": "timeout", "message": message + " timed out"}
    if status == "cancelled":
        return {"status": "cancelled", "message": "Cancelled"}
    text = log_text(path)
    if LICENSE_ERROR.search(text):
        return {"status": "license_error", "message": "EDA license checkout failed"}
    return {"status": "compile_error" if path.name == "compile.log" else "tool_error",
            "message": message + " exited with status {}".format(status)}


def run_vcs(job, work, evidence, call):
    profile = job["profile"]
    uvm = profile["mode"] == "uvm"
    coverage = bool(profile.get("coverage"))
    vcs = str(Path(os.environ["VERIFICATION_VCS_HOME"]) / "bin/vcs")
    executable = work / "simv"
    config = ["-full64", "-sverilog", "-timescale=1ns/1ps", "-f", profile["filelist"],
              "-top", profile["top"], "-o", str(executable)]
    if uvm:
        config += ["-ntb_opts", "uvm-1.2"]
    if job["variant"] == "mutant":
        config += ["+define+VERIFY_MUTANT"]
    if coverage:
        config += ["-cm", "line+cond+tgl"]
    result = call("version.log", [vcs, "-ID"])
    if result != 0:
        return failure(evidence / "version.log", result, "VCS version probe")
    result = call("compile.log", [vcs] + config)
    if result != 0:
        return failure(evidence / "compile.log", result, "VCS compilation/elaboration")
    if not executable.is_file():
        return {"status": "missing_result", "message": "VCS did not produce the simulation executable"}
    args = [str(executable), "+ntb_random_seed={}".format(job["seed"]),
            "+VERIFY_WAVE={}".format(evidence / "wave.vcd")]
    if uvm:
        args += ["+UVM_TESTNAME=" + job["test"]]
    if coverage:
        args += ["-cm", "line+cond+tgl"]
    result = call("simulation.log", args)
    sim_text = log_text(evidence / "simulation.log")
    if result in ("timeout", "cancelled") or LICENSE_ERROR.search(sim_text):
        return failure(evidence / "simulation.log", result, "Simulation")
    if not uvm and result != 0:
        if re.search(r"\bFatal:|\$fatal\b", sim_text, re.IGNORECASE):
            return {"status": "fail", "message": "SystemVerilog test reported a fatal check"}
        return failure(evidence / "simulation.log", result, "Simulation")
    match = re.search(r"^VERIFY_RESULT (?:COMPLETE|PASS) checked=([1-9]\d*)\s*$", sim_text, re.MULTILINE)
    outcome = {"checksExecuted": int(match.group(1)) if match else 0}
    if uvm:
        severities = {level: re.findall(r"^\s*" + level + r"\s*:\s*(\d+)\s*$", sim_text, re.MULTILINE)
                      for level in ("UVM_ERROR", "UVM_FATAL")}
        if all(severities.values()):
            outcome["uvmErrors"] = int(severities["UVM_ERROR"][-1])
            outcome["uvmFatals"] = int(severities["UVM_FATAL"][-1])
        if outcome.get("uvmErrors", 0) or outcome.get("uvmFatals", 0):
            outcome.update(status="fail", message="UVM reported errors or fatals")
        elif result != 0:
            outcome.update(failure(evidence / "simulation.log", result, "UVM simulation"))
        elif not (all(severities.values()) and match and "[RNTST] Running test " + job["test"] in sim_text):
            outcome.update(status="missing_result", message="UVM test execution, check count or report is missing")
        else:
            outcome.update(status="pass", message="UVM test and scoreboard passed")
    elif match:
        outcome.update(status="pass", message="SystemVerilog checks passed")
    else:
        outcome.update(status="missing_result", message="No executed SystemVerilog checks were reported")

    if coverage:
        functional = re.search(r"^VERIFY_COVERAGE functional=([\d.]+)", sim_text, re.MULTILINE)
        measures = {"functionalPercent": float(functional.group(1)) if functional else None}
        database = work / "simv.vdb"
        if database.is_dir():
            urg = str(Path(vcs).with_name("urg"))
            report_dir = evidence / "coverage"
            coverage_status = call("coverage.log", [
                urg, "-dir", str(database), "-format", "text", "-report", str(report_dir)])
            if coverage_status in ("timeout", "cancelled"):
                return failure(evidence / "coverage.log", coverage_status, "Coverage extraction")
            dashboard = log_text(report_dir / "dashboard.txt")
            rows = re.search(r"\bSCORE\s+LINE\s+COND\s+TOGGLE[^\n]*\n\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", dashboard)
            if rows:
                measures.update(dict(zip(("scorePercent", "linePercent", "conditionPercent", "togglePercent"),
                                         map(float, rows.groups()))))
            groups = log_text(report_dir / "groups.txt")
            group_summary = re.search(r"Total Groups Coverage Summary\s+SCORE\s+WEIGHT\s+([\d.]+)", groups)
            if coverage_status == 0 and group_summary:
                measures["functionalPercent"] = float(group_summary.group(1))
            measures["urgAvailable"] = coverage_status == 0 and bool(dashboard)
        outcome["coverage"] = measures
    return outcome


def ifv_properties(report, expected):
    results = {name: {"name": name, "kind": kind, "status": "unknown"}
               for name, kind in expected.items()}
    for line in report.splitlines():
        match = re.match(r"^\s+[\w.]+\.(\w+)\s*:\s*(.+)$", line)
        if not match or match.group(1) not in expected:
            continue
        name, raw = match.groups()
        kind = expected[name]
        depth = re.match(r"^(?:Pass|Fail|Explored|Bounded)\s*\((\d+)\)", raw)
        if raw.startswith("Pass"):
            status = ("reached" if kind == "cover" else
                      "vacuous" if re.search(r"Trigger:\s*(?:Fail|Not_Run)", raw) else "proven")
        elif raw.startswith("Fail"):
            status = "unreachable" if kind == "cover" else "counterexample"
        elif raw.startswith(("Explored", "Bounded")) and depth:
            status = "bounded_pass"
        elif raw.startswith(("Vacuous", "Vacuity")):
            status = "vacuous"
        else:
            status = "unknown"
        result = {"name": name, "kind": kind, "status": status, "toolStatus": raw.strip()}
        if depth:
            result["depth"] = int(depth.group(1))
        results[name] = result
    return list(results.values())


def run_ifv(job, work, evidence, call):
    profile = job["profile"]
    ifv = str(Path(os.environ["VERIFICATION_IFV_HOME"]) / "tools/bin/ifv")
    args = [ifv, "+64bit", "-f", profile["filelist"], "+top+" + profile["top"],
            "+tcl+" + profile["script"]]
    if job["variant"] == "mutant":
        args += ["+define+VERIFY_MUTANT"]
    result = call("formal.log", args)
    report = log_text(evidence / "formal.log")
    properties = ifv_properties(report, profile["properties"])
    statuses = {prop["status"] for prop in properties}
    if result in ("timeout", "cancelled") or LICENSE_ERROR.search(report):
        return dict(failure(evidence / "formal.log", result, "IFV verification"), properties=properties)
    if "counterexample" in statuses:
        status, message = "fail", "An RTL assertion has a counterexample"
    elif result != 0:
        return dict(failure(evidence / "formal.log", result, "IFV verification"), properties=properties)
    elif "Session Status: Finished" not in report or not any("toolStatus" in prop for prop in properties):
        status, message = "missing_result", "IFV did not finish with a property report"
    elif statuses <= {"proven", "reached"}:
        status, message = "pass", "Required proofs and cover reachability passed"
    elif statuses <= {"proven", "reached", "bounded_pass"}:
        status, message = "bounded", "At least one required property passed only within a bound"
    else:
        status, message = "unknown", "A required property is inconclusive, unreachable or vacuous"
    trace = work / "counterexample/cex.trn"
    if trace.is_file():
        converter = str(Path(ifv).with_name("simvisdbutil"))
        cex_status = call("counterexample.log", [
            converter, "-vcd", str(trace), "-output", str(evidence / "counterexample.vcd")])
        if cex_status == "cancelled":
            return dict(failure(evidence / "counterexample.log", cex_status, "Counterexample export"),
                        properties=properties)
    return {"status": status, "message": message, "properties": properties}
