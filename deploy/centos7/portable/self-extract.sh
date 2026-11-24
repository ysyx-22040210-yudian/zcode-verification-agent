#!/bin/bash
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  echo "Usage: bash $0 [project-directory] [Electron options]"
  echo "Opens the ZCode verification desktop in the current X11 session."
  exit 0
fi
[[ $(uname -m) == x86_64 ]] || { echo "This distribution requires Linux x86-64." >&2; exit 2; }
[[ -n ${DISPLAY:-} ]] || { echo "Open a terminal in an X11 desktop session (DISPLAY is empty)." >&2; exit 2; }
umask 077
digest=@PAYLOAD_SHA256@
base=${XDG_CACHE_HOME:-$HOME/.cache}/zcode-verification-agent/centos7
mkdir -p -- "$base"
(
  flock -x 9
  if [[ -x $base/$digest/start && -f $base/$digest/.complete ]]; then exit 0; fi
  staging=$(mktemp -d -- "$base/.unpack.XXXXXXXX")
  trap 'rm -rf -- "$staging"' EXIT
  line=$(LC_ALL=C awk '/^__ZCODE_PAYLOAD__$/{print NR+1; exit}' "$0")
  [[ -n $line ]] || { echo "Incomplete .run file." >&2; exit 1; }
  echo "Preparing the ZCode desktop in your user cache…" >&2
  actual=$(tail -n +"$line" -- "$0" | sha256sum)
  [[ ${actual%% *} == "$digest" ]] || { echo "Incomplete or damaged download (SHA-256 mismatch)." >&2; exit 1; }
  tail -n +"$line" -- "$0" | tar xzf - -C "$staging" --no-same-owner
  test -x "$staging/start"
  touch "$staging/.complete"
  if [[ -e $base/$digest ]]; then mv -T -- "$base/$digest" "$staging.incomplete"; fi
  mv -T -- "$staging" "$base/$digest"
) 9>"$base/unpack.lock"
exec "$base/$digest/start" "$@"
__ZCODE_PAYLOAD__
