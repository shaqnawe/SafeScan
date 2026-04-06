# SafeScan — Barcode Safety Scanner

A consumer first barcode safety scanner that analyzes food and cosmetic products using AI.

## Architecture

- **Backend**: Python FastAPI + Claude claude-opus-4-6 (Anthropic SDK) with multi-agent design
- **Frontend**: React + TypeScript with camera barcode scanning via react-zxing

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
# Copy .env.example → .env and fill in ANTHROPIC_API_KEY and DATABASE_URL
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API runs at http://localhost:8000

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at http://localhost:5173

## How It Works

1. **Scan a barcode** — use your camera or type it manually
2. **Product Lookup** — checks local PostgreSQL DB first, then Open Food Facts, Open Beauty Facts, USDA FoodData Central, OpenFDA OTC drugs, and UPCitemdb (100/day trial) as a final fallback
3. **Safety Analysis** — Claude Opus 4.6 with adaptive thinking analyzes ingredients using EU Cosmetics Regulation, EFSA assessments, NOVA classification, IARC carcinogen groups, and California Prop 65
4. **Safety Report** — A/B/C/D grade with ingredient-by-ingredient breakdown, recall alerts, and allergen highlights

## Example Barcodes

- `3017620422003` — Nutella
- `5449000000996` — Coca-Cola
- `5000159461122` — Kit Kat
