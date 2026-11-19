"""Wire names and schemas shared by the MCP adapter, Python client and tool catalog."""
STRING = {"type": "string"}
RUN_ID = {"type": "string", "description": "Run ID returned by verification_submit"}
STATUS_METHOD = {
    "design_query": "design_query_status",
    "fsdb_signals": "fsdb_get",
    "fsdb_wave": "fsdb_get",
    "coverage_extract": "coverage_get",
}


def prepare(method, args):
    action, _, properties, required = METHODS[method]
    if method == "design_query" and isinstance(args, dict) and (not args.get("kdb") or {"filelist", "profile", "top"}.intersection(args)):
        raise ValueError("RTL queries require kdb (compiled simv.kdb, simv.daidir or kdb.elab++). Filelist, top and profile are not query inputs.")
    if not isinstance(args, dict) or set(args) - set(properties) or set(required) - set(args):
        raise ValueError("Invalid arguments for " + method)
    if method in ("fsdb_signals", "fsdb_wave"):
        return "fsdbStart", dict(args, operation="signals" if method == "fsdb_signals" else "wave")
    return action, args


def schema(method):
    _, _, properties, required = METHODS[method]
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


FSDB_TICK = {
    "type": "string",
    "pattern": "^[0-9]{1,20}$",
    "description": "Integer ticks, in the FSDB scale",
}
FSDB_TRIGGER = {
    "type": "object",
    "additionalProperties": False,
    "required": ["signal", "edge"],
    "properties": {
        "signal": STRING,
        "edge": {"enum": ["rising", "falling", "change"]},
        "from": FSDB_TICK,
        "before": FSDB_TICK,
        "after": FSDB_TICK,
    },
}
METHODS = {
    "coverage_extract": (
        "coverageStart",
        "覆盖率、覆盖数据库、未命中 bin。Extract all native Verdi NPI coverage records from a VCS .vdb path (or a file inside it) or a completed SV/UVM run ID. Preserve every test, native merged results, hierarchy, bins, counters, goal, flags, exclusions, source locations and covered tests. Optional excludeFile applies a report-time exclusion. Poll coverage_get.",
        {
            "path": STRING,
            "runId": RUN_ID,
            "excludeFile": STRING,
            "timeoutSeconds": {"type": "integer", "minimum": 1, "maximum": 86400},
        },
        [],
    ),
    "coverage_get": (
        "coverageGet",
        "Read a workspace coverage extraction. On completion views give per-metric data record counts. jsonlPath and sqlitePath contain all structured NPI records. xmlPath, manifestPath and sourceArchive preserve vendor XML and original VDB members.",
        {"jobId": STRING},
        ["jobId"],
    ),
    "coverage_rows": (
        "coverageRows",
        "Read native coverage detail, ordered by record ID. Filter by exact view ID, metric, NPI kind without npiCov, state, or literal scope substring. Pass nextAfter as after until null. Zero count, absent count and exclusion differ.",
        {
            "jobId": STRING,
            "view": STRING,
            "metric": STRING,
            "kind": STRING,
            "state": STRING,
            "search": STRING,
            "after": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        ["jobId"],
    ),
    "fsdb_files": (
        "fsdbFiles",
        "Find recorded .fsdb waveform files in this workspace and its verification artifacts.",
        {},
        [],
    ),
    "fsdb_signals": (
        "fsdbSignals",
        "波形信号和层次检索。Search the native FSDB hierarchy by substring or * and ? pattern, including "
        "interface and bus names. Poll fsdb_get with the returned job ID for names, widths and tick scale.",
        {"file": STRING, "pattern": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 300}},
        ["file"],
    ),
    "fsdb_wave": (
        "fsdbWave",
        "FSDB 波形、触发前后、跳变、波形窗口。Extract actual recorded values and ordered transitions for 1–16 exact hierarchical "
        "signals. Use decimal tick strings for start/end, or use trigger with from, before and after "
        "for pre-trigger history. Poll fsdb_get until complete. The user can open this ID in the native "
        "FSDB waveform window; the standalone interactive waveform.html is in its evidenceDirectory. "
        "omittedAt is the first unread transition. Missing data is not a known value.",
        {
            "file": STRING,
            "signals": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 16},
            "start": FSDB_TICK,
            "end": FSDB_TICK,
            "trigger": FSDB_TRIGGER,
            "fingerprint": STRING,
            "maxChanges": {"type": "integer", "minimum": 1, "maximum": 2048},
        },
        ["file", "signals"],
    ),
    "fsdb_get": (
        "fsdbGet",
        "Get a saved FSDB search or waveform in this workspace. For a wave, return its ID "
        "and link its viewerPath to open the interactive waveform. Check truncation and each lane status.",
        {"jobId": STRING},
        ["jobId"],
    ),
    "design_query": (
        "designQueryStart",
        "查模块实例、Interface / modport、信号驱动和负载（driver/loader）。Query elaborated SystemVerilog with native Verdi NPI. Use instances to find modules "
        "by definition and/or full hierarchical path (* and ? wildcards, literal generate indices). Use signal "
        "to return drivers, loads and source locations for an exact hierarchical signal, including bound interface "
        "members such as top.u_tx.port.valid. Pass the selected build's compiled VCS KDB. If the build is ambiguous, "
        "ask which KDB to use. Relative paths use the current workspace. Returns a query ID; "
        "call design_query_status until terminal. Inspect warnings, counts, source lines and bindings.",
        {
            "operation": {"enum": ["instances", "signal"]},
            "definition": STRING,
            "instance": STRING,
            "scope": STRING,
            "signal": STRING,
            "direction": {"enum": ["both", "driver", "load"]},
            "kdb": {"type": "string", "minLength": 1, "description": "Path to the build's simv.kdb file, its containing simv.daidir, or kdb.elab++."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            "timeoutSeconds": {"type": "integer", "minimum": 1, "maximum": 3600},
        },
        ["operation", "kdb"],
    ),
    "design_query_status": (
        "designQueryGet",
        "Read the same workspace's native NPI query by ID. When complete, inspect outcome "
        "and truncated separately. An empty direction is meaningful only for an ok, complete trace. "
        "Bindings describe modport declarations; drivers/loads describe accesses reported by NPI.",
        {"jobId": STRING},
        ["jobId"],
    ),
}
