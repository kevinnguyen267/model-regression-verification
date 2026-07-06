#!/usr/bin/env bash

set -uo pipefail

LOG_DIR="${VERIFIER_LOG_DIR:-/logs/verifier}"
mkdir -p "$LOG_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if python3 "$SCRIPT_DIR/test_verify.py"; then
  exit 0
fi

if [ ! -f "$LOG_DIR/reward.txt" ]; then
  echo "0.0" > "$LOG_DIR/reward.txt"
fi
exit 1
