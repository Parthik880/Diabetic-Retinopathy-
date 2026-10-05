#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if (( $# )); then printf 'Usage: ./deploy.sh\n' >&2; exit 2; fi
SCRIPT="$ROOT/scripts/developer-workflow.ps1"
if command -v cygpath >/dev/null 2>&1; then SCRIPT="$(cygpath -w "$SCRIPT")"; fi
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT" -Mode Deploy
