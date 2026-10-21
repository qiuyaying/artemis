#!/bin/sh
# Dedicated WDA endpoint for an explicitly selected iPhone/iPad simulator.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'Usage: sh scripts/ios-wda-simulator.sh <simulator-UDID> <WDA-port>' >&2
  exit 2
fi
case "$2" in ''|*[!0-9]*) echo 'WDA port must be an integer' >&2; exit 2;; esac
if [ "$2" -lt 1 ] || [ "$2" -gt 65535 ]; then exit 2; fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
xcrun simctl bootstatus "$1" -b
export TEST_RUNNER_USE_PORT="$2"
export TEST_RUNNER_MJPEG_SERVER_PORT="${ARTEMIS_MJPEG_PORT:-$((10000 + $2 % 50000))}"
exec xcodebuild -project "$ROOT/.cache/WebDriverAgent/WebDriverAgent.xcodeproj" \
  -scheme WebDriverAgentRunner -destination "platform=iOS Simulator,id=$1" \
  -derivedDataPath "${TMPDIR:-/tmp}/artemis-wda-simulator-$1" \
  CODE_SIGNING_ALLOWED=NO test
