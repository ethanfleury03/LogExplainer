#!/usr/bin/env sh
set -eu

# Run from this script's directory (safe: no writes, no sudo).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python RUN_ME.py "$@"


