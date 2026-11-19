#!/usr/bin/env bash
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)/wave_demo.sv"
out="$(readlink -m -- "$1")"
mkdir -p "$out"
cd "$out"
: "${VERDI_HOME:?Set VERDI_HOME}"
vcs -full64 -sverilog -timescale=1ns/1ns -debug_access+all \
  -P "$VERDI_HOME/share/PLI/VCS/LINUX64/novas.tab" "$VERDI_HOME/share/PLI/VCS/LINUX64/pli.a" \
  -top wave_demo "$src" -o simv >compile.log 2>&1
./simv >simulation.log 2>&1
test -s demo.fsdb

