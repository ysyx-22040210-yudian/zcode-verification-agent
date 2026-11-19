#!/usr/bin/env python3
"""List FSDB files, find signals and extract a native ZCode waveform window."""
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
    parser.add_argument("operation", choices=["files", "signals", "wave", "status"])
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--file")
    parser.add_argument("--pattern", default="*")
    parser.add_argument("--signal", action="append", help="Full signal name. Repeat for more traces.")
    parser.add_argument("--start", help="First tick, inclusive")
    parser.add_argument("--end", help="Last tick, inclusive")
    parser.add_argument("--trigger", help="Trigger signal")
    parser.add_argument("--edge", choices=["rising", "falling", "change"], default="rising")
    parser.add_argument("--from", dest="trigger_from", default="0")
    parser.add_argument("--before", default="0")
    parser.add_argument("--after", default="0")
    parser.add_argument("--max-changes", type=int, default=512)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--id", dest="job_id")
    parser.add_argument("--submit-only", action="store_true")
    args = parser.parse_args()
    endpoint = os.environ.get("ZCODE_VERIFICATION_SOCKET", str(BASE / "runtime" / "verification.sock"))
    workspace = str(Path(args.workspace).resolve())

    def request(action, **fields):
        return call(endpoint, dict(fields, workspace=workspace, action=action))

    if args.operation == "files":
        result = request("fsdbFiles")
    elif args.operation == "status":
        result = request("fsdbGet", jobId=args.job_id)
    else:
        query = dict(operation=args.operation, file=args.file)
        if args.operation == "signals":
            query.update(pattern=args.pattern, limit=args.limit)
        else:
            query.update(signals=args.signal, start=args.start, end=args.end, maxChanges=args.max_changes)
            if args.trigger:
                query["trigger"] = {
                    "signal": args.trigger,
                    "edge": args.edge,
                    "from": args.trigger_from,
                    "before": args.before,
                    "after": args.after,
                }
        result = request("fsdbStart", **query)
        while not args.submit_only and result["status"] in ("queued", "running"):
            time.sleep(0.4)
            result = request("fsdbGet", jobId=result["id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status", "complete") in ("queued", "running", "complete") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as err:
        sys.exit(str(err))
