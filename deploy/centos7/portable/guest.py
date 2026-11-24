"""Bring up the packaged Electron runtime. This program runs only inside the guest."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SESSION = Path("/run/zcode/session")
KIT = Path("/run/zcode/kit")
APP = Path("/opt/zcode-verification-agent")


def project_owner(raw, target, uid, gid, readonly=False):
    # A root desktop session still runs Electron as an ordinary guest user. Present
    # the caller's private files under that guest UID without chowning the originals.
    # Debian 客体的 /root 自带 shell 配置，允许在临时叠加层上挂载调用者的主目录。
    options = "allow_other,nosuid,nodev,nonempty" + (",ro" if readonly else "")
    subprocess.run(["bindfs", f"--force-user={uid}", f"--force-group={gid}", "--create-for-user=0",
                    "--create-for-group=0", "--chown-ignore", "--chgrp-ignore", "-o", options,
                    str(raw), str(target)], check=True)


def main():
    config = json.loads((SESSION / "config.json").read_text())
    uid, gid = config["uid"] or 1000, config["gid"] or 1000
    profile = Path("/var/lib/zcode/user")
    runtime = Path("/run/user") / str(uid)
    for directory in (profile, runtime):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chown(directory, uid, gid)
    with open("/etc/passwd", "a") as passwd:
        passwd.write(f"zcode:x:{uid}:{gid}:ZCode desktop:{profile}:/bin/bash\n")
    with open("/etc/group", "a") as groups:
        groups.write(f"zcode:x:{gid}:\n")
    root_caller = config["uid"] == 0
    raw_shares = Path("/run/zcode/raw")
    if root_caller:
        raw_shares.mkdir(mode=0o700)
        raw_kit = raw_shares / "kit"
        raw_kit.mkdir()
        subprocess.run(["mount", "--move", str(KIT), str(raw_kit)], check=True)
        project_owner(raw_kit, KIT, uid, gid, readonly=True)
    for tag, target in config["shares"].items():
        path = Path(target)
        reserved = (APP, KIT, SESSION, Path("/usr"), Path("/dev"), Path("/proc"), Path("/sys"), Path("/etc"), Path("/var/lib/zcode"))
        if path == Path("/") or any(path == fixed or path in fixed.parents or fixed in path.parents for fixed in reserved):
            raise ValueError(f"Cannot place a project or home over a desktop runtime directory: {target}")
        path.mkdir(parents=True, exist_ok=True)
        mountpoint = raw_shares / tag if root_caller else path
        mountpoint.mkdir(exist_ok=True)
        subprocess.run(["mount", "-t", "9p", "-o", "trans=virtio,version=9p2000.L,msize=262144,cache=mmap,access=any,nosuid,nodev",
                        tag, str(mountpoint)], check=True)
        if root_caller:
            project_owner(mountpoint, path, uid, gid)
    cookie = runtime / "Xauthority"
    shutil.copyfile(SESSION / "Xauthority", cookie)
    os.chmod(cookie, 0o600)
    os.chown(cookie, uid, gid)
    env = dict(os.environ, HOME=str(profile), USER="zcode", LOGNAME="zcode", LANG="C.UTF-8", LC_ALL="C.UTF-8",
               PATH=str(KIT / "formal-toolchain/python/bin") + ":/usr/local/bin:/usr/bin:/bin",
               DISPLAY="10.0.2.100:0", XAUTHORITY=str(cookie), XDG_RUNTIME_DIR=str(runtime),
               ZCODE_DESKTOP_HOME_DIR=str(profile), ZCODE_DATA_BASE_DIR=str(profile),
               ZCODE_VERIFICATION_SOCKET=config["endpoint"], VERIFICATION_KNOWLEDGE_INBOX=config["inbox"],
               ZCODE_DISABLE_FIXED_REMOTE_DEBUGGING_PORT="1", ZCODE_CENTOS7_PORTABLE_DESKTOP="1",
               GDK_BACKEND="x11", NO_AT_BRIDGE="1")
    identity = dict(user=uid, group=gid, extra_groups=[], env=env, cwd=str(profile))
    subprocess.run([sys.executable, "-I", str(KIT / "runner/install-mcp-config.py"), str(profile)], check=True, **identity)
    # The desktop and MCP keep using their authenticated loopback client. Only this guest's
    # loopback is forwarded to the caller's service on the host's slirp gateway.
    port = int(config["port"])
    proxies = [subprocess.Popen(["socat", f"TCP4-LISTEN:{port},bind=127.0.0.1,reuseaddr,fork",
                                 f"TCP4:10.0.2.2:{port}"], **identity)]
    try:
        if config.get("debug"):
            proxies.append(subprocess.Popen(["socat", "TCP4-LISTEN:29223,bind=10.0.2.15,reuseaddr,fork",
                                             f"TCP4:127.0.0.1:{int(config['debug'])}"], **identity))
        binary = next(p for p in (APP / "zcode", APP / "zcode-preview") if p.is_file())
        print("Starting the sandboxed ZCode desktop", flush=True)
        language = ["--lang=" + config["language"]] if config.get("language") else []
        return subprocess.call(["dbus-run-session", "--", str(binary), "--disable-gpu", *language,
                                "--open-workspace=" + config["project"], *config["args"]], **identity)
    finally:
        for proxy in proxies:
            proxy.terminate()
            proxy.wait()


if __name__ == "__main__":
    sys.exit(main())
