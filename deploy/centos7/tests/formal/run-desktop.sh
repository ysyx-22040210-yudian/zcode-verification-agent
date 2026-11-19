#!/usr/bin/env bash
# Exercise this VM's actual desktop build without touching the user's window or workspace.
set -euo pipefail
b=/home/verification-agent
qa=$(readlink -f -- "${1:?Supply a test directory under the VM probes directory}")
case "$qa" in "$b"/probes/*) ;; *) exit 2 ;; esac
project=$(mktemp -d "$qa/ui-project.XXXXXX")
profile=$(mktemp -d "$qa/ui-profile.XXXXXX")
cp -a "$b/fifo/." "$project/"
chown -R host:host "$project" "$profile"
runuser -u host -- python3 "$b/runner/install-mcp-config.py" "$profile"
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
export VERIFICATION_WORKSPACE="$project"
"$b/compat/bookworm.sh" /usr/bin/env "HOME=$profile" "ZCODE_DESKTOP_HOME_DIR=$profile" \
  "ZCODE_DATA_BASE_DIR=$profile" "ZCODE_VERIFICATION_SOCKET=$b/runtime/verification.sock" \
  "GLM_BINARY_PATH=$b/zcode/packages/desktop/bundled-agents/linux-x64/glm/zcode.cjs" \
  "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE=$b/zcode/config/provider/zcode-builtin.json" \
  ELECTRON_OVERRIDE_DIST_PATH=/opt/verification-electron ZCODE_DISABLE_FIXED_REMOTE_DEBUGGING_PORT=1 \
  /bin/bash -c '
  set -e
  b="$1"; qa="$2"; project="$3"; port="$4"
  cd "$b/zcode/packages/desktop"
  timeout 210 xvfb-run -a -s "-screen 0 1440x1000x24" dbus-run-session /opt/verification-electron/electron \
    "$b/runtime/desktop-entry" "--open-workspace=$project" "--remote-debugging-port=$port" >"$qa/formal-window.log" 2>&1 &
  electron=$!
  trap "kill $electron 2>/dev/null || true" EXIT
  node "$b/zcode/deploy/centos7/tests/formal/desktop.cjs" "$port" "$qa/formal-window.png"
' formal "$b" "$qa" "$project" "$port"

