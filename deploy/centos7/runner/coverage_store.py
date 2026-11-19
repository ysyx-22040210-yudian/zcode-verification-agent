"""Stream the native records into immutable, pageable coverage evidence."""
import json
from pathlib import Path
import sqlite3

from project import require

METRICS = ("line", "condition", "branch", "toggle", "fsm", "assertion", "functional", "power")
STRINGS = {"fullName", "definition", "file", "valueText", "toggleType"}
FLAGS = (
    (1, "unreachable"),
    (2, "illegal"),
    (4, "excluded_compile"),
    (8, "covered"),
    (32, "proven"),
    (64, "excluded_report"),
    (128, "attempted"),
    (256, "partially_excluded"),
    (512, "partially_attempted"),
)


def classify(row):
    mask = row.get("status", 0)
    if mask & (4 | 64):
        return "excluded"
    if mask & 256:
        return "partially_excluded"
    if mask & 2:
        return "illegal"
    if mask & 1:
        return "unreachable"
    total, hit = row.get("coverable"), row.get("covered")
    if total and hit is not None:
        return "covered" if hit >= total else "partial" if hit else "missed"
    return "count_only" if "count" in row else "unmeasured"


def save(directory, events):
    sqlite = directory / "coverage.sqlite"
    jsonl = directory / "coverage.jsonl"
    views = {}
    database = None
    final = None
    count = 0
    db = sqlite3.connect(str(sqlite))
    try:
        db.execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, view TEXT, metric TEXT, kind TEXT, state TEXT, scope TEXT, payload TEXT)"
        )
        with db, jsonl.open("w", encoding="utf8") as output:
            for tag, val in events:
                if tag == "database":
                    name, kind, code = val
                    database = {"name": name, "kind": kind, "typeCode": int(code)}
                elif tag == "view":
                    key, label, kind, code = val
                    require(key not in views, "Duplicate native coverage view")
                    views[key] = {
                        "id": key,
                        "name": label,
                        "nativeType": kind or None,
                        "typeCode": int(code) if code else None,
                        "metrics": {m: {"dataRecords": 0} for m in METRICS},
                    }
                elif tag == "row":
                    idx, parent, view, metric, relation, kind, name, scope = val[:8]
                    count += 1
                    require(
                        int(idx) == count
                        and 0 <= int(parent) < count
                        and view in views
                        and len(val) % 2 == 0,
                        "Incomplete native coverage row",
                    )
                    row = {
                        "id": count,
                        "parentId": int(parent) or None,
                        "view": view,
                        "metric": metric,
                        "relation": relation,
                        "kind": kind,
                        "name": name,
                        "scope": scope,
                    }
                    row.update({k: v if k in STRINGS else int(v) for k, v in zip(val[8::2], val[9::2])})
                    if "status" in row:
                        row["flags"] = [label for bit, label in FLAGS if row["status"] & bit]
                    row["state"] = classify(row)
                    if (
                        metric in METRICS
                        and not kind.endswith("Metric")
                        and relation not in ("component", "coveredtest")
                    ):
                        views[view]["metrics"][metric]["dataRecords"] += 1
                    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                    db.execute(
                        "INSERT INTO records VALUES(?,?,?,?,?,?,?)",
                        (count, view, metric, kind, row["state"], scope, payload),
                    )
                    output.write(payload + "\n")
                elif tag == "error":
                    raise ValueError(val[0])
                elif tag == "end":
                    final = int(val[0])
                else:
                    raise ValueError("Unknown native coverage record: " + tag)
            require(
                database and views and count and final == count,
                "Verdi did not complete the coverage traversal",
            )
            db.execute("CREATE INDEX by_view_metric ON records(view,metric,id)")
            db.execute("CREATE INDEX by_state ON records(state,id)")
            db.execute("CREATE INDEX by_kind ON records(kind,id)")
    finally:
        db.close()
    return {
        "databaseObject": database,
        "rowCount": count,
        "views": list(views.values()),
        "jsonlPath": str(jsonl),
        "sqlitePath": str(sqlite),
    }


def page(record, request):
    require(record["status"] == "complete", "Coverage extraction is not complete")
    after, limit = request.get("after", 0), request.get("limit", 50)
    require(
        type(after) is int and 0 <= after < (1 << 63) and type(limit) is int and 1 <= limit <= 200,
        "Invalid coverage page",
    )
    conditions, args = ["id > ?"], [after]
    for key in ("view", "metric", "kind", "state", "search"):
        value = request.get(key, "")
        require(isinstance(value, str) and len(value) <= 2048, "Invalid coverage filter")
        if value:
            conditions.append("instr(lower(scope),lower(?)) > 0" if key == "search" else key + " = ?")
            args.append(value)
    query = "SELECT payload FROM records WHERE " + " AND ".join(conditions) + " ORDER BY id LIMIT ?"
    path = Path(record["result"]["sqlitePath"])
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        data = [json.loads(row[0]) for row in db.execute(query, args + [limit + 1])]
    finally:
        db.close()
    return {"rows": data[:limit], "nextAfter": data[limit - 1]["id"] if len(data) > limit else None}
