-- =============================================================================
-- Document Intelligence Pipeline — Postgres schema
-- =============================================================================
-- Three tables: documents, pages, reference_data.
-- documents.document_category covers all PDF types we ingest:
--   practitioner | letter | receipt | record | other
-- Practitioner-only columns are nullable so non-practitioner PDFs slot in
-- cleanly. The metadata JSONB column absorbs category-specific fields
-- (letter sender/receiver, vendor name, GST, etc.) without further migrations.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- reference_data: mirrors the augmented Excel (master practitioner registry).
-- Created first because documents.reference_data_id FKs into it.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reference_data (
    id                   SERIAL      PRIMARY KEY,
    app_no               BIGINT,
    app_date             TEXT,
    registration_no      INTEGER     NOT NULL UNIQUE,    -- THE join key
    registration_date    TEXT,
    f_name               TEXT,
    m_name               TEXT,
    l_name               TEXT,
    f_name_change        TEXT,                            -- post-marriage
    m_name_change        TEXT,
    l_name_change        TEXT,
    gender               TEXT,
    date_of_birth        TEXT,                            -- mixed formats in source
    place_of_birth       TEXT,
    nationality          TEXT,
    qualification        TEXT,
    exam_month           TEXT,
    exam_year            REAL,
    roll_no              TEXT,
    university           TEXT,
    college              TEXT,
    address              TEXT,
    district             TEXT,
    taluka               TEXT,
    pin_no               INTEGER,
    prof_add             TEXT,
    prof_district        TEXT,
    prof_taluka          TEXT,
    prof_pin_no          INTEGER,
    mobile_no            TEXT,
    telephone_no         TEXT,
    prof_telephone_no    TEXT,
    email_id             TEXT,
    cr_dt                TIMESTAMPTZ,
    status               TEXT,
    valid_upto_date      TEXT,
    doctor_status        TEXT,

    -- Normalized concatenation of searchable name/dob/qual fields for
    -- fuzzy match during the confidence stage. Populated at load time.
    fields_norm          JSONB       NOT NULL DEFAULT '{}'::jsonb,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reference_data_registration_no
    ON reference_data (registration_no);
CREATE INDEX IF NOT EXISTS idx_reference_data_dob
    ON reference_data (date_of_birth);
CREATE INDEX IF NOT EXISTS idx_reference_data_fields_norm
    ON reference_data USING GIN (fields_norm);


-- -----------------------------------------------------------------------------
-- documents: top-level PDF — any category.
-- document_id = sha256 of the original PDF, computed on NAS, used everywhere.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    document_id          TEXT        PRIMARY KEY,         -- sha256 of original PDF

    document_category    TEXT        NOT NULL
        CHECK (document_category IN
            ('practitioner', 'letter', 'receipt', 'record', 'other')),
    document_type        TEXT,                             -- e.g. 'renewal_application',
                                                           --      'govt_letter_in',
                                                           --      'vendor_invoice'

    original_filename    TEXT        NOT NULL,
    qr_content           TEXT,                             -- decoded QR (cover sticker), if any
    s3_key_pdf           TEXT        NOT NULL,
    page_count           INTEGER     NOT NULL CHECK (page_count >= 0),

    status               TEXT        NOT NULL DEFAULT 'received'
        CHECK (status IN
            ('received', 'processing', 'structuring', 'processed', 'failed', 'manual_review')),

    -- ---- Practitioner-only fields (nullable for other categories) ----------
    application_number   TEXT,                             -- AMR-MCH-26-A-XXXXX
    registration_no      TEXT,                             -- join key to reference_data
    applicant_name_raw   TEXT,                             -- as OCR'd, before normalization
    dob                  DATE,
    gender               TEXT,
    reference_data_id    INTEGER     REFERENCES reference_data(id) ON DELETE SET NULL,
    match_status         TEXT
        CHECK (match_status IS NULL OR match_status IN
            ('matched', 'unmatched', 'not_applicable', 'manual_review')),

    -- ---- Flexible bucket for letter/receipt/record metadata ----------------
    -- Examples:
    --   letter   : {"sender_org": "...", "receiver_org": "...", "subject": "...",
    --               "referenced_registration_nos": ["34903", ...]}
    --   receipt  : {"vendor_name": "...", "gst": "...", "amount": 12345.00,
    --               "currency": "INR", "invoice_no": "..."}
    --   record   : {"book_title": "...", "year": 2024, "register_type": "..."}
    metadata             JSONB       NOT NULL DEFAULT '{}'::jsonb,

    -- Retrieval index columns (populated by cloud/index/ stage)
    document_summary     TEXT,
    index_status         VARCHAR,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_category
    ON documents (document_category);
CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents (status);
-- Partial indexes — only practitioner docs have these fields populated
CREATE INDEX IF NOT EXISTS idx_documents_registration_no
    ON documents (registration_no) WHERE registration_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_application_number
    ON documents (application_number) WHERE application_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_metadata
    ON documents USING GIN (metadata);


-- -----------------------------------------------------------------------------
-- pages: per-page OCR + structured output.
-- Same shape across all document categories.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pages (
    page_id              TEXT        PRIMARY KEY,         -- <document_id>:<page_num>
    document_id          TEXT        NOT NULL
        REFERENCES documents(document_id) ON DELETE CASCADE,
    page_num             INTEGER     NOT NULL CHECK (page_num >= 1),
    s3_key_image         TEXT        NOT NULL,

    page_type            TEXT,                             -- e.g. 'application_form', 'aadhaar',
                                                           --      'ssc', 'hsc',
                                                           --      'marks_statement',
                                                           --      'internship_cert',
                                                           --      'provisional_reg',
                                                           --      'form_e', 'marriage_cert',
                                                           --      'letter_body',
                                                           --      'invoice', 'blank'

    raw_text             TEXT,                             -- OCR output (Tesseract)
    structured_json      JSONB,                            -- LLM output (page-typed schema)
    confidence_score     REAL        CHECK (confidence_score IS NULL
                                     OR (confidence_score >= 0 AND confidence_score <= 100)),
    language_detected    TEXT,                             -- eng | mar | hin | mixed

    ocr_status           TEXT        NOT NULL DEFAULT 'pending'
        CHECK (ocr_status IN ('pending', 'queued', 'done', 'failed', 'skipped')),

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Retrieval index columns (populated by cloud/index/ stage)
    page_summary         TEXT,
    search_keywords      JSONB           NOT NULL DEFAULT '[]'::jsonb,
    index_entities       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    index_status         VARCHAR,

    UNIQUE (document_id, page_num)
);

CREATE INDEX IF NOT EXISTS idx_pages_document_id
    ON pages (document_id);
CREATE INDEX IF NOT EXISTS idx_pages_ocr_status
    ON pages (ocr_status);
CREATE INDEX IF NOT EXISTS idx_pages_page_type
    ON pages (page_type) WHERE page_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pages_structured_json
    ON pages USING GIN (structured_json);


-- -----------------------------------------------------------------------------
-- page_types : reference catalogue of known page type labels.
-- pages.page_type is a free TEXT column (no FK) — new types discovered during
-- classification can be stored without a prior schema change. This table exists
-- for management, reporting, and UI dropdowns only.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS page_types (
    name        TEXT        PRIMARY KEY,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO page_types (name, description) VALUES
    ('application_form',  'Practitioner registration application form (MCH Form)'),
    ('aadhaar',           'Aadhaar identity card page'),
    ('ssc',               'Secondary School Certificate (S.S.C.)'),
    ('hsc',               'Higher Secondary Certificate (H.S.C.)'),
    ('marks_statement',   'University statement of marks'),
    ('passing_cert',      'Passing / degree certificate'),
    ('internship_cert',   'Internship completion certificate'),
    ('provisional_reg',   'Provisional registration certificate'),
    ('form_e',            'Form E (name change / renewal)'),
    ('marriage_cert',     'Marriage certificate'),
    ('sbi_receipt',       'SBI e-receipt / challan'),
    ('photo_id',          'Photo identity document (PAN / driving licence / passport)'),
    ('letter_body',       'Official correspondence body'),
    ('invoice',           'Vendor invoice or cash memo'),
    ('blank',             'Blank or near-blank page'),
    ('other',             'Page type not yet classified')
ON CONFLICT (name) DO NOTHING;


-- -----------------------------------------------------------------------------
-- eval_content_type : ground-truth labels + cached CV features for calibrating
-- the triage typed-vs-handwritten detector. Dev/eval only; not on the hot path.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_content_type (
    page_id       TEXT PRIMARY KEY REFERENCES pages(page_id) ON DELETE CASCADE,
    s3_key_image  TEXT NOT NULL,
    label         TEXT CHECK (label IN ('typed', 'handwritten', 'unknown')),
    height_cv     REAL,
    stroke_cv     REAL,
    n_components  INTEGER,
    labeled_by    TEXT,
    labeled_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_content_type_label
    ON eval_content_type (label) WHERE label IS NOT NULL;


-- -----------------------------------------------------------------------------
-- updated_at triggers
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_documents_updated_at      ON documents;
DROP TRIGGER IF EXISTS set_pages_updated_at          ON pages;
DROP TRIGGER IF EXISTS set_reference_data_updated_at ON reference_data;
DROP TRIGGER IF EXISTS set_eval_content_type_updated_at ON eval_content_type;

CREATE TRIGGER set_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_pages_updated_at
    BEFORE UPDATE ON pages
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_reference_data_updated_at
    BEFORE UPDATE ON reference_data
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_eval_content_type_updated_at
    BEFORE UPDATE ON eval_content_type
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- -----------------------------------------------------------------------------
-- dashboard_users: credentials for the operations dashboard (HTTP Basic).
-- Seeded via scripts/add_dashboard_user.py. password_hash = bcrypt.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dashboard_users (
    username      TEXT        PRIMARY KEY,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- audit_log: one row per dashboard CONTROL action (read views not audited).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    username    TEXT        NOT NULL,
    action      TEXT        NOT NULL,          -- ingest | requeue_ocr | reclassify
    document_id TEXT,                          -- nullable
    params      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    result      TEXT        NOT NULL CHECK (result IN ('ok', 'error')),
    detail      TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_document_id ON audit_log (document_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_username    ON audit_log (username);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts          ON audit_log (ts DESC);