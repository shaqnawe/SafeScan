# SafeScan — Enhancement Roadmap

## High Impact — Core Functionality

- [x] Multi-agent pipeline (Claude claude-opus-4-6 + adaptive thinking, two-phase: tool use → structured output)
- [x] Local PostgreSQL database seeded with EU ingredient safety data (239 entries)
- [x] Open Food Facts import (~2M food products)
- [x] Open Beauty Facts import (~63.5K cosmetic products)
- [x] Local DB lookup — check `products` table before hitting external APIs
- [x] Result caching — `safety_reports` table with 7-day TTL, instant repeat scans
- [x] **Ingredient resolver** (`db/ingredient_resolver.py`)
  - Step 1: batch exact name + alias + E-number match (single DB query)
  - Step 2: FTS fallback via GIN index for fuzzy/partial matches
  - Step 3: Claude classification for unknowns (capped at 10/scan)
  - Step 4: write-back to `ingredients` + `ingredient_aliases` so future lookups skip Claude

## Medium Impact — UX & Features

- [x] **Scan history** — `useScanHistory` hook (localStorage, max 20), scrollable card row on scanner screen + dedicated `HistoryPage` with full list, timestamps, clear button
- [x] **Local scoring engine** (`agents/local_analyzer.py`) — full rubric in Python, zero Claude API calls for known products; falls back to Claude only when <3 ingredients are resolved
- [x] **Photo-to-ingredients agent** (`agents/image_agent.py`) — Claude vision extracts product info + parses ingredient list; `POST /api/submit-product`; "+" button in scanner header
- [x] **Allergen profile** — let the user set personal allergens (gluten, nuts, dairy, etc.) and highlight them prominently in every report
- [x] **Product comparison** — side-by-side score, grade, safe/caution/avoid counts, recalls, concerns, highlights; winner banner; ⚖️ button in scanner header

## Lower Impact — Ops & Polish

- [x] **Weekly auto-sync** — launchd job (Sundays 03:00) via `scripts/weekly_sync.sh`; install with `bash scripts/install_sync.sh`; logs kept in `backend/logs/`
- [x] **Mobile camera support** — Vite `host: true`, `VITE_API_URL` env var, backend on `0.0.0.0`
- [x] **PWA / offline mode** — `vite-plugin-pwa` with full manifest, service worker, offline-first scan cache (7-day), safe-area insets for notched phones, apple-touch-icon
- [x] **Recall alerts** — FDA RSS + openFDA enforcement API; `recalls` table with FTS index; real-time match on every scan; red banner in SafetyReport with risk level + official notice link

---

*Last updated: 2026-04-04*
