#!/usr/bin/env bash
# Launch-harness canonical entry point.
# Source this (or run `source setup-harness.sh`) before any render-engine / skill
# command so the locked governance + toolchain env is always applied.
#
#   source ./setup-harness.sh
#
set -a
source "$(dirname "$0")/harness.env"
set +a

# The render pipeline breaks under NODE_OPTIONS shims; clear them.
unset NODE_OPTIONS

# Quiet the "telemetry on" notice even if a stale config re-enables it.
export LAUNCH_VIDEO_NO_TELEMETRY=1

echo "[harness] telemetry=off  python=$(command -v "$LAUNCH_VIDEO_PYTHON" || echo MISSING)  ffmpeg=$(command -v ffmpeg || echo MISSING)"
