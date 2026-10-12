#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Install the project first: see LIVE-DEMO-LINUX.md" >&2
  exit 1
fi
case "${1:-demo}" in
  demo|branch|loop) circuit="${1:-demo}" ;;
  *) echo "Usage: sh tools/run_live_demo.sh [demo|branch|loop]" >&2; exit 1 ;;
esac
exec .venv/bin/python -m netlist_dag build \
  --lib examples/tiny.lib --netlist "examples/$circuit.v" \
  --out "results/live-$circuit"
