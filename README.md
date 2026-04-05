# SafeScan — Barcode Safety Scanner

A Yuka-like barcode safety scanner that analyzes food and cosmetic products using AI.

## Architecture

- **Backend**: Python FastAPI + Claude claude-opus-4-6 (Anthropic SDK) with multi-agent design
- **Frontend**: React + TypeScript with camera barcode scanning via react-zxing

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
uvicorn backend.main:app --reload
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
2. **Product Lookup Agent** — fetches data from Open Food Facts and Open Beauty Facts APIs
3. **Safety Analysis Agent** — Claude claude-opus-4-6 with adaptive thinking analyzes ingredients using:
   - EU Cosmetics Regulation for cosmetics
   - EFSA assessments and NOVA classification for food
4. **Safety Report** — Yuka-style A–E grade with ingredient breakdown

## Example Barcodes

- `3017620422003` — Nutella
- `5449000000996` — Coca-Cola
- `5000159461122` — Kit Kat
