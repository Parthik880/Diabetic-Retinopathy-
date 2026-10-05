#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
args=()
for arg in "$@"; do
  case "$arg" in
    --no-build) args+=(-NoBuild) ;;
    --clean) args+=(-Clean) ;;
    --validate) args+=(-Validate) ;;
    --model-info) args+=(-ModelInfo) ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
SCRIPT="$ROOT/scripts/developer-workflow.ps1"
if command -v cygpath >/dev/null 2>&1; then SCRIPT="$(cygpath -w "$SCRIPT")"; fi
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT" -Mode Run "${args[@]}"
