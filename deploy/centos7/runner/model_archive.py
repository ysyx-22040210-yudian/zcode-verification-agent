"""Durable model-authored finding guides, kept separately from extracted page text."""
import json
import hmac
import os
import sqlite3

BATCH_SIZE = 24
MAX_TOPICS = 24
EVIDENCE_KEY = os.urandom(32)


def original_evidence(digest, page):
    return hmac.new(EVIDENCE_KEY, "{}:{}".format(digest, page).encode("ascii"), "sha256").hexdigest()


def batches(directory):
    path = directory / "guide.sqlite3"
    if not path.is_file():
        return []
    db = sqlite3.connect(str(path))
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='batches'").fetchone():
            return []
        return rows(db)
    finally:
        db.close()


def rows(db):
    return [(a, b, json.loads(t), json.loads(r)) for a, b, t, r in db.execute(
        "SELECT first, last, topics, review FROM batches ORDER BY first")]


def progress(items, count):
    filed = items[-1][1] if items else 0
    reviews = sum(len(item[3]) for item in items)
    status = "pending" if not filed else "partial"
    if filed == count:
        status = "needs_review" if reviews else "filed"
    return {"status": status, "filedPages": filed, "totalPages": count, "reviewCount": reviews,
            "topicCount": sum(len(item[2]) for item in items)}


def selected(request):
    import knowledge
    digest = request.get("sha256")
    if not isinstance(digest, str) or not digest:
        raise ValueError("Specify the source digest returned by the import or catalog")
    return knowledge.resolve(request.get("sourceId"), digest)


