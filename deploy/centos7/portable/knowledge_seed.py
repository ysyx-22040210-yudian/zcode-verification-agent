"""Copy selected, versioned documents between verification knowledge libraries."""
from contextlib import closing
import hashlib
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid


def copy_sources(source, destination, ids=None):
    from manual_import import catalog_writer, load_catalog, write_json

    sources = load_catalog(source)["sources"]
    if ids is not None:
        sources = [item for item in sources if item["id"] in ids]
        if {item["id"] for item in sources} != set(ids):
            raise ValueError("A requested knowledge source does not exist")
    destination.mkdir(parents=True, exist_ok=True)
    with catalog_writer(destination):
        catalog = load_catalog(destination)
        existing = {item["id"] for item in catalog["sources"]}
        documents = destination / "documents"
        for item in sources:
            if item["id"] in existing:
                continue
            if not re.fullmatch(r"documents/[0-9a-f]{32}", item["generation"]):
                raise ValueError("Invalid source generation")
            origin = (source / item["generation"]).resolve(strict=True)
            if origin.parent != (source / "documents").resolve():
                raise ValueError("Source generation is outside the knowledge library")
            documents.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=documents) as work:
                staged = Path(work) / "document"
                staged.mkdir()
                pdf = staged / "source.pdf"
                shutil.copyfile(origin / pdf.name, pdf)
                with pdf.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                        raise ValueError("Knowledge PDF digest differs from its catalog")
                for name in ("index.sqlite3", "guide.sqlite3"):
                    database = origin / name
                    if name == "guide.sqlite3" and not database.exists():
                        continue
                    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as reader:
                        with closing(sqlite3.connect(staged / name)) as writer:
                            reader.backup(writer)
                generation = documents / uuid.uuid4().hex
                staged.rename(generation)
            catalog["sources"].append(dict(item, generation="documents/" + generation.name))
            write_json(destination / "catalog.json", catalog)
            existing.add(item["id"])


if __name__ == "__main__":
    runner, source, destination, *ids = sys.argv[1:]
    sys.path.insert(0, runner)
    copy_sources(Path(source), Path(destination), ids)
