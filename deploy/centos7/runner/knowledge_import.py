"""Stage the user's PDF in the caller's namespace; index it on the native host."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import threading
import uuid

import knowledge
from manual_import import import_manual, write_json


INBOX = Path(os.environ.get("VERIFICATION_KNOWLEDGE_INBOX",
                            str(Path(__file__).resolve().parent.parent / "runtime" / "knowledge-inbox")))
WORKERS = ThreadPoolExecutor(max_workers=1)
ACTIVE = {}
LOCK = threading.Lock()


def stage(path, workspace):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Select a local PDF file")
    source = (Path(workspace) / path).resolve(strict=True)
    if source.suffix.lower() != ".pdf" or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError("Select a regular .pdf file")
    INBOX.mkdir(mode=0o700, parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    job = INBOX / token
    job.mkdir(mode=0o700)
    try:
        with source.open("rb") as reader, (job / "input.pdf").open("xb") as writer:
            header = reader.read(1024)
            if b"%PDF-" not in header:
                raise ValueError("The selected file has no PDF header")
            writer.write(header)
            shutil.copyfileobj(reader, writer, 1024 * 1024)
        write_json(job / "receipt.json", {"jobId": token, "filename": source.name, "status": "indexing"})
    except BaseException:
        shutil.rmtree(str(job))
        raise
    return token


def receipt(job):
    return json.loads((job / "receipt.json").read_text(encoding="utf-8"))


def index(job):
    state = receipt(job)
    try:
        source = import_manual(job / "input.pdf", knowledge.LIBRARY, filename=state["filename"])
        state.update(status="indexed", sourceId=source["id"], sha256=source["sha256"],
                     title=source["title"], pageCount=source["pageCount"])
    except Exception as error:
        state.update(status="failed", error=str(error) or type(error).__name__)
    write_json(job / "receipt.json", state)
    (job / "input.pdf").unlink()
    return state


def status(token, wait=2):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid knowledge import receipt")
    job = INBOX / token
    if job.is_symlink() or not (job / "receipt.json").is_file():
        raise ValueError("Knowledge import receipt was not found")
    with LOCK:
        state = receipt(job)
        if state["status"] != "indexing":
            return state
        future = ACTIVE.get(token)
        if future is None:
            future = WORKERS.submit(index, job)
            ACTIVE[token] = future
    try:
        return future.result(timeout=wait)
    except TimeoutError:
        return receipt(job)
    finally:
        with LOCK:
            for completed in [key for key, item in ACTIVE.items() if item.done()]:
                del ACTIVE[completed]


def resume_pending():
    if INBOX.is_dir():
        for job in INBOX.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", job.name) and (job / "receipt.json").is_file():
                try:
                    if receipt(job).get("status") == "indexing":
                        status(job.name, wait=0)
                except (OSError, ValueError, KeyError) as error:
                    print("Could not recover import {}: {}".format(job.name, error), file=sys.stderr)


if __name__ == "__main__":
    # Both desktop and MCP resolve the selected file in the caller's mount namespace.
    print(stage(sys.argv[1], os.getcwd()), flush=True)

