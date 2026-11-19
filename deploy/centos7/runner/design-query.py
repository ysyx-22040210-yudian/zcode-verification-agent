#!/usr/bin/env python3
"""Run and inspect the same native NPI queries as the ZCode desktop."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "runtime" / "python"))
from server import call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["instances", "signal", "status"])
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--definition", help="Module definition pattern (* and ?)")
    parser.add_argument("--instance", help="Full instance path pattern (* and ?)")
    parser.add_argument("--scope", help="Restrict instance search to this exact hierarchy and descendants")
    parser.add_argument("--signal", help="Hierarchical signal or bound interface member path")
    parser.add_argument("--direction", choices=["driver", "load", "both"])
    parser.add_argument("--kdb", help="Compiled VCS simv.kdb file, simv.daidir or kdb.elab++ directory")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, dest="timeoutSeconds")
    parser.add_argument("--id", dest="jobId", help="Query ID for status")
    parser.add_argument("--submit-only", action="store_true")
    args = parser.parse_args()
    endpoint = os.environ.get("ZCODE_VERIFICATION_SOCKET", str(BASE / "runtime" / "verification.sock"))
    workspace = str(Path(args.workspace).resolve())
    query = {k: v for k, v in vars(args).items() if v is not None and k not in ("submit_only", "workspace")}
    if args.operation == "status":
        if not args.jobId:
            parser.error("status requires --id")
        job = call(endpoint, dict(action="designQueryGet", workspace=workspace, jobId=args.jobId))
    else:
        if not args.kdb:
            parser.error(args.operation + " requires --kdb (compiled VCS KDB)")
        job = call(endpoint, dict(query, workspace=workspace, action="designQueryStart"))
        while not args.submit_only and job["status"] in ("running", "queued"):
            time.sleep(.4)
            job = call(endpoint, dict(action="designQueryGet", workspace=workspace, jobId=job["id"]))
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0 if job["status"] in ("running", "queued", "complete") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(str(error))

