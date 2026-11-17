"""Project contract and immutable input snapshots for verify.yaml."""
import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$-]*$")


def require(condition, description):
    if not condition:
        raise ValueError(description)


def relative_file(root, name):
    require(isinstance(name, str) and name and "\0" not in name, "Expected a relative source path")
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts, "Project paths must be relative")
    path = root / relative
    resolved = path.resolve()
    require(root in resolved.parents and resolved.is_file(), "Missing project input: " + name)
    return resolved


def definition(root):
    marked = relative_file(root, "verify.yaml")
    if marked.stat().st_size > 256 * 1024:
        raise ValueError("verify.yaml exceeds 256 KiB")
    try:
        data = yaml.safe_load(marked.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(str(error))
    require(isinstance(data, dict) and data.get("version") == 1, "verify.yaml requires version: 1")
    inputs = data.get("inputs")
    require(isinstance(inputs, list) and bool(inputs), "Declare inputs for snapshotting")
    for name in set(inputs):
        relative_file(root, name)
    inputs = set(inputs)
    require(data.get("spec") in inputs, "spec must be listed in inputs")
    profiles = data.get("profiles")
    require(isinstance(profiles, dict) and bool(profiles), "Declare one or more verification profiles")
    for name, profile in profiles.items():
        require(isinstance(name, str) and IDENTIFIER.fullmatch(name), "Invalid profile name")
        require(isinstance(profile, dict), "Invalid profile " + name)
        mode = profile.get("mode")
        require(mode in ("sv", "uvm", "formal"), "Invalid mode for " + name)
        require(isinstance(profile.get("top"), str) and IDENTIFIER.fullmatch(profile["top"]),
                "Invalid top module for " + name)
        require(profile.get("filelist") in inputs, "filelist must be listed in inputs")
        seconds = profile.get("timeoutSeconds", 180)
        require(type(seconds) is int and 0 < seconds <= 21600, "timeoutSeconds must be 1–21600")
        if mode == "uvm":
            require(isinstance(profile.get("test"), str) and IDENTIFIER.fullmatch(profile["test"]),
                    "An executable UVM test is required")
        if mode == "formal":
            require(profile.get("script") in inputs, "Formal Tcl script must be listed in inputs")
            properties = profile.get("properties")
            require(isinstance(properties, dict) and bool(properties), "Formal properties are required")
            for key, kind in properties.items():
                require(isinstance(key, str) and IDENTIFIER.fullmatch(key) and kind in ("assert", "cover"),
                        "Invalid Formal property")
    checks = data.get("checks")
    require(isinstance(checks, list) and bool(checks), "Declare requirements in checks")
    spec_text = relative_file(root, data["spec"]).read_text(encoding="utf-8")
    known = set()
    for check in checks:
        require(isinstance(check, dict) and isinstance(check.get("id"), str), "Invalid requirement")
        key = check["id"]
        require(key not in known and IDENTIFIER.fullmatch(key) and key in spec_text,
                "Check must have a unique ID in the specification: " + key)
        require(isinstance(check.get("title"), str) and bool(check["title"]), "Check title is required")
        require(isinstance(check.get("profiles"), list) and bool(check["profiles"]) and
                all(item in profiles for item in check["profiles"]), "Unknown profiles in " + key)
        if "property" in check:
            require(any(check["property"] in profiles[name].get("properties", {})
                        for name in check["profiles"]), "Unknown property in " + key)
        known.add(key)
    return data


def hash_file(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inputs_digest(root, config, destination=None):
    hashes = {}
    for name in sorted(set(config["inputs"]) | {"verify.yaml"}):
        origin = relative_file(root, name)
        if destination is not None:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(origin), str(target))
            origin = target
        hashes[name] = hash_file(origin)
    canonical = json.dumps(hashes, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), hashes
