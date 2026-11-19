#!/usr/bin/env python3
"""Summarize recorded four-state transitions over an exact FSDB interval."""
import argparse
import json
from pathlib import Path

from verification_tools import VerificationClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--file", required=True)
    parser.add_argument("--signal", action="append", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args()
    interval = {k: v for k, v in (("start", args.start), ("end", args.end)) if v is not None}
    job = VerificationClient(args.workspace).run(
        "fsdb_wave", file=args.file, signals=args.signal, **interval
    )
    result = job["result"]
    report = {
        "jobId": job["id"],
        "outcome": result["outcome"],
        "scale": result["scale"],
        "viewerPath": job.get("viewerPath"),
        "signals": [
            {
                "name": lane["name"],
                "status": lane["status"],
                "initial": lane["initial"],
                "changes": len(lane["changes"]),
                "omittedAt": lane.get("omittedAt"),
            }
            for lane in result["lanes"]
        ],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf8")
    print(text)


if __name__ == "__main__":
    main()
