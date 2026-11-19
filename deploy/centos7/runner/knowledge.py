"""Read-only reference manuals shared by native desktop and Agent MCP."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import struct

from original_document import read_pages
import model_archive


LIBRARY = Path(os.environ.get("VERIFICATION_KNOWLEDGE_DIR", str(Path(__file__).resolve().parent.parent / "knowledge")))
TOPICS = {
    "初始化": "npi_init", "结束": "npi_end", "加载设计": "npi_load_design",
    "波形": "fsdb", "仿真": "vcs", "覆盖率": "coverage", "网表": "netlist",
    "事务": "transaction", "电源": "power", "功耗": "power", "文本模型": "text model",
    "遍历": "traverse", "编译": "compile make", "共享库": "shared library",
    "库文件": "library", "头文件": "header", "信号": "signal", "值变化": "value change",
}


def integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("{} must be between {} and {}".format(label, minimum, maximum))
    return value


def catalog():
    path = LIBRARY / "catalog.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != 1 or not isinstance(data.get("sources"), list):
        raise ValueError("The knowledge catalog has an unsupported format")
    return data["sources"]


def public_source(source, include_archive=False):
    metadata = {key: value for key, value in source.items() if key != "generation"}
    if include_archive:
        _, directory = resolve(source["id"], source["sha256"])
        metadata["archive"] = model_archive.progress(model_archive.batches(directory), source["pageCount"])
    return metadata


def resolve(source_id, digest=None):
    source = next((item for item in catalog() if item["id"] == source_id), None)
    if not source:
        raise ValueError("Knowledge source was not found")
    if digest is not None and source["sha256"] != digest:
        raise ValueError("This manual has changed. Reload the knowledge library")
    if not re.fullmatch(r"documents/[0-9a-f]{32}", source["generation"]):
        raise ValueError("Invalid knowledge generation")
    selected = LIBRARY / source["generation"]
    directory = selected.resolve()
    if selected.is_symlink() or directory.parent != (LIBRARY / "documents").resolve():
        raise ValueError("Invalid knowledge generation")
    return source, directory


def connect(directory):
    path = directory / "index.sqlite3"
    if not path.is_file() or path.is_symlink():
        raise ValueError("The knowledge index is missing")
    connection = sqlite3.connect(str(path), timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def query_terms(query):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300:
        raise ValueError("Enter a search query of 1 to 300 characters")
    terms = list(dict.fromkeys(re.findall(r"[a-z0-9_]+|[^\W\d_a-z]+", query.casefold())))
    if not terms:
        raise ValueError("Use a keyword or API name")
    if len(terms) > 16:
        raise ValueError("Search using at most 16 terms")
    return terms


def rank(data):
    values = struct.unpack("<{}I".format(len(data) // 4), data)
    phrases, columns = values[:2]
    score = 0.0
    for phrase in range(phrases):
        for column in range(columns):
            start = 2 + 3 * (phrase * columns + column)
            local, total = values[start:start + 2]
            score += (12 if column == 0 else 1) * local / max(total, 1)
    return score


def indexed_rows(connection, terms):
    if any(not re.fullmatch(r"[a-z0-9_]+", term) for term in terms):
        # The CentOS FTS tokenizer cannot split continuous Chinese text into words.
        clause = " AND ".join("instr(lower(section || ' ' || text), ?) > 0" for _ in terms)
        for row in connection.execute("SELECT page,label,section,text FROM pages WHERE " + clause, terms):
            pos = max(0, row["text"].casefold().find(terms[0]) - 70)
            yield row, row["text"][pos:pos + 330], 1
        return
    expression = " AND ".join('"{}"'.format(term) for term in terms)
    rows = connection.execute("""
        SELECT pages.page, pages.label, pages.section, matchinfo(search) AS ranking,
               snippet(search, '', '', ' … ', 1, 44) AS excerpt
        FROM search JOIN pages ON pages.page=search.docid WHERE search MATCH ?
    """, (expression,))
    for row in rows:
        yield row, row["excerpt"], rank(row["ranking"])


def search(request):
    terms = query_terms(request.get("query"))
    limit = integer(request.get("limit", 20), 1, 50, "Search limit")
    source_id = request.get("sourceId")
    sources = [resolve(source_id, request.get("sha256"))[0]] if source_id else catalog()
    results = []
    for source in sources:
        _, directory = resolve(source["id"], source["sha256"])
        found = {}
        for topic in model_archive.search_hits(directory, terms):
            found[topic["page"]] = {"page": topic["page"], "pageLabel": str(topic["page"]),
                                    "section": topic["title"], "excerpt": topic["summary"],
                                    "origin": "model_guide", "score": 1.0}
        raw_terms = terms
        if source["id"] == "vc-apps-npi":
            translated = request["query"].casefold()
            for original, replacement in TOPICS.items():
                translated = translated.replace(original, " " + replacement + " ")
            raw_terms = query_terms(translated.strip()) if translated != request["query"].casefold() else terms
        connection = connect(directory)
        try:
            for row, excerpt, score in indexed_rows(connection, raw_terms):
                found[row["page"]] = {"page": row["page"], "pageLabel": row["label"], "section": row["section"],
                                      "excerpt": " ".join(excerpt.split()), "origin": "page_text",
                                      "score": score + (1 if row["page"] in found else 0)}
        finally:
            connection.close()
        results.extend(dict(item, sourceId=source["id"], title=source["title"], version=source["version"],
                            sha256=source["sha256"]) for item in found.values())
    results.sort(key=lambda hit: (-hit["score"], hit["sourceId"], hit["page"]))
    return {"query": request["query"], "terms": terms, "total": len(results),
            "results": [{key: value for key, value in hit.items() if key != "score"}
                        for hit in results[:limit]]}


def read(request):
    source, directory = resolve(request.get("sourceId"), request.get("sha256"))
    page = integer(request.get("page"), 1, source["pageCount"], "PDF page")
    count = integer(request.get("count", 1), 1, 3, "Page count")
    connection = connect(directory)
    try:
        rows = connection.execute("SELECT * FROM pages WHERE page>=? AND page<? ORDER BY page", (page, page + count))
        pages = [{"page": row["page"], "pageLabel": row["label"], "section": row["section"],
                  "text": row["text"]} for row in rows]
        if not pages:
            raise ValueError("The requested page is missing from the knowledge index")
        return {"source": public_source(source), "pages": pages}
    finally:
        connection.close()


def pdf_range(request):
    source, directory = resolve(request.get("sourceId"), request.get("sha256"))
    offset = integer(request.get("offset"), 0, source["pdfBytes"] - 1, "PDF offset")
    length = integer(request.get("length"), 1, 1024 * 1024, "PDF range length")
    path = directory / "source.pdf"
    if path.is_symlink() or path.stat().st_size != source["pdfBytes"]:
        raise ValueError("The source PDF has changed. Import the manual again")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(length)
    return {"base64": base64.b64encode(data).decode("ascii")}


def read_original(request):
    source, directory = resolve(request.get("sourceId"), request.get("sha256"))
    first = integer(request.get("page"), 1, source["pageCount"], "PDF page")
    count = integer(request.get("count", 1), 1, 3, "Page count")
    pdf = directory / "source.pdf"
    if pdf.is_symlink() or pdf.stat().st_size != source["pdfBytes"]:
        raise ValueError("The source PDF has changed. Import the manual again")
    digest = hashlib.sha256()
    with pdf.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != source["sha256"]:
        raise ValueError("The source PDF digest does not match the imported manual")
    include_images = request.get("includeImages", True)
    if type(include_images) is not bool:
        raise ValueError("includeImages must be a boolean")
    pages = read_pages(pdf, first, min(first + count - 1, source["pageCount"]), include_images=include_images)
    for page in pages:
        if include_images and page["images"]:
            page["originalEvidence"] = model_archive.original_evidence(source["sha256"], page["page"])
    return {"source": dict(public_source(source), originalPath=str(pdf)),
            "origin": "original_pdf", "pages": pages}


def dispatch(action, request):
    if action == "knowledgeList":
        return [public_source(source, include_archive=True) for source in catalog()]
    if action == "knowledgeSearch":
        return search(request)
    if action == "knowledgeRead":
        return read(request)
    if action == "knowledgePdfRange":
        return pdf_range(request)
    if action == "knowledgeOriginal":
        return read_original(request)
    if action == "knowledgeArchiveNext":
        return model_archive.next_batch(request)
    if action == "knowledgeArchiveSave":
        return model_archive.save_batch(request)
    if action == "knowledgeGuide":
        return model_archive.guide(request)
    raise ValueError("Unknown knowledge action")
