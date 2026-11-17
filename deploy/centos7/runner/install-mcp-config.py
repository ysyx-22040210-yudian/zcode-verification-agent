#!/usr/bin/env python3
"""Register this app's MCP adapter in the isolated ZCode user profile."""
import json
import os
import sys
from pathlib import Path


def main():
    project = Path(__file__).resolve().parent.parent
    profile = Path(sys.argv[1]) if len(sys.argv) > 1 else project / "runtime" / "build-home"
    config = profile / ".zcode" / "cli" / "config.json"
    config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    server = {
        "type": "stdio",
        "command": "python3",
        "args": [str(project / "runner" / "mcp.py")],
        "enabled": True,
        "timeoutMs": 20000,
    }
    data.setdefault("features", {})["mcp"] = True
    servers = data.setdefault("mcp", {}).setdefault("servers", {})
    if servers.get("verification") == server and config.exists():
        return
    servers["verification"] = server
    temporary = config.with_suffix(".new")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(str(temporary), str(config))


if __name__ == "__main__":
    main()
