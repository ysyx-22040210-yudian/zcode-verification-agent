#!/usr/bin/env python3
"""Local verification service shared by the ZCode service and MCP adapters."""
import argparse
import hmac
import json
import os
import secrets
import socketserver
import sys
import tempfile
from pathlib import Path

from verification_tools.client import call
from verification_tools.catalog import catalog, scaffold
from jobs import Jobs, load
import fsdb
import coverage_store
import knowledge
import knowledge_import
from npi_query import DesignQueries
from project import require


MAX_REQUEST = 1024 * 1024


def dispatch(jobs, request):
    require(isinstance(request, dict), "Invalid verification request")
    action = request.get("action")
    if action == "health":
        return {"ok": True}
    if action in ("toolCatalog", "toolScaffold"):
        workspace = jobs.workspace(request.get("workspace"))
        return catalog(request) if action == "toolCatalog" else scaffold(workspace, request.get("toolId"))
    if action in ("coverageStart", "coverageGet", "coverageRows"):
        workspace = jobs.workspace(request.get("workspace"))
        if action == "coverageStart":
            return jobs.design_queries.start(workspace, request, kind="coverage")
        record = jobs.design_queries.get(workspace, request.get("jobId"), kind="coverage")
        return coverage_store.page(record, request) if action == "coverageRows" else record
    if action == "fsdbArtifact":
        workspace = jobs.workspace(request.get("workspace"))
        run = jobs.find(workspace, request.get("runId"))
        name = request.get("name")
        require(isinstance(name, str) and name.lower().endswith(".fsdb") and
                any(a["name"] == name for a in load(run)["artifacts"]), "Unknown FSDB artifact")
        evidence = run.parent / "evidence"
        target = (evidence / name).resolve()
        require(evidence in target.parents and target.is_file(), "Missing FSDB artifact")
        return {"path": str(target)}
    if action in ("fsdbFiles", "fsdbStart", "fsdbGet", "fsdbViewer"):
        workspace = jobs.workspace(request.get("workspace"))
        if action == "fsdbFiles":
            return fsdb.list_files(jobs, workspace)
        if action == "fsdbStart":
            return jobs.design_queries.start(workspace, request, kind="fsdb")
        record = jobs.design_queries.get(workspace, request.get("jobId"), kind="fsdb")
        if action == "fsdbViewer":
            return {"html": fsdb.viewer(record)}
        return record
    if action in ("designQueryStart", "designQueryGet"):
        workspace = jobs.workspace(request.get("workspace"))
        if action == "designQueryStart":
            return jobs.design_queries.start(workspace, request)
        return jobs.design_queries.get(workspace, request.get("jobId"))
    if action == "knowledgeImportStatus":
        return knowledge_import.status(request.get("jobId"))
    if action in ("knowledgeList", "knowledgeSearch", "knowledgeRead", "knowledgePdfRange", "knowledgeOriginal",
                  "knowledgeArchiveNext", "knowledgeArchiveSave", "knowledgeGuide"):
        return knowledge.dispatch(action, request)
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
            request = json.loads(data.decode("utf-8"))
            token = getattr(self.server, "token", None)
            if token is not None:
                received = request.pop("auth", None) if isinstance(request, dict) else None
                require(isinstance(received, str) and hmac.compare_digest(received.encode("utf-8"), token.encode("ascii")),
                        "Invalid local endpoint credentials")
            payload = {"result": dispatch(self.server.jobs, request)}
        except (ValueError, OSError, KeyError, TypeError, knowledge.sqlite3.DatabaseError) as error:
            payload = {"error": str(error)}
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")


def listen(endpoint):
    if endpoint.suffix == ".json":
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        server.token = secrets.token_hex(32)
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=str(endpoint.parent), delete=False) as target:
                json.dump({"version": 1, "port": server.server_address[1], "token": server.token}, target)
            os.replace(target.name, str(endpoint))
        except BaseException:
            server.server_close()
            raise
        return server

    class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        pass

    if endpoint.exists():
        endpoint.unlink()
    server = UnixServer(str(endpoint), Handler)
    endpoint.chmod(0o600)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--call", action="store_true")
    args = parser.parse_args()
    if args.call:
        print(json.dumps(call(args.socket, json.load(sys.stdin)), indent=2, ensure_ascii=True))
        return
    if not args.runs:
        parser.error("--runs is required when serving")
    with args.socket.with_suffix(".lock").open("a") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("Verification runner is already serving")
        with listen(args.socket) as server:
            server.daemon_threads = True
            server.jobs = Jobs(args.runs)
            server.jobs.design_queries = DesignQueries(server.jobs)
            knowledge_import.resume_pending()
            print("Verification service ready", flush=True)
            try:
                server.serve_forever()
            finally:
                args.socket.unlink()


if __name__ == "__main__":
    main()
