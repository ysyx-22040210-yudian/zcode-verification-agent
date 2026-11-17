#!/usr/bin/env bash
set -euo pipefail

base="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$base/runtime/python"
export VERIFICATION_VCS_HOME="${VERIFICATION_VCS_HOME:-/home/synopsys/vcs/O-2018.09-SP2}"
export VERIFICATION_IFV_HOME="${VERIFICATION_IFV_HOME:-/home/cadence/INCISIVE152}"

export VCS_HOME="$VERIFICATION_VCS_HOME"
export VERDI_HOME="${VERDI_HOME:-/home/synopsys/verdi/Verdi_O-2018.09-SP2}"
export VCS_TARGET_ARCH=linux64
export PATH="$VCS_HOME/bin:$VERIFICATION_IFV_HOME/tools/bin:$VERDI_HOME/bin:$PATH"
# Repeated login-shell setup can expand PATH beyond what this IFV release handles.
# Keep each search directory's first occurrence and preserve lookup order.
PATH="$(python3 - <<'PYTHON'
import os
from collections import OrderedDict

paths = os.environ["PATH"].split(os.pathsep)
print(os.pathsep.join(OrderedDict.fromkeys(paths)))
PYTHON
)"
if [ -n "${VERIFICATION_VCS_LICENSE:-}" ]; then
  export LM_LICENSE_FILE="$VERIFICATION_VCS_LICENSE"
  export SNPSLMD_LICENSE_FILE="$VERIFICATION_VCS_LICENSE"
fi
exec python3 "$base/runner/server.py" --socket "${VERIFICATION_SOCKET:-$base/runtime/verification.sock}" --runs "${VERIFICATION_ARTIFACTS:-$base/artifacts}"
