#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT:$ROOT/packages/artemis-client/src${PYTHONPATH:+:$PYTHONPATH}"
export ARTEMIS_APP_DIR="$ROOT/.cache/artemis-ios"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/ios_agent_run.py" "$@"
