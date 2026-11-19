#!/usr/bin/env python3
"""Export source locations of drivers and loads for a hierarchical RTL or interface signal."""
import argparse
import csv
from pathlib import Path
import sys

from verification_tools import VerificationClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--signal", required=True)
    parser.add_argument("--kdb", required=True, help="Compiled simv.kdb, simv.daidir or kdb.elab++")
    args = parser.parse_args()
    job = VerificationClient(args.workspace).run(
        "design_query", operation="signal", signal=args.signal, direction="both", kdb=args.kdb
    )
    result = job["result"]
    print(
        "Query {} · {} · truncated={}".format(job["id"], result["outcome"], result["truncated"]),
        file=sys.stderr,
    )
    for warning in result["warnings"]:
        print(warning, file=sys.stderr)
    writer = csv.writer(sys.stdout)
    writer.writerow(["direction", "scope", "name", "kind", "file", "line"])
    for direction, group in (("driver", "drivers"), ("load", "loads")):
        for row in result[group]:
            writer.writerow([direction, row["scope"], row["name"], row["kind"], row["file"], row["line"]])


if __name__ == "__main__":
    main()
