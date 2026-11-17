#!/usr/bin/env python3
"""Materialize the pinned ZCode desktop test base inside the project."""
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import tarfile

PROJECT = "/home/verification-agent"
COMPAT = os.path.join(PROJECT, "compat")
ROOTFS = os.path.join(COMPAT, "bookworm")
DOWNLOADS = os.path.join(COMPAT, "oci-cache")
TAG = "24.14.0-bookworm"
REGISTRY = "https://registry-1.docker.io/v2/library/node"
MEDIA_TYPES = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))


def curl(url, token=None, destination=None):
    args = ["curl", "-4", "-fsSL", "--retry", "3", "--connect-timeout", "12", "--max-time", "420"]
    if token:
        args += ["-H", "Authorization: Bearer " + token, "-H", "Accept: " + MEDIA_TYPES]
    if destination:
        args += ["-o", destination]
    result = subprocess.run(args + [url], stdout=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError("Download failed: " + url)
    return result.stdout


def file_digest(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha256.update(block)
    return "sha256:" + sha256.hexdigest()


def layer(digest, token):
    filename = os.path.join(DOWNLOADS, digest.split(":", 1)[1] + ".tar")
    if os.path.isfile(filename) and file_digest(filename) == digest:
        return filename
    print("Downloading", digest, flush=True)
    curl(REGISTRY + "/blobs/" + digest, token, filename + ".part")
    if file_digest(filename + ".part") != digest:
        raise RuntimeError("Layer digest mismatch: " + digest)
    os.replace(filename + ".part", filename)
    print("Verified", digest, flush=True)
    return filename


def apply_whiteouts(archive, root):
    with tarfile.open(archive, "r:*") as members:
        for member in members:
            name = os.path.basename(member.name)
            if not name.startswith(".wh."):
                continue
            directory = os.path.realpath(os.path.join(root, os.path.dirname(member.name)))
            if os.path.commonpath((root, directory)) != root:
                raise RuntimeError("Unsafe OCI whiteout directory: " + member.name)
            if name == ".wh..wh..opq":
                targets = [os.path.join(directory, item) for item in os.listdir(directory)] if os.path.isdir(directory) else []
            else:
                targets = [os.path.join(directory, name[4:])]
            for target in targets:
                if os.path.isdir(target) and not os.path.islink(target):
                    shutil.rmtree(target)
                elif os.path.lexists(target):
                    os.unlink(target)


def main():
    if os.geteuid():
        raise SystemExit("Run as root to preserve image ownership.")
    if os.path.isfile(os.path.join(ROOTFS, ".verification-rootfs.json")):
        print("Bookworm rootfs already prepared")
        return
    staging = ROOTFS + ".staging"
    os.makedirs(DOWNLOADS, mode=0o755, exist_ok=True)
    token = json.loads(curl(
        "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/node:pull"
    ))["token"]
    index = json.loads(curl(REGISTRY + "/manifests/" + TAG, token))
    image = next(item["digest"] for item in index["manifests"]
                 if item["platform"].get("os") == "linux" and item["platform"].get("architecture") == "amd64")
    manifest_bytes = curl(REGISTRY + "/manifests/" + image, token)
    if "sha256:" + hashlib.sha256(manifest_bytes).hexdigest() != image:
        raise RuntimeError("Image manifest digest mismatch")
    digests = [item["digest"] for item in json.loads(manifest_bytes)["layers"]]
    print("Image", TAG, image, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        archives = list(executor.map(lambda digest: layer(digest, token), digests))
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.mkdir(staging, 0o755)
    for archive in archives:
        print("Extracting", os.path.basename(archive), flush=True)
        apply_whiteouts(archive, staging)
        subprocess.check_call(["tar", "-xf", archive, "--numeric-owner", "--exclude=*.wh.*", "-C", staging])
    metadata = {"image": "docker.io/library/node:" + TAG, "manifest": image, "layers": digests}
    with open(os.path.join(staging, ".verification-rootfs.json"), "w") as output:
        json.dump(metadata, output, indent=2)
    os.rename(staging, ROOTFS)
    print("Bookworm rootfs ready", flush=True)


if __name__ == "__main__":
    main()
