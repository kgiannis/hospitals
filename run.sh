#!/usr/bin/env bash
# Start the on-call tracker on port 9999 with auto-reload.
set -euo pipefail
cd "$(dirname "$0")"
exec uv run uvicorn hospitals.main:app --reload --port 9999
