#!/bin/bash
set -e

CACHE_DB="/sbbs/data/indexer_cache.db"
XFER_ROOT="/sbbs/xfer/cpm"

echo "=== CP/M Software Depot BBS ==="
echo ""

# Check if file areas are mounted
if [ ! -d "$XFER_ROOT" ]; then
    echo "Warning: No CP/M files mounted at $XFER_ROOT"
    echo "Mount your archive with: -v /path/to/cpm:/sbbs/xfer/cpm:ro"
    echo "Starting Synchronet without file areas..."
    exec /sbbs/exec/sbbs
fi

# Run the indexer pipeline
# Step 1: Scan — full import if no cache, incremental otherwise (spec §6)
echo "Step 1/3: Scanning file areas..."
python3 /indexer/scan.py "$XFER_ROOT" "$CACHE_DB"

# Step 2: Describe — extract FILE_ID.DIZ, README, heuristic (spec §5.2)
echo "Step 2/3: Extracting descriptions..."
python3 /indexer/describe.py "$CACHE_DB"

# Step 3: Sync — write FILES.BBS + register via addfiles.js (spec §6)
echo "Step 3/3: Syncing to Synchronet file areas..."
python3 /indexer/sync_synchronet.py "$CACHE_DB"

echo ""
echo "Indexer complete. Starting Synchronet BBS..."
echo "  Telnet: port 23 (host 2323)"
echo "  HTTP:   port 80 (host 8080)"
echo ""

# Hand off to Synchronet's normal startup
exec /sbbs/exec/sbbs
