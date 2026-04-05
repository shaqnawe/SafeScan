# SafeScan — Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT (Browser / PWA)                             │
│                                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
│  │ BarcodeScanner│  │AddProductPage│  │ SubmissionsPage │  │ ComparisonPage   │ │
│  │  (camera /  │  │ (photo upload│  │ (poll status,   │  │ (side-by-side    │ │
│  │   manual    │  │  + manual    │  │  view report)   │  │  grade/score)    │ │
│  │   input)    │  │  ingredients)│  │                 │  │                  │ │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘  └────────┬─────────┘ │
│         │                │                    │                    │           │
│  ┌──────▼────────────────▼────────────────────▼────────────────────▼─────────┐ │
│  │                          React App  (App.tsx)                             │ │
│  │  AllergenProfilePage · HistoryPage · SafetyReport · useScanHistory hook  │ │
│  │                  localStorage (scan history, allergen profile)            │ │
│  └───────────────────────────────────┬───────────────────────────────────────┘ │
│                                      │ fetch / FormData                        │
│            Service Worker (workbox)  │ NetworkFirst cache for /api/scan        │
└──────────────────────────────────────┼─────────────────────────────────────────┘
                                       │ HTTP
                    ┌──────────────────▼──────────────────────┐
                    │         FastAPI  (main.py)               │
                    │                                          │
                    │  POST /api/submit-product                │
                    │  POST /api/scan                          │
                    │  GET  /api/submissions                   │
                    │  POST /api/recalls/refresh               │
                    │  GET  /health                            │
                    └────┬──────────────┬────────────┬─────────┘
                         │              │            │
           ┌─────────────▼──┐    ┌──────▼──────┐    │
           │  image_agent   │    │  scanner.py  │    │
           │  (vision)      │    │              │    │
           │                │    │ ┌──────────┐ │    │
           │ _extract_      │    │ │ Cache    │ │    │
           │  product_info  │    │ │ check    │ │    │
           │ _parse_        │    │ └────┬─────┘ │    │
           │  ingredients   │    │      │ miss  │    │
           │                │    │ ┌────▼─────┐ │    │
           │ process_       │    │ │ Local    │ │    │
           │  product_      │    │ │ fast     │ │    │
           │  photos()      │    │ │ path     │ │    │
           └───────┬────────┘    │ └────┬─────┘ │    │
                   │             │      │ <3    │    │
                   │             │      │ ingr. │    │
                   │             │ ┌────▼─────┐ │    │
                   │             │ │  Claude  │ │    │
                   │             │ │  Opus    │ │    │
                   │             │ │  loop    │ │    │
                   │             │ │ (tool    │ │    │
                   │             │ │  use +   │ │    │
                   │             │ │ adaptive │ │    │
                   │             │ │ thinking)│ │    │
                   │             │ └────┬─────┘ │    │
                   │             └──────┼────────┘    │
                   │                   │              │
      ┌────────────▼───────────────────▼──────────────▼────────────────┐
      │                    Anthropic API  (claude-opus-4-6)             │
      │           Vision · Tool Use · Adaptive Thinking · Parse         │
      └─────────────────────────────────────────────────────────────────┘
                   │                   │              │
      ┌────────────▼───────────────────▼──────────────▼────────────────┐
      │                     PostgreSQL  (safescan)                      │
      │                                                                  │
      │  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
      │  │  products   │  │  safety_reports │  │ user_submissions │   │
      │  │  (~2M food  │  │  (cache, 7-day  │  │ (barcode, status,│   │
      │  │  ~63K cosm) │  │   TTL)          │  │  extracted_data, │   │
      │  └──────┬──────┘  └─────────────────┘  │  report)         │   │
      │         │                               └──────────────────┘   │
      │  ┌──────▼──────────────┐  ┌────────────────────────────────┐  │
      │  │ product_ingredients │  │  ingredients                   │  │
      │  │ (position-ordered   │  │  + ingredient_aliases          │  │
      │  │  list per product)  │  │  (239 EU safety entries,       │  │
      │  └─────────────────────┘  │   write-back from Claude)      │  │
      │                           └────────────────────────────────┘  │
      │  ┌──────────────────────────────────────────────────────────┐  │
      │  │  recalls  (FDA RSS + openFDA enforcement, GIN FTS index) │  │
      │  └──────────────────────────────────────────────────────────┘  │
      └──────────────────────────────────────────────────────────────────┘
                   │                              │
      ┌────────────▼────────────┐    ┌────────────▼────────────────────┐
      │  ingredient_resolver    │    │  recall_store                   │
      │                         │    │                                 │
      │  1. Exact + alias match │    │  fetch_and_store_recalls()      │
      │  2. E-number lookup     │    │  ├─ FDA RSS feed                │
      │  3. FTS (GIN index)     │    │  └─ openFDA enforcement API     │
      │  4. Claude classify     │    │                                 │
      │     (≤10/scan, cached)  │    │  check_product_recalls()        │
      └─────────────────────────┘    │  ├─ local FTS                  │
                                     │  └─ real-time openFDA query     │
                                     └─────────────────────────────────┘

────────────────────────────────────────────────────────────────────────────────
 Analysis Pipeline (3 paths, fastest wins)
────────────────────────────────────────────────────────────────────────────────

  Barcode in ──► Cache hit? ──YES──► Return cached report (~200ms)
                    │
                   NO
                    │
                    ▼
             In products table? ──YES──► local_analyzer.py
                    │                    ≥3 resolved ingredients?
                    │                    YES ──► Grade/score locally (~500ms)
                    │                    NO  ──► fall through to Claude
                   NO
                    │
                    ▼
             Open Food Facts API ──found──► Claude analysis
             Open Beauty Facts API         (tool use loop)
             user_submissions fallback        │
                                             ▼
                                        Phase 1: lookup_product tool
                                        Phase 2: messages.parse()
                                        structured SafetyReport (~3-6 min)
                                             │
                                             ▼
                                        Cache result (7 days)
                                        Attach recall alerts
                                        Return SafetyReport

────────────────────────────────────────────────────────────────────────────────
 Scheduled Jobs  (macOS launchd — every Sunday 03:00)
────────────────────────────────────────────────────────────────────────────────

  weekly_sync.sh
  ├─ Open Food Facts CSV import   (updates ~2M food products)
  ├─ Open Beauty Facts CSV import (updates ~63K cosmetic products)
  └─ recall_store refresh         (pulls latest FDA recalls)
```
