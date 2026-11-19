#!/usr/bin/env python3
"""Extract and read Verdi NPI coverage using the ZCode verification runner."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "runtime/python"))
from server import call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    sub = parser.add_subparsers(dest="command")
    extract = sub.add_parser("extract")
    source = extract.add_mutually_exclusive_group(required=True)
    source.add_argument("--path")
    source.add_argument("--run-id", dest="runId")
    extract.add_argument("--exclude-file", dest="excludeFile")
    extract.add_argument("--timeout", type=int, dest="timeoutSeconds")
    extract.add_argument("--submit-only", action="store_true")
    sub.add_parser("get").add_argument("jobId")
    rows = sub.add_parser("rows")
    rows.add_argument("jobId")
    for key in ("view", "metric", "kind", "state", "search"):
        rows.add_argument("--" + key)
    rows.add_argument("--after", type=int)
    rows.add_argument("--limit", type=int)
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command is None:
        parser.error("Choose extract, get or rows")
    submit_only = args.pop("submit_only", False)
    workspace = str(Path(args.pop("workspace")).resolve())
    endpoint = os.environ.get("ZCODE_VERIFICATION_SOCKET", str(BASE / "runtime/verification.sock"))

    def rpc(action, **fields):
        return call(endpoint, dict(fields, workspace=workspace, action=action))

    args = {k: v for k, v in args.items() if v is not None}
    result = rpc({"extract": "coverageStart", "get": "coverageGet", "rows": "coverageRows"}[command], **args)
    while command == "extract" and not submit_only and result["status"] in ("queued", "running"):
        time.sleep(0.4)
        result = rpc("coverageGet", jobId=result["id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status", "complete") in ("queued", "running", "complete") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(str(error))
