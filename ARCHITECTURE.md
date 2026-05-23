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
      │  │  list per product)  │  │  (~276 seeded entries, with    │  │
      │  └─────────────────────┘  │   IARC/Prop65/GHS enrichment   │  │
      │                           │   and Claude write-back)       │  │
      │                           └────────────────────────────────┘  │
      │  ┌──────────────────────────────────────────────────────────┐  │
      │  │  recalls  (FDA food + FDA drug + RASFF, GIN FTS index)   │  │
      │  └──────────────────────────────────────────────────────────┘  │
      └──────────────────────────────────────────────────────────────────┘
                   │                              │
      ┌────────────▼────────────┐    ┌────────────▼────────────────────┐
      │  ingredient_resolver    │    │  recall_store / rasff_store     │
      │                         │    │                                 │
      │  1. Exact + alias match │    │  fetch_and_store_openfda()      │
      │  2. E-number lookup     │    │  ├─ food/enforcement (28.7K)   │
      │  3. FTS (GIN index)     │    │  └─ drug/enforcement (17.7K)   │
      │  4. Claude classify     │    │  fetch_and_store_rasff() (38K) │
      │     (≤10/scan, cached,  │    │                                 │
      │      writes back CAS)   │    │  check_product_recalls()        │
      └─────────────────────────┘    │  └─ local FTS + barcode literal│
                                     │     (real-time openFDA call    │
                                     │      removed — Session H)       │
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
                    │                    ≥1 resolved ingredient (MIN_RESOLVED)?
                    │                    YES ──► Grade/score locally (~500ms)
                    │                    NO  ──► fall through to Claude
                   NO
                    │
                    ▼
             Open Food Facts API ──found──► Claude analysis
             Open Beauty Facts API         (tool use loop)
             UPCitemdb fallback              │
             user_submissions fallback       │
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
  ├─ Open Food Facts CSV import      (updates ~2M food products)
  ├─ Open Beauty Facts CSV import    (updates ~63K cosmetic products)
  ├─ USDA FoodData Central import    (updates ~500K branded foods)
  ├─ OpenFDA OTC drug labels         (updates ~17K OTC drugs)
  ├─ DailyMed Rx drug labels         (Rx, NDC-11 barcodes)
  ├─ FDA food recalls (45-day delta) (food/enforcement.json)
  ├─ FDA drug recalls (45-day delta) (drug/enforcement.json)
  ├─ RASFF EU recall feed            (full re-pagination, ~531 pages)
  ├─ IARC Monographs enrichment      (concerns array, no inserts)
  ├─ California Prop 65 enrichment   (concerns array, no inserts)
  └─ ECHA Annex VI CLP / GHS enrichment (concerns array, no inserts)
```
