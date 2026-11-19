"""Discovery and workspace starters for the installed native verification tools."""
import os
from pathlib import Path
import stat
import uuid

from .operations import schema

RUNNER = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).with_name("templates")
PROJECT_DIR = "verification_extensions"

TOOLS = {
    "rtl": {
        "title": {"zh": "RTL 实例与信号连接", "en": "RTL instances and connectivity"},
        "summary": {
            "zh": "读取已编译的 KDB，查找模块实例、信号驱动与负载，解析 interface 与 modport 绑定。",
            "en": "Read a compiled KDB to find module instances, signal drivers and loads, and interface or modport bindings.",
        },
        "keywords": [
            "module",
            "module实例",
            "信号driver",
            "信号loader",
            "instance",
            "实例",
            "层次",
            "驱动",
            "负载",
            "driver",
            "loader",
            "fanout",
            "interface",
            "接口",
            "modport",
            "SystemVerilog",
            "KDB",
            "simv.kdb",
            "simv.daidir",
            "kdb.elab++",
        ],
        "methods": ["design_query", "design_query_status"],
        "cli": "design-query.py",
        "sources": ["npi_query.py", "npi_query.tcl", "npi_interface.tcl"],
        "starter": "rtl_endpoints.py",
        "usage": "rtl_endpoints.py --kdb build/simv.daidir/simv.kdb --signal 'npi_demo.lane[0].u_tx.port.valid'",
        "starterPurpose": {
            "zh": "将信号的驱动和负载位置导出为 CSV。",
            "en": "Export driver and load source locations to CSV.",
        },
    },
    "fsdb": {
        "title": {"zh": "FSDB 波形提取", "en": "FSDB waveforms"},
        "summary": {
            "zh": "检索已录制信号，按时间区间或触发边沿提取四态波形。",
            "en": "Find recorded signals and extract four-state waveforms by time range or trigger.",
        },
        "keywords": [
            "波形",
            "时序",
            "触发前",
            "触发后",
            "上升沿",
            "下降沿",
            "跳变",
            "信号检索",
            "波形窗口",
            "时序波形",
            "wave",
            "waveform",
            "trigger",
            "edge",
            "pretrigger",
            "tick",
            "X/Z",
        ],
        "methods": ["fsdb_files", "fsdb_signals", "fsdb_wave", "fsdb_get"],
        "cli": "fsdb-wave.py",
        "sources": ["fsdb.py", "fsdb_query.tcl", "fsdb_viewer.html"],
        "starter": "fsdb_edges.py",
        "usage": "fsdb_edges.py --file demo.fsdb --signal wave_demo.data --start 8 --end 12",
        "starterPurpose": {
            "zh": "统计所选信号的区间初值、跳变次数和截断位置。",
            "en": "Summarize initial values, transitions and truncation for selected signals.",
        },
    },
    "coverage": {
        "title": {"zh": "VDB 覆盖率提取", "en": "VDB coverage"},
        "summary": {
            "zh": "提取逐测试和合并覆盖明细，定位未命中及排除项。",
            "en": "Extract per-test and merged coverage and inspect missed or excluded objects.",
        },
        "keywords": [
            "覆盖率",
            "覆盖",
            "覆盖率文件",
            "未命中",
            "排除项",
            "覆盖空洞",
            "coverage",
            "covergroup",
            "功能覆盖率",
            "代码覆盖率",
            "line",
            "branch",
            "toggle",
            "condition",
            "coverpoint",
            "cross",
            "bin",
            "fsm",
            "tgl",
            "assertion",
            "URG",
            ".vdb",
        ],
        "methods": ["coverage_extract", "coverage_get", "coverage_rows"],
        "cli": "coverage-query.py",
        "sources": ["coverage_query.tcl", "coverage_store.py", "coverage_source.py"],
        "starter": "coverage_gaps.py",
        "usage": "coverage_gaps.py --database simv.vdb --metric fsm --kind TransBin",
        "starterPurpose": {
            "zh": "分页汇总未覆盖的对象，并列出可定位的层次路径。",
            "en": "Page through missed records and summarize their types and locations.",
        },
    },
}


def catalog(request):
    tool_id = request.get("toolId")
    if tool_id is not None and (not isinstance(tool_id, str) or tool_id not in TOOLS):
        raise ValueError("Unknown verification tool")
    query = request.get("query", "")
    if not isinstance(query, str) or len(query) > 512:
        raise ValueError("Invalid tool search")
    words = query.casefold().split()
    tools = []
    for key, data in TOOLS.items():
        terms = [
            "Verdi NPI",
            key,
            *data["title"].values(),
            *data["summary"].values(),
            *data["keywords"],
            *data["methods"],
            data["cli"],
        ]
        haystack = " ".join(terms).casefold()
        if (tool_id is None or key == tool_id) and all(w in haystack for w in words):
            tools.append(
                dict(
                    data,
                    id=key,
                    cli=str(RUNNER / data["cli"]),
                    sources=[str(RUNNER / name) for name in data["sources"]],
                )
            )
    result = {
        "tools": tools,
        "sdkPath": str(Path(__file__).with_name("client.py")),
        "guidePath": str(RUNNER / "skills/verification-tools/SKILL.md"),
    }
    if tool_id:
        result["schemas"] = {m: schema(m) for m in TOOLS[tool_id]["methods"]}
    return result


def scaffold(workspace, tool_id):
    if not isinstance(tool_id, str) or tool_id not in TOOLS:
        raise ValueError("Unknown verification tool")
    name = TOOLS[tool_id]["starter"]
    source = (TEMPLATES / name).read_text(encoding="utf8")
    entry = "from verification_tools import VerificationClient"
    bootstrap = "from os import environ\nfrom sys import path as module_path\n\nmodule_path.insert(0, environ.get('ZCODE_VERIFICATION_RUNNER_DIR', {!r}))\n".format(
        str(RUNNER)
    )
    source = source.replace(entry, bootstrap + entry, 1)
    folder = workspace / PROJECT_DIR
    folder.mkdir(exist_ok=True)
    directory = os.open(str(folder), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".starter-" + uuid.uuid4().hex
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644, dir_fd=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf8") as out:
                out.write(source)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                created = True
            except FileExistsError:
                if not stat.S_ISREG(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode):
                    raise ValueError("The starter path is not a regular project file")
                created = False
        finally:
            os.unlink(temporary, dir_fd=directory)
    finally:
        os.close(directory)
    return {
        "toolId": tool_id,
        "created": created,
        "path": str(folder / name),
        "relativePath": PROJECT_DIR + "/" + name,
    }
