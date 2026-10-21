#!/bin/sh
# Explicit device deployment; requires existing Xcode signing/provisioning.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'Usage: sh scripts/ios-wda-device.sh <device-UDID> <development-team-ID>' >&2
  exit 2
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WDA_PROJECT="$ROOT/.cache/WebDriverAgent/WebDriverAgent.xcodeproj"
# Keep signed products outside synced Documents folders (FinderInfo breaks codesign).
BUILD_DIR="${ARTEMIS_WDA_BUILD_DIR:-${TMPDIR:-/tmp}/artemis-wda-device-build-$(id -u)}"
if [ ! -d "$WDA_PROJECT" ]; then
  echo 'Official WebDriverAgent checkout is missing in .cache/WebDriverAgent' >&2
  exit 1
fi
exec xcodebuild -project "$WDA_PROJECT" -scheme WebDriverAgentRunner \
  -destination "platform=iOS,id=$1" -derivedDataPath "$BUILD_DIR" \
  "DEVELOPMENT_TEAM=$2" CODE_SIGN_STYLE=Automatic test
