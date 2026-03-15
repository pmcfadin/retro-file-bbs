#!/bin/bash
set -e

DB_PATH="/data/index.db"
CPM_ROOT="/data/cpm"

echo "=== CP/M Software Depot ==="

# Run indexer pipeline
if [ -d "$CPM_ROOT" ]; then
    echo "Step 1/2: Scanning file areas..."
    python3 /app/indexer/scan.py "$CPM_ROOT" "$DB_PATH"

    echo "Step 2/2: Extracting descriptions..."
    python3 /app/indexer/describe.py "$DB_PATH"
else
    echo "Warning: No CP/M files at $CPM_ROOT"
fi

# Start HTTP mirror in background
echo "Starting HTTP mirror on :8080..."
python3 -m http.server 8080 --directory "$CPM_ROOT" &

# Start telnet server
echo "Starting telnet server on :2323..."
exec python3 -m server.main --db "$DB_PATH" --cpm-root "$CPM_ROOT" --port 2323
