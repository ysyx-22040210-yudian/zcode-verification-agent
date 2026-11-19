"""Build an offline Formal kit using only the checked-in lock and the Python stdlib."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

HERE = Path(__file__).resolve().parent
DEPLOY = HERE.parent / "centos7"
LOCK = json.loads((HERE / "toolchain.lock.json").read_text(encoding="utf-8"))


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def fetch(item, cache, offline):
    path = cache / item["file"]
    if not path.exists():
        if offline:
            raise ValueError("Missing cached source: " + path.name)
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as target:
            tmp = Path(target.name)
            try:
                with urlopen(item["url"], timeout=90) as stream:
                    shutil.copyfileobj(stream, target)
            except BaseException:
                target.close()
                tmp.unlink()
                raise
        if digest(tmp) != item["sha256"]:
            tmp.unlink()
            raise ValueError("Checksum mismatch: " + path.name)
        os.replace(tmp, path)
    if digest(path) != item["sha256"]:
        raise ValueError("Checksum mismatch: " + path.name)
    return path


def add_stream(out, name, source, executable=False):
    name = PurePosixPath(name)
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("Invalid archive path")
    info = zipfile.ZipInfo(name.as_posix())
    info.create_system = 3
    info.external_attr = (0o100755 if executable else 0o100644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with out.open(info, "w") as target:
        shutil.copyfileobj(source, target)


def build(target, archive, cache, offline):
    windows = target == "win-x64"
    site = "formal-toolchain/python/" + ("Lib" if windows else "lib/python3.11") + "/site-packages/"
    with zipfile.ZipFile(archive, "w") as out:
        for key, item in LOCK["packages"].items():
            if target not in item["targets"]:
                continue
            path = fetch(item, cache, offline)
            if key.startswith("cpython-"):
                # A seekable tar avoids decompressing the entire interpreter again for every symlink.
                with tempfile.TemporaryFile() as unpacked, gzip.open(path, "rb") as compressed:
                    shutil.copyfileobj(compressed, unpacked)
                    unpacked.seek(0)
                    with tarfile.open(fileobj=unpacked, mode="r:") as python:
                        add_python(out, python)
            elif path.suffix == ".whl":
                with zipfile.ZipFile(path) as wheel:
                    for name in wheel.namelist():
                        if name.endswith("/") or name.endswith(".pyc"):
                            continue
                        if key.startswith("z3-solver"):
                            if name.endswith(("/bin/z3", "/bin/z3.exe")):
                                dest = "formal-toolchain/bin/" + PurePosixPath(name).name
                            elif ".dist-info/" in name:
                                dest = site + name
                            else:
                                continue
                        else:
                            dest = site + name
                        with wheel.open(name) as source:
                            add_stream(out, dest, source, dest.startswith("formal-toolchain/bin/"))
            else:
                with path.open("rb") as source:
                    add_stream(out, "formal-toolchain/licenses/" + item["file"], source)
        sources = [(p, "runner/" + p.relative_to(DEPLOY / "runner").as_posix())
                   for p in (DEPLOY / "runner").rglob("*") if p.is_file() and "__pycache__" not in p.parts
                   and not p.name.startswith("test_") and p.suffix != ".pyc"]
        sources += [(p, "fifo/" + p.relative_to(DEPLOY / "fifo").as_posix())
                    for p in (DEPLOY / "fifo").rglob("*") if p.is_file()]
        sources += [(p, p.relative_to(HERE).as_posix())
                    for p in [HERE / "portable.py", HERE / "README.md", HERE / "zcode-formal",
                              HERE / "zcode-formal.cmd", HERE / "adapters/registry.example.json"]]
        sources += [(HERE / "toolchain.lock.json", "formal-toolchain/toolchain.lock.json"),
                    (HERE.parents[1] / "LICENSE", "LICENSE")]
        for path, name in sorted(sources, key=lambda pair: pair[1]):
            with path.open("rb") as source:
                add_stream(out, name, source, name == "zcode-formal" or name.endswith(".sh"))


def add_python(out, python):
    for member in python:
        name = member.name
        if member.isdir() or "/__pycache__/" in name or "/site-packages/" in name:
            continue
        if not (member.isfile() or member.issym() or member.islnk()):
            continue
        # Only the interpreter, its standard library, shared libraries and notices are needed.
        if any(part in name.split("/") for part in ("include", "Include", "tcl", "tkinter", "test", "idlelib", "ensurepip", "turtledemo")):
            continue
        if name.endswith((".a", ".lib", ".pdb", ".pyc")):
            continue
        with python.extractfile(member) as source:
            add_stream(out, "formal-toolchain/" + name, source, bool(member.mode & 0o111))


def install(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as contents:
        for member in contents.infolist():
            path = Path(contents.extract(member, destination))
            if os.name != "nt":
                path.chmod((member.external_attr >> 16) & 0o777)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["linux-x64", "win-x64"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "zcode-formal-build")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--install", type=Path, help="also extract for a desktop package or local test")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as staging:
        output = Path(staging) / "kit.zip"
        build(args.target, output, args.cache, args.offline)
        os.replace(output, args.output)
    if args.install:
        install(args.output, args.install)
    print(digest(args.output), args.output)