def next_batch(request):
    import knowledge
    source, directory = selected(request)
    items = batches(directory)
    state = progress(items, source["pageCount"])
    review = request.get("reviewOnly") is True
    if review:
        pending = next((row for row in items if row[3]), None)
        if not pending:
            return dict(state, done=True)
        first, last, _, wanted = pending
    else:
        first = state["filedPages"] + 1
        if first > source["pageCount"]:
            return dict(state, done=True)
        last = min(source["pageCount"], first + BATCH_SIZE - 1)
        wanted = range(first, last + 1)
    limit = min(4500, 14000 // len(wanted))
    db = knowledge.connect(directory)
    try:
        pages = []
        for row in db.execute("SELECT page, section, text FROM pages WHERE page BETWEEN ? AND ? ORDER BY page",
                              (first, last)):
            if row["page"] in wanted:
                value = row["text"]
                pages.append({"page": row["page"], "section": row["section"][:180],
                              "excerpt": value[:limit], "truncated": len(value) > limit})
    finally:
        db.close()
    if len(pages) != len(wanted):
        raise ValueError("The requested batch is missing pages in the index")
    return dict(state, done=False, sourceId=source["id"], sha256=source["sha256"], title=source["title"],
                version=source["version"], firstPage=first, lastPage=last, reviewOnly=review, pages=pages)


def clean_string(value, limit, label):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError("Invalid " + label)
    return value.strip()


def normalize(value):
    return " ".join(value.split()).casefold()


def checked_topics(supplied, allowed, directory, digest):
    import knowledge
    if not isinstance(supplied, list) or len(supplied) > MAX_TOPICS:
        raise ValueError("Submit up to 24 cited topics per batch")
    result = []
    db = knowledge.connect(directory)
    try:
        for entry in supplied:
            if not isinstance(entry, dict):
                raise ValueError("Each topic needs a title, summary, keywords and page evidence")
            number = entry.get("page")
            if type(number) is not int or number not in allowed:
                raise ValueError("Citation page is outside this batch")
            aliases = entry.get("keywords")
            if not isinstance(aliases, list) or len(aliases) > 12:
                raise ValueError("Use up to 12 search keywords per topic")
            topic = {"page": number, "title": clean_string(entry.get("title"), 160, "topic title"),
                     "summary": clean_string(entry.get("summary"), 1200, "topic summary"),
                     "keywords": [clean_string(a, 90, "keyword") for a in aliases]}
            if entry.get("visual") is True:
                token = entry.get("originalEvidence")
                if not isinstance(token, str) or not hmac.compare_digest(original_evidence(digest, number), token):
                    raise ValueError("Read this original page and supply its originalEvidence for a visual finding")
                topic["visual"] = True
            else:
                quote = clean_string(entry.get("quote"), 420, "source quotation")
                row = db.execute("SELECT text FROM pages WHERE page=?", (number,)).fetchone()
                if not row or normalize(quote) not in normalize(row[0]):
                    raise ValueError("The quotation does not match PDF page {}".format(number))
                topic["quote"] = quote
            result.append(topic)
    finally:
        db.close()
    return result


def save_batch(request):
    import knowledge
    source, directory = selected(request)
    first = knowledge.integer(request.get("firstPage"), 1, source["pageCount"], "First page")
    if (first - 1) % BATCH_SIZE:
        raise ValueError("Use firstPage from knowledge_archive_next")
    last = min(first + BATCH_SIZE - 1, source["pageCount"])
    review = request.get("reviewOnly") is True
    if not review:
        committed = batches(directory)
        if any(row[0] == first for row in committed):
            return progress(committed, source["pageCount"])
    pending = request.get("reviewPages", [])
    if not isinstance(pending, list) or any(type(p) is not int or not first <= p <= last for p in pending):
        raise ValueError("Original-page review references must be in the current batch")
    pending = sorted(set(pending))
    topics = checked_topics(request.get("topics"), range(first, last + 1), directory, source["sha256"])
    if not review:
        unobserved = {p for p in source.get("emptyPages", []) if first <= p <= last}
        if unobserved - set(pending) - {t["page"] for t in topics if t.get("visual")}:
            raise ValueError("Read image-only pages in the original or keep their numbers in reviewPages")
    if not topics and not pending:
        raise ValueError("Submit a cited topic or identify pages that still need original review")
    path = directory / "guide.sqlite3"
    # Create the table and first checkpoint as one transaction, including on the first concurrent read.
    db = sqlite3.connect(str(path), timeout=12)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS batches(first INTEGER PRIMARY KEY, last INTEGER, topics TEXT, review TEXT)")
        items = rows(db)
        old = next((i for i in items if i[0] == first), None)
        if review:
            if not old or not set(pending).issubset(old[3]) or any(
                    t["page"] not in old[3] and t not in old[2] for t in topics):
                raise ValueError("Reload the outstanding review pages")
            if set(old[3]) - set(pending) - {t["page"] for t in topics}:
                raise ValueError("Keep each unresolved page pending until it has a cited finding")
            topics = old[2] + [t for t in topics if t not in old[2]]
        elif old:
            return progress(items, source["pageCount"])
        elif first != (items[-1][1] + 1 if items else 1):
            raise ValueError("An earlier page batch is still pending")
        db.execute("INSERT OR REPLACE INTO batches VALUES (?, ?, ?, ?)",
                   (first, last, json.dumps(topics), json.dumps(pending)))
        state = progress(rows(db), source["pageCount"])
        db.commit()
        return state
    finally:
        db.close()


def guide(request):
    import knowledge
    source, directory = selected(request)
    items = batches(directory)
    topics = [t for row in items for t in row[2]]
    offset = knowledge.integer(request.get("offset", 0), 0, len(topics), "Topic offset")
    limit = knowledge.integer(request.get("limit", 32), 1, 64, "Topic limit")
    end = offset + limit
    return dict(progress(items, source["pageCount"]), topics=topics[offset:end],
                nextOffset=end if end < len(topics) else None,
                reviewPages=[p for row in items for p in row[3]][:64])


def search_hits(directory, terms):
    for _, _, topics, _ in batches(directory):
        for topic in topics:
            field = normalize(" ".join([topic["title"], topic["summary"]] + topic["keywords"]))
            if all(term in field for term in terms):
                yield topic

