#!/usr/bin/env bash
# Run as a VM maintainer. All edits and the loopback model configuration use a fresh test project/profile.
set -euo pipefail
b=/home/verification-agent
qa="${1:?Supply a writable evidence directory under /home/verification-agent/probes}"
case "$(readlink -f -- "$qa")" in "$b"/probes/*) ;; *) exit 2 ;; esac
scenario="${2:-tool-catalog}"
case "$scenario" in tool-catalog|model-vision) ;; *) exit 2 ;; esac
sample="$(mktemp -d "$qa/project.XXXXXX")"
profile="$(mktemp -d "$qa/profile.XXXXXX")"
chown host:host "$profile" "$sample"
if [[ "$scenario" == tool-catalog ]]; then
  cp -a "$b/examples/coverage/." "$sample/"
  mkdir -p "$sample/build"
  ln -s "$b/examples/npi/build/simv.daidir" "$sample/build/simv.daidir"
  test -r "$sample/build/simv.daidir/simv.kdb"
  cp "$b/examples/fsdb/demo.fsdb" "$sample/"
fi
install -d -o host -g host "$profile/.zcode" "$profile/.zcode/v2"
runuser -u host -- python3 "$b/runner/install-mcp-config.py" "$profile"
test -r "$profile/.zcode/skills/verification-tools/SKILL.md"
ports="$(python3 - <<'PY'
import socket
sockets=[socket.socket() for _ in range(2)]
for sock in sockets: sock.bind(('127.0.0.1',0))
print(*(sock.getsockname()[1] for sock in sockets))
PY
)"
read -r provider_port debug_port <<< "$ports"
runuser -u host -- python3 - "$profile" "$provider_port" "${TOOL_CATALOG_TEST_SEARCH:-off}" <<'PY'
from pathlib import Path
import json,sys
config=Path(sys.argv[1])/'.zcode/v2'
provider='verification-e2e'
model='verification-tool-test'
selection={'providerId':provider,'modelId':model}
rule={'providerId':provider,'providerName':'Verification E2E','config':{
    'group':'standard-personal','access':{'type':'api-key','apiKey':'loopback-test-only'},
    'api':{'type':'openai-chat-completions','baseUrl':'http://127.0.0.1:'+sys.argv[2]+'/v1'},
    'personalModelIds':[model]}}
config_data={'providerConfigRules':{'providerRules':[rule]},'defaultModelSelection':selection,
             'modelConfigRules':{'providerModelRules':[dict(selection,config={'properties':{'inputFormat':{'supportsImage':True}}})],
                                 'manualProviderModelRules':[]}}
(config/'provider_config.json').write_text(json.dumps({'schemaVersion':1,'config':config_data}))
assert sys.argv[3] in ('off','local','auto')
(config/'setting.json').write_text(json.dumps({'locale':'zh-CN','localePreference':'zh-CN','toolSearchMode':sys.argv[3]}))
PY
tests="$b/zcode/deploy/centos7/tests/tool-catalog"
runuser -u host -- python3 -u "$tests/../$scenario/agent-provider.py" "$provider_port" >"$qa/model.log" 2>&1 &
model_pid=$!
trap 'kill "$model_pid" 2>/dev/null || true' EXIT
export VERIFICATION_WORKSPACE="$sample"
echo "PROJECT $sample"
"$b/compat/bookworm.sh" /usr/bin/env "HOME=$profile" "ZCODE_DESKTOP_HOME_DIR=$profile" "ZCODE_DATA_BASE_DIR=$profile" \
  "ZCODE_VERIFICATION_SOCKET=$b/runtime/verification.sock" "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=$profile/.zcode/v2/provider_config.json" \
  "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE=$b/zcode/config/provider/zcode-builtin.test.json" \
  "GLM_BINARY_PATH=$b/zcode/packages/desktop/bundled-agents/linux-x64/glm/zcode.cjs" \
  ELECTRON_OVERRIDE_DIST_PATH=/opt/verification-electron ZCODE_DISABLE_FIXED_REMOTE_DEBUGGING_PORT=1 /bin/bash -c '
    set -e
    b="$1"; q="$2"; sample="$3"; port="$4"
    cd "$b/zcode/packages/desktop"
    timeout 420 xvfb-run -a -s "-screen 0 1440x1000x24" dbus-run-session /opt/verification-electron/electron \
      "$b/runtime/desktop-entry" "--open-workspace=$sample" "--remote-debugging-port=$port" >"$q/test-electron.log" 2>&1 &
    electron=$!
    trap "kill $electron 2>/dev/null || true" EXIT
    node "$5/desktop.cjs" "$port" "$q/tool-window.png" "$sample/build/simv.daidir/simv.kdb" "$6"
  ' toolkit "$b" "$qa" "$sample" "$debug_port" "$tests" "$scenario"
if [[ "$scenario" == model-vision ]]; then exit 0; fi
python3 - "$sample/unknown-edges.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['count']==1 and d['unknownTicks']==['9'] and len(d['jobId'])==32,d
print('PROJECT_FILE',sys.argv[1],d['jobId'])
PY

