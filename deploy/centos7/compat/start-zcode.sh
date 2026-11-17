#!/usr/bin/env bash
set -euo pipefail

base="$(cd "$(dirname "$0")/.." && pwd)"
workspace="$(readlink -f -- "${1:-$base/fifo}")"
if [ "$#" -gt 0 ]; then shift; fi
profile="$(readlink -m -- "${VERIFICATION_PROFILE_DIR:-$base/runtime/build-home}")"
runner="$base/runtime/verification.sock"

check_runner() {
  runuser -u host -- env "PYTHONPATH=$base/runtime/python" \
    python3 "$base/runner/server.py" --socket "$runner" --call \
    <<<'{"action":"health"}' >/dev/null 2>&1
}

if ! check_runner; then
  nohup runuser -u host -- bash -lc 'exec /home/verification-agent/runner/start-native.sh' \
    >"$base/evidence/runner.log" 2>&1 </dev/null &
  for attempt in 1 2 3 4 5; do
    if check_runner; then break; fi
    sleep 1
  done
fi
check_runner
test -d "$workspace"
test -f "$base/zcode/packages/desktop/out/main/index.js"
case "$profile" in
  "$base/runtime/"*) install -d -o host -g host "$profile" ;;
  *) printf '%s\n' 'Select a ZCode application profile under the project runtime directory.' >&2; exit 2 ;;
esac
runuser -u host -- python3 "$base/runner/install-mcp-config.py" "$profile"

if [ -z "${DISPLAY:-}" ]; then
  export DISPLAY=:0
fi
if [ -z "${XAUTHORITY:-}" ] && [ -f /home/host/.Xauthority ]; then
  export XAUTHORITY=/home/host/.Xauthority
fi
export VERIFICATION_WORKSPACE="$workspace"
exec "$base/compat/bookworm.sh" /usr/bin/env \
  "HOME=$profile" \
  "ZCODE_DESKTOP_HOME_DIR=$profile" \
  "ZCODE_DATA_BASE_DIR=$profile" \
  "ZCODE_VERIFICATION_SOCKET=$runner" \
  ZCODE_DISABLE_FIXED_REMOTE_DEBUGGING_PORT=1 \
  "GLM_BINARY_PATH=$base/zcode/packages/desktop/bundled-agents/linux-x64/glm/zcode.cjs" \
  "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE=$base/zcode/config/provider/zcode-builtin.json" \
  "ELECTRON_OVERRIDE_DIST_PATH=/opt/verification-electron" \
  dbus-run-session /opt/verification-electron/electron \
  "$base/runtime/desktop-entry" "--open-workspace=$workspace" "$@"
