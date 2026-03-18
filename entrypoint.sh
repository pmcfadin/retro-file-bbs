#!/bin/bash
set -e

DB_PATH="${DB_PATH:-/data/index.db}"
CPM_ROOT="${CPM_ROOT:-/data/cpm}"
TELNET_PORT="${TELNET_PORT:-2323}"
WEB_PORT="${WEB_PORT:-8080}"

echo "=== Retro File BBS ==="

# Run indexer pipeline
if [ -d "$CPM_ROOT" ]; then
    echo "Step 1/2: Scanning file areas..."
    python3 /app/indexer/scan.py "$CPM_ROOT" "$DB_PATH"

    echo "Step 2/2: Extracting descriptions..."
    python3 /app/indexer/describe.py "$DB_PATH"
else
    echo "Warning: No CP/M files at $CPM_ROOT"
fi

# Start telnet + admin web UI server
echo "Starting telnet server on :${TELNET_PORT} and admin UI on :${WEB_PORT}..."
exec python3 -m server.main --db "$DB_PATH" --cpm-root "$CPM_ROOT" --port "$TELNET_PORT" --web-port "$WEB_PORT"
