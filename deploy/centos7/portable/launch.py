"""Start the packaged desktop as the calling CentOS user, with host-side EDA."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parent
KIT = BASE / "kit"
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(KIT))
import portable
from knowledge_seed import copy_sources


def display_connection():
    value = os.environ.get("DISPLAY", "")
    match = re.fullmatch(r"(.*):(\d+)(?:\.\d+)?", value)
    if not match:
        raise ValueError("Open a terminal in an X11 desktop session (DISPLAY is required).")
    host, display = match[1], int(match[2])
    if not host or host in ("unix", "unix/") or host.endswith("/unix"):
        address = "UNIX-CONNECT:/tmp/.X11-unix/X" + str(display)
    else:
        if not re.fullmatch(r"[A-Za-z0-9_.:\[\]-]+", host) or display > 59535:
            raise ValueError("Unsupported X11 display address")
        address = f"TCP:{host}:{6000 + display}"
    return address, str(display).encode()


def copy_cookie(session, display):
    source = Path(os.environ.get("XAUTHORITY") or Path.home() / ".Xauthority")
    content = bytearray()
    if source.is_file():
        data = memoryview(source.read_bytes())
        pos = 0
        while pos < len(data):
            pos += 2
            fields = []
            for _ in range(4):
                length = int.from_bytes(data[pos:pos + 2], "big")
                pos += 2
                if pos + length > len(data):
                    raise ValueError("Invalid Xauthority file")
                fields.append(bytes(data[pos:pos + length]))
                pos += length
            if fields[1] == display and fields[2] == b"MIT-MAGIC-COOKIE-1":
                content.extend(b"\xff\xff")
                for field in (b"", b"0", fields[2], fields[3]):
                    content.extend(struct.pack("!H", len(field)) + field)
    (session / "Xauthority").write_bytes(content)


def prepare_files(state, project):
    example = state / "examples" / "fifo"
    if project is None and not example.exists():
        example.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=example.parent) as work:
            source = Path(work) / "fifo"
            shutil.copytree(KIT / "fifo", source)
            source.rename(example)
    project = Path(project).expanduser().resolve(strict=True) if project else example
    if not project.is_dir() or project == Path("/"):
        raise ValueError("Choose a project directory")
    disk = state / "desktop.img"
    if not disk.exists():
        with tempfile.TemporaryDirectory(dir=state) as work:
            subprocess.run(["tar", "-xzf", BASE / "guest/profile.tar.gz", "-C", work, "desktop.img"], check=True)
            (Path(work) / "desktop.img").replace(disk)
    return project, disk


def host_service(state):
    os.environ.setdefault("ZCODE_FORMAL_STATE", str(state / "verification"))
    defaults = BASE / "knowledge-seed"
    if "VERIFICATION_KNOWLEDGE_DIR" not in os.environ and (defaults / "catalog.json").is_file():
        copy_sources(defaults, state / "knowledge")
    os.environ.setdefault("VERIFICATION_KNOWLEDGE_DIR", str(state / "knowledge"))
    os.environ["PATH"] = str(BASE / "host/pdf-tools") + os.pathsep + os.environ.get("PATH", os.defpath)
    for variable, conventional, name, levels in (
        ("VERIFICATION_VCS_HOME", "VCS_HOME", "vcs", 2),
        ("VERIFICATION_IFV_HOME", "IUS_HOME", "ifv", 3),
        ("VERDI_HOME", "NOVAS_HOME", "verdi", 2),
    ):
        tool = shutil.which(name)
        root = os.environ.get(conventional)
        if not root and tool:
            root = str(Path(tool).absolute().parents[levels - 1])
        if root:
            os.environ.setdefault(variable, root)
    return portable.activate()


def escaped(value):
    # QEMU's key/value parser represents a literal comma with a double comma.
    return str(value).replace(",", ",,")


def run_desktop(state, workspace, extras):
    address, display = display_connection()
    project, disk = prepare_files(state, workspace)
    endpoint = host_service(state)
    if endpoint.suffix != ".json":
        raise ValueError("The portable desktop needs its per-user local verification endpoint")
    descriptor = json.loads(endpoint.read_text())
    session_root = Path(tempfile.mkdtemp(prefix="session-", dir=state))
    host = BASE / "host"
    kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
    qemu = [host / "lib/ld-linux-x86-64.so.2", "--library-path", host / "lib", host / "qemu-system-x86_64",
            "-name", "ZCode verification desktop", "-L", host / "firmware", "-no-user-config", "-nodefaults",
            "-machine", "pc", "-accel", "kvm" if kvm else "tcg,thread=multi"]
    if kvm:
        qemu.extend(["-accel", "tcg,thread=multi"])
    qemu.extend(["-cpu", "max", "-smp", "2", "-m", "2048", "-display", "none", "-monitor", "none", "-no-reboot",
                 "-serial", "stdio", "-kernel", BASE / "guest/vmlinuz", "-initrd", BASE / "guest/initrd.gz",
                 "-append", "console=ttyS0 quiet panic=1 net.ifnames=0 random.trust_cpu=on",
                 "-drive", f"if=virtio,format=raw,readonly=on,file={escaped(BASE / 'guest/desktop.squashfs')}",
                 "-drive", f"if=virtio,format=raw,file={escaped(disk)}",
                 "-object", "rng-random,filename=/dev/urandom,id=rng0", "-device", "virtio-rng-pci,rng=rng0"])
    net = "user,id=network,guestfwd=tcp:10.0.2.100:6000-cmd:zcode-x11"
    debug = next((int(a.split("=")[1]) for a in extras if re.fullmatch(r"--remote-debugging-port=[1-9]\d{0,4}", a)), None)
    if debug:
        if debug > 65535:
            raise ValueError("Invalid debugging port")
        net += f",hostfwd=tcp:127.0.0.1:{debug}-10.0.2.15:29223"
    qemu.extend(["-netdev", net, "-device", "virtio-net-pci,netdev=network,romfile="])
    home = Path.home().resolve()
    shares = {"homefs": home}
    for name, directory in (("statefs", state), ("projectfs", project), ("endpointfs", endpoint.parent.resolve())):
        if not any(directory == path or path in directory.parents for path in shares.values()):
            shares[name] = directory
    for name, path in {"session": session_root, "kit": KIT, **shares}.items():
        qemu.extend(["-virtfs", f"local,id=fs{name},path={escaped(path)},security_model=none,mount_tag={name}"
                     + (",readonly=on" if name == "kit" else "")])
    env = dict(os.environ, PATH=str(host) + ":" + os.environ.get("PATH", "/usr/bin:/bin"),
               QEMU_MODULE_DIR=str(host / "modules"), ZCODE_PORTABLE_HOST=str(host), ZCODE_PORTABLE_X11=address)
    try:
        copy_cookie(session_root, display)
        locale = next((os.environ.get(key) for key in ("LC_ALL", "LC_MESSAGES", "LANG") if os.environ.get(key)), "")
        language = locale.split(".")[0].replace("_", "-")
        config = {"uid": os.getuid(), "gid": os.getgid(), "project": str(project),
                  "endpoint": str(endpoint), "port": descriptor["port"], "shares": {n: str(d) for n, d in shares.items()},
                  "inbox": str(portable.state_directory() / "knowledge-inbox"), "args": extras, "debug": debug,
                  "language": language if re.fullmatch(r"[a-z]{2}(?:-[A-Za-z]{2,4})?", language) else ""}
        (session_root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        log = state / "desktop.log"
        print(f"Opening ZCode on {os.environ['DISPLAY']}. Startup log: {log}", file=sys.stderr, flush=True)
        with log.open("wb") as stream:
            with subprocess.Popen(qemu, env=env, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream) as process:
                def stop(_signal, _frame):
                    process.terminate()
                old = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
                try:
                    status = process.wait()
                finally:
                    for sig, handler in old.items():
                        signal.signal(sig, handler)
        result = session_root / "exit"
        if status or not result.exists() or result.read_text().strip() != "0":
            raise RuntimeError(f"The desktop stopped. See {log}")
    finally:
        shutil.rmtree(session_root)


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    workspace = args.pop(0) if args and not args[0].startswith("--") else None
    state = (Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "zcode-verification-agent").resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "desktop.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("The ZCode portable desktop is already open for this user.", file=sys.stderr)
            return
        run_desktop(state, workspace, args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit(str(error))
