-- =============================================================================
-- SafeScan Database Schema
-- PostgreSQL 15+
-- Run with: psql safescan < schema.sql
-- =============================================================================

-- =============================================================================
-- products
-- Central product registry. One row per unique barcode. Source-of-truth for
-- product metadata retrieved from Open Food Facts, Open Beauty Facts, or
-- submitted by users / extracted by the image agent.
-- =============================================================================
CREATE TABLE IF NOT EXISTS products (
    id              BIGSERIAL PRIMARY KEY,
    -- EAN-13, UPC-A, or any other barcode standard. Globally unique.
    barcode         TEXT        UNIQUE NOT NULL,
    -- Human-readable product name (may be null if not yet resolved)
    name            TEXT,
    -- Brand / manufacturer name
    brand           TEXT,
    -- Broad category: food, cosmetic, or unknown (not yet classified)
    product_type    TEXT        CHECK (product_type IN ('food', 'cosmetic', 'unknown')),
    -- Front-of-pack image URL from the data source
    image_url       TEXT,
    -- Nutri-Score letter grade (a–e), food only
    nutriscore      CHAR(1),
    -- NOVA processing group 1–4, food only
    nova_group      SMALLINT,
    -- Free-form category tags from the originating database
    categories      TEXT[],
    -- Where this record originated
    source          TEXT        CHECK (source IN ('off', 'obf', 'user', 'image_scan', 'usda', 'openfda', 'upcitemdb')),
    -- When the record was last refreshed from an external API or sync
    last_synced_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE products IS
    'Central product registry. One row per barcode. Populated from Open Food Facts (off), '
    'Open Beauty Facts (obf), user image submissions, or manual entries.';
COMMENT ON COLUMN products.barcode         IS 'EAN-13, UPC-A, or other standard barcode. Globally unique.';
COMMENT ON COLUMN products.product_type    IS 'food | cosmetic | unknown — drives which safety rules apply.';
COMMENT ON COLUMN products.nutriscore      IS 'Nutri-Score letter grade a–e (food only).';
COMMENT ON COLUMN products.nova_group      IS 'NOVA group 1–4 measuring ultra-processing level (food only).';
COMMENT ON COLUMN products.categories      IS 'Array of free-form category strings from the originating database.';
COMMENT ON COLUMN products.source          IS 'off=Open Food Facts, obf=Open Beauty Facts, user=submitted, image_scan=extracted by agent, usda=USDA FoodData, openfda=OpenFDA OTC, upcitemdb=UPCitemdb barcode fallback.';
COMMENT ON COLUMN products.last_synced_at  IS 'Timestamp of last successful sync from the upstream source.';


-- =============================================================================
-- ingredients
-- Canonical ingredient dictionary. Each row is one unique ingredient with its
-- safety classification, score penalty, regulatory status, and evidence sources.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ingredients (
    id              BIGSERIAL PRIMARY KEY,
    -- Lowercase canonical name used for exact matching (e.g. "sodium benzoate")
    name            TEXT        NOT NULL UNIQUE,
    -- INCI (International Nomenclature of Cosmetic Ingredients) standard name
    inci_name       TEXT,
    -- EU E-number if applicable (e.g. 'E211')
    e_number        TEXT,
    -- CAS Registry Number for chemical identity matching (e.g. '50-00-0')
    cas_number      TEXT,
    -- Whether this ingredient appears in food, cosmetics, or both
    ingredient_type TEXT        CHECK (ingredient_type IN ('food_additive', 'cosmetic', 'food', 'both')),
    -- Overall safety classification driving grade contribution
    safety_level    TEXT        CHECK (safety_level IN ('safe', 'caution', 'avoid')),
    -- Points to deduct from the base score of 100 (0–30)
    score_penalty   SMALLINT    DEFAULT 0 CHECK (score_penalty BETWEEN 0 AND 30),
    -- Array of specific concern tags, e.g. ARRAY['endocrine_disruptor','allergen']
    concerns        TEXT[],
    -- EU regulatory status for this substance
    eu_status       TEXT        CHECK (eu_status IN ('approved', 'restricted', 'banned', 'unknown')),
    -- Evidence sources used to classify this ingredient
    sources         TEXT[],
    -- Free-form notes for agents or reviewers
    notes           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE ingredients IS
    'Canonical ingredient dictionary. Contains safety classification, score penalties, '
    'EU regulatory status, and concern tags for every known ingredient.';
COMMENT ON COLUMN ingredients.name           IS 'Lowercase canonical name. Must be unique. Used for exact-match resolution.';
COMMENT ON COLUMN ingredients.inci_name      IS 'INCI standard name used in EU cosmetic labelling.';
COMMENT ON COLUMN ingredients.e_number       IS 'EU E-number (food additives), e.g. E211 for sodium benzoate.';
COMMENT ON COLUMN ingredients.cas_number     IS 'CAS Registry Number for chemical identity matching, e.g. 50-00-0 (formaldehyde). Used by IARC/Prop65 importers.';
COMMENT ON COLUMN ingredients.ingredient_type IS 'food_additive | cosmetic | food | both.';
COMMENT ON COLUMN ingredients.safety_level   IS 'safe | caution | avoid — drives score penalty application.';
COMMENT ON COLUMN ingredients.score_penalty  IS 'Points deducted from base score 100. Range 0–30.';
COMMENT ON COLUMN ingredients.concerns       IS 'Array of concern tags: endocrine_disruptor, allergen, carcinogen, paraben, etc.';
COMMENT ON COLUMN ingredients.eu_status      IS 'EU regulatory status: approved | restricted | banned | unknown.';
COMMENT ON COLUMN ingredients.sources        IS 'Evidence source tags: cosing, efsa, iarc, off, obf, etc.';
COMMENT ON COLUMN ingredients.notes          IS 'Human-readable notes for agents or DB reviewers.';


-- =============================================================================
-- ingredient_aliases
-- Alternative names, synonyms, trade names, and translations that all map to a
-- single canonical ingredient. Supports multi-language label parsing.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ingredient_aliases (
    id              BIGSERIAL PRIMARY KEY,
    -- The canonical ingredient this alias resolves to
    ingredient_id   BIGINT      NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    -- The alias text (raw, mixed-case allowed — queries use lower())
    alias           TEXT        NOT NULL,
    -- ISO 639-1 two-letter language code
    language        CHAR(2)     DEFAULT 'en',
    UNIQUE (ingredient_id, alias)
);

COMMENT ON TABLE ingredient_aliases IS
    'Alternative names, synonyms, trade names, and translations for canonical ingredients. '
    'Enables the alias-match step in the resolution pipeline.';
COMMENT ON COLUMN ingredient_aliases.alias    IS 'Raw alias text. Queries normalize with lower() for case-insensitive matching.';
COMMENT ON COLUMN ingredient_aliases.language IS 'ISO 639-1 language code. Defaults to en.';


-- =============================================================================
-- product_ingredients
-- Join table linking products to their resolved (or unresolved) ingredients.
-- Preserves the raw label text and ordinal position.
-- =============================================================================
CREATE TABLE IF NOT EXISTS product_ingredients (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    -- Raw ingredient text as it appears on the label
    ingredient_name TEXT        NOT NULL,
    -- Resolved canonical ingredient. NULL means unresolved — needs agent resolution.
    ingredient_id   BIGINT      REFERENCES ingredients(id) ON DELETE SET NULL,
    -- Ordinal position in the ingredient list (1-based)
    position        SMALLINT,
    -- True if this ingredient was flagged as a declared allergen
    is_allergen     BOOLEAN     DEFAULT false
);

COMMENT ON TABLE product_ingredients IS
    'Join table between products and resolved ingredients. '
    'ingredient_id NULL means the raw ingredient text has not yet been resolved to a canonical entry.';
COMMENT ON COLUMN product_ingredients.ingredient_name IS 'Raw text from the product label, preserved exactly.';
COMMENT ON COLUMN product_ingredients.ingredient_id   IS 'FK to canonical ingredient. NULL = unresolved.';
COMMENT ON COLUMN product_ingredients.position        IS '1-based position in the ingredient list.';
COMMENT ON COLUMN product_ingredients.is_allergen     IS 'True if declared as an allergen on the label (bold, caps, "Contains:" block).';


-- =============================================================================
-- safety_reports
-- Cached safety analysis results keyed by barcode. Each report stores the full
-- JSONB payload and an expiry timestamp for cache invalidation.
-- =============================================================================
CREATE TABLE IF NOT EXISTS safety_reports (
    id          BIGSERIAL PRIMARY KEY,
    -- Barcode of the product this report covers
    barcode     TEXT        NOT NULL,
    -- Full SafetyReport JSON payload
    report      JSONB       NOT NULL,
    -- True if this report was generated or supplemented by Claude
    claude_used BOOLEAN     DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now(),
    -- After this timestamp the cache entry should be regenerated
    expires_at  TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE safety_reports IS
    'Cache of computed safety reports. Looked up first on every barcode scan. '
    'Reports expire after a configurable TTL (default 7 days) and are regenerated on next request.';
COMMENT ON COLUMN safety_reports.report      IS 'Full SafetyReport Pydantic model serialised as JSONB.';
COMMENT ON COLUMN safety_reports.claude_used IS 'True when the report was generated with Claude AI assistance.';
COMMENT ON COLUMN safety_reports.expires_at  IS 'Cache expiry. Barcode agent checks this before returning cached data.';


-- =============================================================================
-- user_submissions
-- Records of user-uploaded product or ingredient photos awaiting processing.
-- The image agent extracts data; status tracks the review pipeline.
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_submissions (
    id                      BIGSERIAL PRIMARY KEY,
    -- Barcode if the user provided one or if the image agent extracted it
    barcode                 TEXT,
    -- File-system or object-storage path to the product front image
    product_image_path      TEXT,
    -- File-system or object-storage path to the ingredient list image
    ingredients_image_path  TEXT,
    -- JSON data extracted by image and ingredient parser agents
    extracted_data          JSONB,
    -- Workflow status
    status                  TEXT        CHECK (status IN ('pending', 'verified', 'rejected')) DEFAULT 'pending',
    created_at              TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE user_submissions IS
    'User-submitted product photos pending agent extraction and verification. '
    'Once verified, extracted_data is merged into products and product_ingredients.';
COMMENT ON COLUMN user_submissions.barcode                IS 'Barcode extracted from image or entered manually by user.';
COMMENT ON COLUMN user_submissions.product_image_path     IS 'Path to the product front photo (local or object-storage key).';
COMMENT ON COLUMN user_submissions.ingredients_image_path IS 'Path to the ingredient list photo.';
COMMENT ON COLUMN user_submissions.extracted_data         IS 'Structured data extracted by image/ingredient parser agents.';
COMMENT ON COLUMN user_submissions.status                 IS 'pending | verified | rejected — tracks review workflow.';


-- =============================================================================
-- recalls
-- Food and product recall alerts from external sources (FDA RSS, RASFF).
-- Populated by recall_store.py (FDA) and rasff_store.py (EU RASFF).
-- Queried during every scan via check_product_recalls() in recall_store.py.
-- =============================================================================
CREATE TABLE IF NOT EXISTS recalls (
    id           SERIAL      PRIMARY KEY,
    -- Data source: 'fda' for FDA RSS feed, 'rasff' for EU RASFF Datalake API
    source       TEXT        NOT NULL DEFAULT 'fda',
    -- Stable unique identifier: FDA RSS guid URL, or RASFF NOTIFICATION_REFERENCE
    guid         TEXT        UNIQUE,
    title        TEXT        NOT NULL,
    description  TEXT,
    -- Severity: serious / high / medium / low
    risk_level   TEXT,
    -- Product category (free text from source)
    category     TEXT,
    -- Countries of distribution (ISO names or codes from source)
    countries    TEXT[]      NOT NULL DEFAULT '{}',
    link         TEXT,
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS recalls_fts_idx
    ON recalls
    USING GIN (to_tsvector('english', title || ' ' || COALESCE(description, '')));

CREATE INDEX IF NOT EXISTS recalls_published_at_idx
    ON recalls (published_at DESC);

COMMENT ON TABLE recalls IS
    'Product recall and safety alerts from FDA (US) and RASFF (EU). '
    'Populated by recall_store.py and rasff_store.py. Queried on every scan.';
COMMENT ON COLUMN recalls.source IS 'fda = FDA RSS recall feed; rasff = EU RASFF Datalake API.';
COMMENT ON COLUMN recalls.guid   IS 'Stable dedup key: FDA RSS guid URL or RASFF NOTIFICATION_REFERENCE.';


-- =============================================================================
-- sync_log
-- Audit trail for all external data sync runs. Records source, timing,
-- record counts, and error messages for monitoring and debugging.
-- =============================================================================
CREATE TABLE IF NOT EXISTS sync_log (
    id              BIGSERIAL PRIMARY KEY,
    -- Data source being synced
    source          TEXT        NOT NULL,
    started_at      TIMESTAMPTZ DEFAULT now(),
    -- NULL until the run finishes
    completed_at    TIMESTAMPTZ,
    -- Number of new rows inserted in this run
    records_added   INTEGER     DEFAULT 0,
    -- Number of existing rows updated in this run
    records_updated INTEGER     DEFAULT 0,
    -- Current or final run status
    status          TEXT        CHECK (status IN ('running', 'completed', 'failed')) DEFAULT 'running',
    -- Error message if status = 'failed'
    error           TEXT
);

COMMENT ON TABLE sync_log IS
    'Audit log for external data sync runs (OFF, OBF, CosIng, EFSA). '
    'One row per sync attempt. Used for monitoring, alerting, and resume logic.';
COMMENT ON COLUMN sync_log.source          IS 'off | obf | cosing | efsa — identifies which feed was synced.';
COMMENT ON COLUMN sync_log.records_added   IS 'Count of new rows inserted during this run.';
COMMENT ON COLUMN sync_log.records_updated IS 'Count of existing rows updated during this run.';
COMMENT ON COLUMN sync_log.status          IS 'running | completed | failed.';
COMMENT ON COLUMN sync_log.error           IS 'Error detail when status = failed. NULL on success.';


-- =============================================================================
-- INDEXES
-- =============================================================================

-- products — barcode uniqueness enforced by UNIQUE constraint above;
-- additional indexes for sync queries and type-based filtering
CREATE INDEX IF NOT EXISTS idx_products_synced
    ON products (last_synced_at);

CREATE INDEX IF NOT EXISTS idx_products_type
    ON products (product_type);

-- product_ingredients — fast joins in both directions
CREATE INDEX IF NOT EXISTS idx_product_ingredients_product
    ON product_ingredients (product_id);

CREATE INDEX IF NOT EXISTS idx_product_ingredients_ingredient
    ON product_ingredients (ingredient_id);

-- ingredient_aliases — GIN full-text search for fuzzy ingredient resolution
CREATE INDEX IF NOT EXISTS idx_ingredient_aliases_fts
    ON ingredient_aliases
    USING GIN (to_tsvector('english', alias));

-- ingredient_aliases — exact case-insensitive lookup (faster than FTS for exact matches)
CREATE INDEX IF NOT EXISTS idx_ingredient_aliases_alias
    ON ingredient_aliases (lower(alias));

-- ingredients — E-number lookup (partial: only rows where e_number is set)
CREATE INDEX IF NOT EXISTS idx_ingredients_enumber
    ON ingredients (e_number)
    WHERE e_number IS NOT NULL;

-- ingredients — INCI name lookup case-insensitive (partial)
CREATE INDEX IF NOT EXISTS idx_ingredients_inci
    ON ingredients (lower(inci_name))
    WHERE inci_name IS NOT NULL;

-- ingredients — CAS number lookup (partial: only rows where cas_number is set)
CREATE INDEX IF NOT EXISTS idx_ingredients_cas
    ON ingredients (cas_number)
    WHERE cas_number IS NOT NULL;

-- ingredients — filter by type and safety level (common query patterns)
CREATE INDEX IF NOT EXISTS idx_ingredients_type
    ON ingredients (ingredient_type);

CREATE INDEX IF NOT EXISTS idx_ingredients_safety
    ON ingredients (safety_level);

-- safety_reports — cache lookup by barcode and expiry check
CREATE INDEX IF NOT EXISTS idx_safety_reports_barcode
    ON safety_reports (barcode);

CREATE INDEX IF NOT EXISTS idx_safety_reports_expires
    ON safety_reports (expires_at);

-- user_submissions — filter by workflow status
CREATE INDEX IF NOT EXISTS idx_user_submissions_status
    ON user_submissions (status);


-- =============================================================================
-- INGREDIENT RESOLUTION FLOW
-- =============================================================================
--
-- When a raw ingredient string arrives from a product label or user submission,
-- the Safety Lookup Agent resolves it to a canonical ingredients row using the
-- following four-step cascade:
--
-- Step 1 — EXACT MATCH
--   SELECT * FROM ingredients WHERE name = lower(trim($raw_text));
--   Fast path. Covers well-known additives and canonical INCI names already in DB.
--
-- Step 2 — ALIAS MATCH
--   SELECT i.* FROM ingredients i
--   JOIN ingredient_aliases a ON a.ingredient_id = i.id
--   WHERE lower(a.alias) = lower(trim($raw_text));
--   Uses idx_ingredient_aliases_alias. Covers trade names, synonyms, translations.
--
-- Step 3 — FULL-TEXT SEARCH (FTS)
--   SELECT i.*, ts_rank(to_tsvector('english', a.alias), query) AS rank
--   FROM ingredient_aliases a
--   JOIN ingredients i ON i.id = a.ingredient_id,
--   to_tsquery('english', $normalized_tokens) query
--   WHERE to_tsvector('english', a.alias) @@ query
--   ORDER BY rank DESC LIMIT 5;
--   Uses idx_ingredient_aliases_fts GIN index. Handles plurals, partial words,
--   and minor spelling variants. Top result taken if rank is above threshold.
--
-- Step 4 — CLAUDE INFERENCE
--   If steps 1–3 all fail (or FTS confidence is below threshold), the raw
--   ingredient string is sent to the Analysis Agent (Claude). Claude classifies
--   the ingredient using its training knowledge, returns a safety_level and
--   score_penalty, and the result is written back to ingredients +
--   ingredient_aliases so future lookups are resolved at step 1 or 2.
--
-- Resolution result is stored in product_ingredients.ingredient_id.
-- Unresolved ingredients leave ingredient_id NULL and are surfaced in the
-- report as "unclassified" with a note.
-- =============================================================================
