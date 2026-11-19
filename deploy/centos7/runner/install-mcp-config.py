#!/usr/bin/env python3
"""Register this app's MCP adapter in the isolated ZCode user profile."""
import json
import os
import sys
import tempfile
from pathlib import Path


def main():
    project = Path(__file__).resolve().parent.parent
    profile = Path(sys.argv[1]) if len(sys.argv) > 1 else project / "runtime" / "build-home"
    skills = profile / ".zcode" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    for name in ("verification-knowledge", "verification-tools"):
        try:
            (skills / name).symlink_to(project / "runner" / "skills" / name, target_is_directory=True)
        except FileExistsError:
            pass
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
    features = data.setdefault("features", {})
    servers = data.setdefault("mcp", {}).setdefault("servers", {})
    if servers.get("verification") == server and features.get("mcp") is True:
        return
    features["mcp"] = True
    servers["verification"] = server
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=str(config.parent), delete=False) as output:
        json.dump(data, output, indent=2, ensure_ascii=False)
        output.write("\n")
    os.replace(output.name, str(config))


if __name__ == "__main__":
    main()
