#!/usr/bin/env sh
set -eu

# Print Python version first (Python 2.7 prints version to stderr).
python -V 2>&1

# Ensure `src/` is on PYTHONPATH so `python -m log_explainer` works from repo root.
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

python -m log_explainer "$@"


