# SafeScan — Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│            CLIENT (Browser / PWA · Capacitor iOS & Android WebView)             │
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
│  │  HomePage · AllergenProfilePage · HistoryPage · SafetyReport · ThemeToggle│ │
│  │  Hooks: useScanHistory · useAllergenProfile · ThemeProvider/useTheme      │ │
│  │  Type: Manrope (body) + Fraunces (display: wordmark + grade letter only) │ │
│  │  Motion: src/motion.css (fade-up, stagger, lift, press; respects RM pref)│ │
│  │                  localStorage (scan history, allergen profile, theme)     │ │
│  └───────────────────────────────────┬───────────────────────────────────────┘ │
│                                      │ fetch / FormData                        │
│            Service Worker (workbox)  │ NetworkFirst cache for /api/scan        │
└──────────────────────────────────────┼─────────────────────────────────────────┘
                                       │ HTTP
                    ┌──────────────────▼──────────────────────┐
                    │         FastAPI  (main.py)               │
                    │  CORS: env-driven explicit allowlist     │
                    │   (capacitor://localhost, https://       │
                    │    localhost, Vite dev/preview, prod URL)│
                    │                                          │
                    │  POST /api/submit-product                │
                    │  POST /api/scan                          │
                    │  GET  /api/search?q=...                  │
                    │  GET  /api/submissions                   │
                    │  POST /api/recalls/refresh               │
                    │  GET  /health                            │
                    └────┬──────────────┬────────────┬─────────┘
                         │              │            │
           ┌─────────────▼──┐    ┌──────▼──────────┐    │
           │  image_agent   │    │  scanner.py     │    │
           │  (vision)      │    │                 │    │
           │                │    │ ┌─────────────┐ │    │
           │ _extract_      │    │ │ Cache       │ │    │
           │  product_info  │    │ │ check       │ │    │
           │ _parse_        │    │ │ (safety_    │ │    │
           │  ingredients   │    │ │  reports,   │ │    │
           │   (Sonnet 4.6, │    │ │  7-day TTL) │ │    │
           │    parse, NO   │    │ └──────┬──────┘ │    │
           │    thinking,   │    │        │ miss   │    │
           │    max 4096,   │    │ ┌──────▼──────┐ │    │
           │    parallel    │    │ │ Local fast  │ │    │
           │    via asyncio)│    │ │ path        │ │    │
           │                │    │ │ (rich src + │ │    │
           │ process_       │    │ │  resolved   │ │    │
           │  product_      │    │ │  ingr ≥ 1)  │ │    │
           │  photos()      │    │ └──────┬──────┘ │    │
           └───────┬────────┘    │        │ skip   │    │
                   │             │ ┌──────▼──────┐ │    │
                   │             │ │ Phase 1     │ │    │
                   │             │ │ Sonnet 4.6  │ │    │
                   │             │ │ lookup_     │ │    │
                   │             │ │  product    │ │    │
                   │             │ │ tool loop   │ │    │
                   │             │ │ (thinking   │ │    │
                   │             │ │  display=   │ │    │
                   │             │ │  omitted)   │ │    │
                   │             │ └──────┬──────┘ │    │
                   │             │ ┌──────▼──────┐ │    │
                   │             │ │ Phase 2     │ │    │
                   │             │ │ Opus 4.6    │ │    │
                   │             │ │ synthesis   │ │    │
                   │             │ │ via         │ │    │
                   │             │ │ messages.   │ │    │
                   │             │ │  stream()   │ │    │
                   │             │ │ (keeps LB   │ │    │
                   │             │ │  connection │ │    │
                   │             │ │  alive past │ │    │
                   │             │ │  60s cutoff)│ │    │
                   │             │ └──────┬──────┘ │    │
                   │             └────────┼────────┘    │
                   │                      │             │
      ┌────────────▼──────────────────────▼─────────────▼──────────────┐
      │   Anthropic API   Opus 4.6 (synthesis) · Sonnet 4.6 (lookup,   │
      │                   OCR, ingredient parse, classification)       │
      │   Vision · Tool Use · Adaptive Thinking · Streaming · Parse    │
      │   Prompt caching: ephemeral 5-min cache on all system prompts  │
      └─────────────────────────────────────────────────────────────────┘
                   │                   │              │
      ┌────────────▼───────────────────▼──────────────▼────────────────┐
      │                     PostgreSQL  (safescan)                      │
      │                                                                  │
      │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
      │  │  products   │  │  safety_reports  │  │ user_submissions │  │
      │  │ (~2M food + │  │  (UNIQUE barcode,│  │ (barcode, status,│  │
      │  │  ~63K cosm +│  │  upsert with     │  │  extracted_data, │  │
      │  │  ~500K USDA+│  │  updated_at,     │  │  report;         │  │
      │  │  ~17K OTC + │  │  7-day TTL)      │  │  partial UNIQUE  │  │
      │  │  ~? Rx NDC) │  └──────────────────┘  │  on barcode)     │  │
      │  └──────┬──────┘                         └──────────────────┘  │
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

  Barcode in ──► Cache hit (safety_reports, not expired)? ──YES──► Return (~200ms)
                    │
                   NO
                    │
                    ▼
             In products with rich source (off/obf/usda/openfda/dailymed)
             AND ≥1 resolved ingredient with safety_level?
                    │                    YES ──► local_analyzer.py
                    │                            Grade/score locally (~500ms)
                    │                    NO  ──► Claude pipeline (below)
                   NO
                    │
                    ▼
             Phase 1: Sonnet 4.6 tool loop — calls lookup_product()
                      with adaptive thinking (display=omitted to keep
                      Phase 2 payload small)

                      lookup_product priority (highest fidelity first):
                        1. Local DB row with rich source
                        2. user_submissions with parsed ingredients
                        3. Open Food Facts live API
                        4. Open Beauty Facts live API
                        5. UPCitemdb live fetch (caches as source='upcitemdb')
                        6. user_submissions name+brand only
                        7. UPCitemdb-cached local row (last resort)
                    │
                    ▼
             Phase 2: Opus 4.6 synthesis via messages.stream()
                      (streaming required — non-streaming hits the
                      upstream ~60s LB cutoff on large payloads;
                      bisected in Session I-extended, scratch/repro_phase2.py)
                      → joined text chunks → strip fences → json.loads →
                        SafetyReport(**data)  (~60–120s)
                    │
                    ▼
             Upsert to safety_reports (UNIQUE on barcode, refreshes
             updated_at + expires_at) · Attach recall alerts · Return
                    │
                    ▼
             /api/scan post-processing (food path also fills 2 + 3):
              1. Attach up to 3 alternatives by category_slug + better
                 score (skipped grade A + not_found)
              2. Backfill nutriscore + nova_group from products if
                 missing on the cached/Claude report
              3. Derive is_vegan from ingredients_analysis via
                 agents/vegan.py (food only; True/False/None tri-state)
             scoring_breakdown is populated upstream by either
             local_analyzer or Claude Phase 2 — never backfilled here.

────────────────────────────────────────────────────────────────────────────────
 Name Search  (GET /api/search?q=...&product_type=...&limit=...)
────────────────────────────────────────────────────────────────────────────────

  query in ──► search_products() — pg_trgm GIN on products.name + brand
                                   (281 MB total over 4.6M rows, ~1-2 ms)
                    │
                    ▼
             Rank: brand-exact > name-prefix > brand-prefix >
                   name-substring > brand-substring
                    │
                    ▼
             Return list[SearchResult] {barcode, name, brand,
                                        image_url, product_type}

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
