#!/usr/bin/env bash
# Install or uninstall the SafeScan weekly sync launchd job.
#
# Usage:
#   bash scripts/install_sync.sh          # install
#   bash scripts/install_sync.sh remove   # uninstall

PLIST_NAME="com.safescan.weekly-sync"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/$PLIST_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

if [[ "${1:-}" == "remove" ]]; then
    launchctl unload "$PLIST_DEST" 2>/dev/null && echo "Unloaded $PLIST_NAME"
    rm -f "$PLIST_DEST" && echo "Removed $PLIST_DEST"
    echo "Weekly sync uninstalled."
    exit 0
fi

# Make sync script executable
chmod +x "$(dirname "$0")/weekly_sync.sh"

# Create logs dir
mkdir -p "$(dirname "$0")/../logs"

# Copy plist and load
cp "$PLIST_SRC" "$PLIST_DEST"
launchctl load "$PLIST_DEST"

echo "Weekly sync installed."
echo "  Schedule : every Sunday at 03:00"
echo "  Logs     : backend/logs/sync_YYYYMMDD_HHMMSS.log"
echo ""
echo "To run now (test):  bash scripts/weekly_sync.sh"
echo "To uninstall:       bash scripts/install_sync.sh remove"
