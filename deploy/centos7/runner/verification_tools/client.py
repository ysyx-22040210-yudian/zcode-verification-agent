"""Python client for the same named operations and workspace evidence used by the Agent."""
import json
import os
from pathlib import Path
import socket
import time

from .operations import METHODS, STATUS_METHOD, prepare


def call(endpoint, payload):
    if Path(endpoint).suffix == ".json":
        descriptor = json.loads(Path(endpoint).read_text(encoding="utf-8"))
        if descriptor.get("version") != 1:
            raise ValueError("Unsupported local verification endpoint")
        family, address = socket.AF_INET, ("127.0.0.1", descriptor["port"])
        payload = dict(payload, auth=descriptor["token"])
    else:
        family, address = socket.AF_UNIX, str(endpoint)
    with socket.socket(family, socket.SOCK_STREAM) as client:
        client.settimeout(20)
        client.connect(address)
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        with client.makefile("rb") as reply:
            parsed = json.loads(reply.readline().decode("utf-8"))
    if "error" in parsed:
        raise ValueError(parsed["error"])
    return parsed["result"]


class VerificationJobError(RuntimeError):
    def __init__(self, job):
        self.job = job
        super().__init__(
            "{}: {}: {}".format(job["id"], job["status"], job.get("message") or "see evidence")
        )


class VerificationClient:
    """Run locally in the VM or its desktop runtime. Paths and receipts belong to this workspace."""

    def __init__(self, workspace=".", socket_path=None):
        self.workspace = str(Path(workspace).resolve())
        base = Path(__file__).resolve().parents[2]
        self.endpoint = (
            socket_path
            or os.environ.get("ZCODE_VERIFICATION_SOCKET")
            or base / "runtime/verification.sock"
        )

    def call(self, method, **arguments):
        """Perform one native method call. A submitted job may still be queued or running."""
        if method not in METHODS:
            raise ValueError("Unknown verification method: " + str(method))
        action, fields = prepare(method, arguments)
        return call(self.endpoint, dict(fields, workspace=self.workspace, action=action))

    def run(self, method, **arguments):
        """Submit once, follow the original receipt, and return the complete job with its native outcome."""
        if method not in STATUS_METHOD:
            raise ValueError("Choose a query submission method for run(): " + str(method))
        job = self.call(method, **arguments)
        while job["status"] in ("queued", "running"):
            time.sleep(0.4)
            job = self.call(STATUS_METHOD[method], jobId=job["id"])
        if job["status"] != "complete":
            raise VerificationJobError(job)
        return job

    def coverage_rows(self, job_id, **filters):
        """Yield native coverage rows with their stable IDs until nextAfter is null."""
        offset = filters.pop("after", 0)
        while True:
            page = self.call("coverage_rows", jobId=job_id, after=offset, **filters)
            yield from page["rows"]
            following = page["nextAfter"]
            if following is None:
                return
            if following <= offset:
                raise ValueError("Coverage cursor did not advance")
            offset = following
