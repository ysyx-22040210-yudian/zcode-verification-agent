"""Launch the bundled verification service for the desktop, MCP or a terminal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT / "runner"))
from verification_tools.client import call


def state_directory():
    custom = os.environ.get("ZCODE_FORMAL_STATE")
    if custom:
        return Path(custom).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    install_id = hashlib.sha256(os.path.normcase(str(KIT)).encode("utf-8")).hexdigest()[:16]
    return base / "zcode" / "formal" / install_id


def ready(endpoint):
    try:
        return call(endpoint, {"action": "health"}).get("ok") is True
    except (OSError, ValueError, KeyError):
        return False


def activate():
    state = state_directory()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    configured = os.environ.get("ZCODE_VERIFICATION_SOCKET")
    if configured and ready(Path(configured)):
        return Path(configured)
    if configured and Path(configured) != state / "endpoint.json":
        raise RuntimeError("Configured verification service is unavailable: " + configured)
    endpoint = state / "endpoint.json"
    if not ready(endpoint):
        env = os.environ.copy()
        env["VERIFICATION_FORMAL_HOME"] = str(KIT / "formal-toolchain")
        env["VERIFICATION_KNOWLEDGE_INBOX"] = str(state / "knowledge-inbox")
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        with (state / "runner.log").open("ab") as log:
            subprocess.Popen([sys.executable, "-E", "-s", "-X", "utf8", str(KIT / "runner/server.py"),
                              "--socket", str(endpoint), "--runs", str(state / "runs")],
                             cwd=str(KIT), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **flags)
        for _ in range(120):
            if ready(endpoint):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Formal service startup failed. See " + str(state / "runner.log"))
    return endpoint


def register_mcp():
    profile = Path(os.environ.get("ZCODE_DATA_BASE_DIR") or os.environ.get("ZCODE_DESKTOP_HOME_DIR") or Path.home())
    config = profile / ".zcode/cli/config.json"
    config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    servers = data.setdefault("mcp", {}).setdefault("servers", {})
    if "verification" in servers:
        return
    entry = {"type": "stdio", "command": sys.executable, "args": ["-E", "-s", "-X", "utf8", str(KIT / "portable.py"), "mcp"],
             "enabled": True, "timeoutMs": 20000}
    if servers.get("verification-formal") == entry and data.get("features", {}).get("mcp") is True:
        return
    servers["verification-formal"] = entry
    data.setdefault("features", {})["mcp"] = True
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config.parent, delete=False) as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    os.replace(stream.name, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command")
    modes.add_parser("activate", help="start the service and register it in this ZCode profile")
    mcp = modes.add_parser("mcp", help="serve the verification MCP tools on stdio")
    mcp.add_argument("workspace", nargs="?", default=".")
    run = modes.add_parser("run", help="run a project profile and print its evidence")
    run.add_argument("workspace", nargs="?", default=str(KIT / "fifo"))
    run.add_argument("--profile", default="formal")
    run.add_argument("--variant", choices=["normal", "mutant"], default="normal")
    run.add_argument("--seed", type=int, default=42)
    desktop = modes.add_parser("desktop", help="open a local ZCode verification desktop with the shared runner")
    desktop.add_argument("executable")
    desktop.add_argument("workspace", nargs="?", default=str(KIT / "fifo"))
    args = parser.parse_args()
    endpoint = activate()
    os.environ["ZCODE_VERIFICATION_SOCKET"] = str(endpoint)
    if args.command == "activate":
        register_mcp()
        print(json.dumps({"endpoint": str(endpoint)}))
        return 0
    if args.command == "desktop":
        register_mcp()
        return subprocess.call([args.executable, "--open-workspace=" + str(Path(args.workspace).resolve())])
    if args.command == "mcp":
        import mcp as adapter
        # Only advertise the operations provided by the stand-alone Formal kit.
        adapter.METHODS = {k: v for k, v in adapter.METHODS.items() if v[0] in
                           ("inspect", "submit", "get", "cancel", "rerun", "readArtifact", "advance")}
        sys.argv = [adapter.__file__, args.workspace]
        adapter.main()
        return 0
    workspace = str(Path(getattr(args, "workspace", KIT / "fifo")).resolve())
    receipt = call(endpoint, {"action": "submit", "workspace": workspace, "profile": getattr(args, "profile", "formal"),
                              "variant": getattr(args, "variant", "normal"), "seed": getattr(args, "seed", 42)})
    while receipt["status"] in ("queued", "running"):
        time.sleep(0.2)
        receipt = call(endpoint, {"action": "get", "workspace": workspace, "runId": receipt["id"]})
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] in ("pass", "bounded") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)

