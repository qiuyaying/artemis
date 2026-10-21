#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT:$ROOT/packages/artemis-client/src${PYTHONPATH:+:$PYTHONPATH}"
export ARTEMIS_APP_DIR="$ROOT/.cache/artemis-ios"
export ARTEMIS_IOS_TASK_RUNNER="$ROOT/scripts/ios_agent_run.py"
cd "$ROOT"
exec "$ROOT/.venv/bin/artemis" ios "$@"
