#!/usr/bin/env bash
# Start the on-call tracker on port 9999 with auto-reload.
# Binds to 0.0.0.0 so other devices on the same network (e.g. a phone on the
# same Wi-Fi) can reach it at http://<this-machine-LAN-IP>:9999
set -euo pipefail
cd "$(dirname "$0")"
exec uv run uvicorn hospitals.main:app --reload --host 0.0.0.0 --port 9999
