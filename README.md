# SafeScan — Barcode Safety Scanner

A consumer first barcode safety scanner that analyzes food and cosmetic products using AI.
Available as a **PWA** (web), **iOS app**, and **Android app** via Capacitor.

## Architecture

- **Backend**: Python FastAPI + Claude claude-opus-4-6 (Anthropic SDK) with multi-agent design
- **Frontend**: React + TypeScript + Vite, Capacitor for native iOS/Android, react-zxing for web camera scanning, `@capacitor-mlkit/barcode-scanning` for native scanning

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

### Mobile (iOS & Android)

Prerequisites: Xcode (iOS) and/or Android Studio (Android) must be installed.

```bash
cd frontend

# 1. Set the production backend URL (baked into the native bundle at build time)
echo "VITE_API_URL=https://your-backend.example.com" >> .env.local

# 2. Build web assets and sync to both native projects (no service worker)
npm run build:mobile

# 3. Open in Xcode / Android Studio to sign, build, and run
npm run open:ios
npm run open:android
```

**Live-reload during native development** — point the WebView at your local Vite dev server:
```bash
# In a separate terminal
npm run dev

# Then sync with the dev server URL
CAPACITOR_SERVER_URL=http://192.168.x.x:5173 npx cap sync
npm run open:ios   # or open:android
```

**Barcode scanning**: on iOS/Android the native MLKit scanner opens as a fullscreen overlay when the user taps the scan button. On web, the existing ZXing camera view is used. Manual barcode entry is always available as a fallback.

## How It Works

1. **Scan a barcode** — use your camera or type it manually
2. **Product Lookup** — checks local PostgreSQL DB first, then Open Food Facts, Open Beauty Facts, USDA FoodData Central, OpenFDA OTC drugs, DailyMed Rx drugs (NDC-11), and UPCitemdb (100/day trial) as a final fallback
3. **Safety Analysis** — Claude Opus 4.6 with adaptive thinking analyzes ingredients using EU Cosmetics Regulation, EFSA assessments, NOVA classification, IARC carcinogen groups, ECHA Annex VI CLP / GHS hazard codes, and California Prop 65
4. **Safety Report** — A/B/C/D grade with ingredient-by-ingredient breakdown, food + drug + RASFF recall alerts, and allergen highlights

## Example Barcodes

- `3017620422003` — Nutella
- `5449000000996` — Coca-Cola
- `5000159461122` — Kit Kat
