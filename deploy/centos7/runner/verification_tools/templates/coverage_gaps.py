#!/usr/bin/env python3
"""Count missed VDB records by kind with example scope paths and their native query ID."""
import argparse
from collections import Counter
import json
from pathlib import Path

from verification_tools import VerificationClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database")
    source.add_argument("--job-id", help="Reuse an existing coverage extraction in this project")
    parser.add_argument("--view", help="Native view ID, e.g. test-1 or merged")
    parser.add_argument("--metric", default="")
    parser.add_argument("--kind", default="")
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    client = VerificationClient(args.workspace)
    job = (
        client.run("coverage_extract", path=args.database)
        if args.database
        else client.call("coverage_get", jobId=args.job_id)
    )
    if job["status"] != "complete":
        parser.error("Coverage extraction {} is {}".format(job["id"], job["status"]))
    views = [v["id"] for v in job["result"]["views"]]
    if not views:
        parser.error("No coverage views in extraction " + job["id"])
    view = args.view or ("merged" if "merged" in views else views[0])
    if view not in views:
        parser.error("Unknown coverage view; available: " + ", ".join(views))
    counts = Counter()
    examples = []
    for row in client.coverage_rows(
        job["id"], view=view, metric=args.metric, kind=args.kind, state="missed", limit=args.page_size
    ):
        counts[row["kind"]] += 1
        if len(examples) < 10:
            examples.append(row["scope"])
    print(
        json.dumps(
            {
                "jobId": job["id"],
                "view": view,
                "count": sum(counts.values()),
                "byKind": dict(counts),
                "examples": examples,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
