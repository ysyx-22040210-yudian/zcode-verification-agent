#!/usr/bin/env bash
set -euo pipefail

base="$(cd "$(dirname "$0")/.." && pwd)"
test -f "$base/compat/bookworm/.verification-rootfs.json"
test -x "$base/compat/bookworm/opt/verification-electron/electron"
exec "$base/compat/bookworm.sh" /bin/bash -c '
  set -e
  cd /home/verification-agent/zcode
  ulimit -c 0
  export NODE_OPTIONS=--max-old-space-size=4800
  export ELECTRON_OVERRIDE_DIST_PATH=/opt/verification-electron
  export npm_config_store_dir=/home/verification-agent/cache/pnpm-store
  pnpm architecture:check --changed
  pnpm typecheck
  pnpm lint
  # TypeScript emits intermediate desktop outputs into out/. Assemble the
  # production bundles after typecheck so Electron loads the bundled Host.
  pnpm --filter @zcode/desktop build:no-runtime-assets
'
