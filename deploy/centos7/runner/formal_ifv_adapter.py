"""Cadence IFV reference implementation of the external JSON adapter protocol."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from engines import log_text, run_ifv


def main(request, result):
    data = json.loads(request.read_text(encoding="utf-8"))
    work, artifacts = Path(data["workDir"]), Path(data["artifactsDir"])
    commands = []

    def call(name, argv):
        commands.append({"argv": argv, "log": name})
        with (artifacts / name).open("wb") as stream:
            return subprocess.call(argv, cwd=str(work), stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT)

    report = {"protocolVersion": 1, "runId": data["runId"]}
    try:
        outcome = run_ifv(data, work, artifacts, call)
        if outcome["status"] in ("pass", "fail", "bounded", "unknown"):
            text = log_text(artifacts / "formal.log")
            match = re.search(r"(?:IFV|ifv|ncvlog|ncelab)(?:\(64\))?\s*:\s*(?:Version\s+)?([0-9][\w.()-]*)", text, re.I)
            if not match:
                exe = str(Path(os.environ["VERIFICATION_IFV_HOME"]) / "tools/bin/ifv")
                call("version.log", [exe, "-version"])
                match = re.search(r"\b(\d{2}\.\d+[\w.()-]*)", log_text(artifacts / "version.log"))
            report["tool"] = {"name": "IFV", "version": match.group(1) if match else ""}
            report["properties"] = outcome["properties"]
        else:
            report["error"] = {"status": outcome["status"], "message": outcome["message"]}
    except (OSError, KeyError) as error:
        report["error"] = {"status": "tool_error", "message": str(error)}
    (artifacts / "ifv-commands.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
    report["artifacts"] = sorted(p.name for p in artifacts.iterdir() if p.is_file())
    result.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))

