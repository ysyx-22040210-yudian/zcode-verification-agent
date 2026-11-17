#!/usr/bin/env python3
"""Local verification service shared by the ZCode service and MCP adapters."""
import argparse
import fcntl
import json
import os
import socket
import socketserver
import sys
from pathlib import Path

from jobs import Jobs, load
from project import require


MAX_REQUEST = 1024 * 1024


def dispatch(jobs, request):
    require(isinstance(request, dict), "Invalid verification request")
    action = request.get("action")
    if action == "health":
        return {"ok": True}
    with jobs.lock:
        workspace = jobs.workspace(request.get("workspace"))
        if action in ("inspect", "advance"):
            return jobs.inspect(workspace, advance=action == "advance")
        if action == "submit":
            return jobs.submit(workspace, request)
        path = jobs.find(workspace, request.get("runId"))
        if action == "get":
            return load(path)
        if action == "cancel":
            return jobs.cancel(path)
        if action == "rerun":
            return jobs.submit(workspace, request, previous=path)
        if action == "readArtifact":
            return jobs.artifact(path, request.get("name"), request.get("offset", 0))
        raise ValueError("Unknown verification action")


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(7)
        try:
            data = self.rfile.readline(MAX_REQUEST + 1)
            if not data:
                return
            require(len(data) <= MAX_REQUEST, "Verification request is too large")
            payload = {"result": dispatch(self.server.jobs, json.loads(data.decode("utf-8")))}
        except (ValueError, OSError, KeyError, TypeError) as error:
            payload = {"error": str(error)}
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, endpoint, jobs):
        self.jobs = jobs
        super().__init__(str(endpoint), Handler)


def call(endpoint, payload):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(20)
        client.connect(str(endpoint))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        with client.makefile("rb") as reply:
            parsed = json.loads(reply.readline().decode("utf-8"))
    if "error" in parsed:
        raise ValueError(parsed["error"])
    return parsed["result"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--call", action="store_true")
    args = parser.parse_args()
    if args.call:
        print(json.dumps(call(args.socket, json.load(sys.stdin)), indent=2, ensure_ascii=False))
        return
    if not args.runs:
        parser.error("--runs is required when serving")
    with args.socket.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("Verification runner is already serving")
        if args.socket.exists():
            args.socket.unlink()
        with UnixServer(args.socket, Jobs(args.runs)) as server:
            args.socket.chmod(0o600)
            print("Verification service ready", flush=True)
            try:
                server.serve_forever()
            finally:
                args.socket.unlink()


if __name__ == "__main__":
    main()
