#!/usr/bin/env bash
set -euo pipefail

base="$(cd "$(dirname "$0")/.." && pwd)"
cache="$base/compat/oci-cache"
tag=v44.7.0
archive="electron-$tag-linux-x64.zip"
endpoint="https://github.com/electron/electron/releases/download/$tag"
target="$base/compat/bookworm/opt/verification-electron"
args=(-4 -fsSL --retry 2 --connect-timeout 10 --max-time 360)
if [ -n "${VERIFICATION_HTTP_PROXY:-}" ]; then args+=(--proxy "$VERIFICATION_HTTP_PROXY"); fi
cd "$cache"
if [ ! -f "electron-$tag-SHASUMS256.txt" ]; then
  curl "${args[@]}" "$endpoint/SHASUMS256.txt" -o "electron-$tag-SHASUMS256.txt.part"
  mv "electron-$tag-SHASUMS256.txt.part" "electron-$tag-SHASUMS256.txt"
fi
if [ ! -f "$archive" ]; then
  curl "${args[@]}" "$endpoint/$archive" -o "$archive.part"
  mv "$archive.part" "$archive"
fi
grep "electron-$tag-linux-x64.zip$" "electron-$tag-SHASUMS256.txt" | sha256sum -c -
install -d "$target"
python3 - "$archive" "$target" <<'PY'
import os, sys, zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    for entry in archive.infolist():
        output = archive.extract(entry, sys.argv[2])
        mode = (entry.external_attr >> 16) & 0o777
        if mode:
            os.chmod(output, mode)
os.chmod(os.path.join(sys.argv[2], "chrome-sandbox"), 0o4755)
PY
