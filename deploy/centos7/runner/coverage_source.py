"""Identify VCS databases and preserve source fields outside the NPI coverage model."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import xml.etree.ElementTree as ET
import zipfile

from project import require


def database(workspace, jobs, request):
    name, run_id = request.get("path"), request.get("runId")
    require(bool(name) != bool(run_id), "Select a .vdb path or a verification run")
    if run_id:
        run = jobs.find(workspace, run_id)
        from jobs import load

        require(load(run)["status"] not in ("queued", "running"), "The simulation is still writing its VDB")
        path = run.parent / "work" / "simv.vdb"
    else:
        require(isinstance(name, str) and len(name) <= 4096 and "\0" not in name, "Invalid VDB path")
        path = (workspace / name).resolve()
    require(path.exists(), "Coverage database does not exist: " + str(path))
    path = next((p for p in (path, *path.parents) if p.is_dir() and p.suffix.lower() == ".vdb"), None)
    require(path is not None and (path / "snps/coverage/db").is_dir(), "Select a VCS .vdb coverage database")
    options = {"database": str(path), "timeoutSeconds": request.get("timeoutSeconds", 3600)}
    require(
        type(options["timeoutSeconds"]) is int and 1 <= options["timeoutSeconds"] <= 86400,
        "Invalid timeoutSeconds",
    )
    if run_id:
        options["runId"] = run_id
    if request.get("excludeFile"):
        ex = request["excludeFile"]
        require(isinstance(ex, str) and len(ex) <= 4096 and "\0" not in ex, "Invalid exclusion path")
        path = (workspace / ex).resolve()
        require(path.is_file(), "Exclusion file does not exist")
        options["excludeFile"] = str(path)
    return options


def inventory(root):
    """Visit referenced file contents, including linked directories, and reject cycles."""
    rows = {}

    def walk(folder, ancestors):
        st = folder.stat()
        key = st.st_dev, st.st_ino
        require(key not in ancestors, "Coverage database contains a directory link cycle")
        for child in sorted(folder.iterdir()):
            info = child.stat()
            if stat.S_ISDIR(info.st_mode):
                walk(child, ancestors | {key})
            else:
                require(stat.S_ISREG(info.st_mode), "Unsupported coverage database member: " + str(child))
                rows[child.relative_to(root).as_posix()] = (
                    info.st_dev,
                    info.st_ino,
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                )

    walk(root, set())
    require(rows, "The coverage database is empty")
    return rows


def digest_inventory(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_xml(source, output, member):
    stack = []
    count = 0
    for event, node in ET.iterparse(source, events=("start", "end")):
        if event == "start":
            count += 1
            stack.append((count, node))
            continue
        idx, current = stack.pop()
        row = {
            "member": member,
            "node": idx,
            "parent": stack[-1][0] if stack else None,
            "tag": current.tag,
            "attributes": current.attrib,
            "text": current.text,
            "tail": current.tail,
        }
        output.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf8"))
        if stack:
            stack[-1][1].remove(current)
        current.clear()
    return count


def export_source(root, directory, files):
    archive = directory / "source-vdb.zip"
    xml = directory / "vdb-xml.jsonl"
    manifest = directory / "source-manifest.json"
    members, nodes, xml_errors = [], 0, 0
    with zipfile.ZipFile(str(archive), "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as db:
        for name in files:
            sha = hashlib.sha256()
            with (root / name).open("rb") as src, db.open(name, "w", force_zip64=True) as out:
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    sha.update(chunk)
                    out.write(chunk)
            members.append({"path": name, "bytes": files[name][2], "sha256": sha.hexdigest()})
    with zipfile.ZipFile(str(archive)) as db, xml.open("wb") as out:
        for info in members:
            name = info["path"]
            if not name.lower().endswith((".xml", ".xml.gz")):
                continue
            offset = out.tell()
            try:
                with db.open(name) as src:
                    signature = src.read(2)
                with db.open(name) as src:
                    if signature == b"\x1f\x8b":
                        with gzip.GzipFile(fileobj=src) as stream:
                            count = write_xml(stream, out, name)
                    else:
                        count = write_xml(src, out, name)
                info["xmlNodes"] = count
                nodes += count
            except (ET.ParseError, EOFError, OSError, LookupError) as err:
                if isinstance(err, OSError) and err.errno is not None:
                    raise
                # Preserve the original bytes and report this member separately.
                out.seek(offset)
                out.truncate()
                info["xmlError"] = str(err)
                xml_errors += 1
    manifest.write_text(json.dumps(members, ensure_ascii=False, indent=2), encoding="utf8")
    return {
        "sourceArchive": str(archive),
        "manifestPath": str(manifest),
        "xmlPath": str(xml),
        "sourceFiles": len(files),
        "xmlNodes": nodes,
        "xmlErrors": xml_errors,
    }
