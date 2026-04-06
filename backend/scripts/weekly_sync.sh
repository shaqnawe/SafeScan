#!/usr/bin/env bash
# SafeScan weekly sync — streams latest OFF + OBF dumps and upserts into the DB.
# Runs automatically via launchd every Sunday at 03:00.
# You can also trigger it manually:  bash scripts/weekly_sync.sh

set -euo pipefail

PYTHON="/Users/npc/miniconda3/envs/myenv/bin/python"
BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$BACKEND_DIR/logs"
LOG_FILE="$LOG_DIR/sync_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

echo "=============================" | tee "$LOG_FILE"
echo "SafeScan weekly sync started" | tee -a "$LOG_FILE"
echo "$(date)"                       | tee -a "$LOG_FILE"
echo "=============================" | tee -a "$LOG_FILE"

cd "$BACKEND_DIR"

echo "" | tee -a "$LOG_FILE"
echo "--- Open Food Facts ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.importers.off_importer --url 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "--- Open Beauty Facts ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.importers.obf_importer --url 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "--- USDA FoodData Central (branded foods) ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.importers.usda_importer --url 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "--- OpenFDA OTC Drug Labels ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.importers.openfda_importer 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "--- FDA Recall Alerts ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.recall_store 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "--- IARC Monographs (enrich ingredients) ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.importers.iarc_importer 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "--- California Prop 65 (enrich ingredients) ---" | tee -a "$LOG_FILE"
"$PYTHON" -m db.importers.prop65_importer 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "=============================" | tee -a "$LOG_FILE"
echo "Sync completed: $(date)"       | tee -a "$LOG_FILE"
echo "=============================" | tee -a "$LOG_FILE"

# Keep only the last 8 log files (2 months of weekly logs)
ls -t "$LOG_DIR"/sync_*.log 2>/dev/null | tail -n +9 | xargs rm -f
