#!/usr/bin/env python3
"""Import a PDF into the native knowledge library using PyMuPDF."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid


def write_json(path, value):
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.replace(str(temporary), str(path))


@contextmanager
def catalog_writer(library):
    # SQLite releases the interprocess lock even if the importer is terminated.
    conn = sqlite3.connect(str(library / ".catalog-lock.sqlite3"), timeout=20)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
    finally:
        conn.close()


def load_catalog(library):
    path = library / "catalog.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"format": 1, "sources": []}


def reusable(catalog, library, digest, source_id):
    return next((item for item in catalog["sources"]
                 if (source_id is None or item["id"] == source_id) and item["sha256"] == digest
                 and item.get("indexFormat") == "fts4-simple-v1"
                 and all((library / item["generation"] / name).is_file()
                         for name in ("index.sqlite3", "source.pdf"))), None)


def import_manual(pdf, library, source_id=None, title=None, version=None, filename=None):
    import fitz

    if source_id is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", source_id):
        raise ValueError("Use a lowercase source ID containing letters, digits and hyphens")
    pdf = pdf.resolve(strict=True)
    library.mkdir(parents=True, exist_ok=True)
    filename = filename or pdf.name
    documents = library / "documents"
    documents.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".import-", dir=str(documents)))
    try:
        checksum = hashlib.sha256()
        retained = staging / "source.pdf"
        with pdf.open("rb") as reader, retained.open("wb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                checksum.update(chunk)
                writer.write(chunk)
        digest = checksum.hexdigest()
        previous = reusable(load_catalog(library), library, digest, source_id)
        if previous:
            return previous
        with fitz.open(str(retained)) as document:
            if document.needs_pass:
                raise ValueError("The PDF requires a password")
            if not document.is_pdf or not len(document):
                raise ValueError("Select a PDF with at least one page")
            first_page = document[0].get_text(sort=True)
            version_match = re.search(r"\bVersion\s+([^,\n]+)", first_page)
            source_title = title or document.metadata.get("title") or Path(filename).stem
            source_version = version or (version_match.group(1).strip() if version_match else "")
            outline = [{"level": level, "title": heading.strip(), "page": page}
                       for level, heading, page in document.get_toc()
                       if 1 <= page <= len(document) and heading.strip()]
            outline.sort(key=lambda item: item["page"])
            connection = sqlite3.connect(str(staging / "index.sqlite3"))
            try:
                connection.executescript("""
                    PRAGMA journal_mode=DELETE;
                    CREATE TABLE pages (page INTEGER PRIMARY KEY, label TEXT NOT NULL,
                                        section TEXT NOT NULL, text TEXT NOT NULL);
                    CREATE VIRTUAL TABLE search USING fts4(heading, text, tokenize=simple);
                """)
                cursor = 0
                section = []
                empty_pages = []
                characters = 0
                for index, page in enumerate(document):
                    number = index + 1
                    headings = []
                    while cursor < len(outline) and outline[cursor]["page"] <= number:
                        item = outline[cursor]
                        section = [part for part in section if part[0] < item["level"]]
                        section.append((item["level"], item["title"]))
                        if item["page"] == number:
                            headings.append(item["title"])
                        cursor += 1
                    text = page.get_text(sort=True).replace("\x00", "").strip()
                    breadcrumb = " > ".join(part[1] for part in section)
                    if not text:
                        empty_pages.append(number)
                    characters += len(text)
                    connection.execute("INSERT INTO pages VALUES (?, ?, ?, ?)",
                                       (number, page.get_label() or str(number), breadcrumb, text))
                    heading = breadcrumb + " | " + " | ".join(headings)
                    connection.execute("INSERT INTO search(docid, heading, text) VALUES (?, ?, ?)",
                                       (number, heading, text))
                connection.commit()
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("The new page index failed its integrity check")
            finally:
                connection.close()
            generation = "documents/" + uuid.uuid4().hex
            source = {
                "id": source_id or ("pdf-" + digest[:48]), "title": source_title, "version": source_version,
                "filename": filename, "pageCount": len(document), "sha256": digest,
                "pdfBytes": retained.stat().st_size, "textCharacters": characters,
                "emptyPages": empty_pages, "generation": generation, "indexFormat": "fts4-simple-v1",
                "chapters": [{"title": item["title"], "page": item["page"]}
                             for item in outline if item["level"] == 1],
            }
        with catalog_writer(library):
            catalog = load_catalog(library)
            previous = reusable(catalog, library, digest, source_id)
            if previous:
                return previous
            os.replace(str(staging), str(library / generation))
            staging = None
            catalog["sources"] = [item for item in catalog["sources"] if item["id"] != source["id"]] + [source]
            write_json(library / "catalog.json", catalog)
        return source
    finally:
        if staging is not None:
            shutil.rmtree(str(staging))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--id", help="Optional stable ID for an administratively managed manual")
    parser.add_argument("--title")
    parser.add_argument("--version")
    args = parser.parse_args()
    source = import_manual(args.pdf, args.library, args.id, args.title, args.version)
    print(json.dumps({key: source[key] for key in (
        "id", "title", "version", "pageCount", "sha256", "textCharacters", "emptyPages")},
        ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
