-- FilingFinder database schema. Safe to run more than once.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id                text PRIMARY KEY,
    ticker                  text    NOT NULL,
    company                 text    NOT NULL,
    form                    text    NOT NULL,
    fiscal_year             integer NOT NULL,
    report_date             date    NOT NULL,
    accession               text    NOT NULL,
    source_url              text    NOT NULL,
    section                 text    NOT NULL,  -- label as written in the filing
    item_code               text,              -- clean code: '1A', '7', '8'; null for front matter
    section_name            text    NOT NULL,  -- clean name: 'Risk Factors'
    is_financial_statements boolean NOT NULL DEFAULT false,  -- Item 8, or NVDA's Item 15
    page                    integer NOT NULL,  -- page in the HTML document
    printed_page            integer,           -- page number printed on the filing
    text                    text    NOT NULL,  -- original passage, shown to analysts
    search_text             text    NOT NULL,  -- text minus headers/footers, used for search
    embedding               vector(768),       -- meaning search (nomic-embed-text-v1.5)
    embedding_model         text,
    tsv                     tsvector GENERATED ALWAYS AS
                                (to_tsvector('english', search_text)) STORED  -- keyword search
);

-- Keyword search index.
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);

-- Filters: ticker, year, section.
CREATE INDEX IF NOT EXISTS chunks_filter_idx ON chunks (ticker, fiscal_year, item_code);

-- No approximate vector index on purpose: with ~4,000 rows an exact scan takes
-- milliseconds and always returns correct results when filters are applied.
-- Add an HNSW index if the corpus grows to hundreds of thousands of chunks.
