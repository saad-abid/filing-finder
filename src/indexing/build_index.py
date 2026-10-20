"""Load data/processed/chunks.jsonl into Postgres and compute embeddings.

Run from the project folder:  python -m src.indexing.build_index

Safe to re-run: unchanged chunks keep their embeddings, so only new or
changed chunks are embedded again. Progress is saved after every batch,
so you can stop it (Ctrl+C) and run it again to continue.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from src.db import apply_schema, connect
from src.indexing import embedder
from src.indexing.enrich import enrich

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = ROOT / "data/processed/chunks.jsonl"

COLUMNS = [
    "chunk_id", "ticker", "company", "form", "fiscal_year", "report_date",
    "accession", "source_url", "section", "item_code", "section_name",
    "is_financial_statements", "page", "printed_page", "text", "search_text",
    "embedding_model", "embed_input_hash",
]

# On conflict, keep the old embedding only if exactly the same input was embedded.
UPSERT = f"""
INSERT INTO chunks ({", ".join(COLUMNS)})
VALUES ({", ".join("%(" + c + ")s" for c in COLUMNS)})
ON CONFLICT (chunk_id) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])},
    embedding = CASE WHEN chunks.embed_input_hash = EXCLUDED.embed_input_hash
                     THEN chunks.embedding END
"""


def load_rows():
    with CHUNKS.open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    rows = enrich(chunks)
    for r in rows:
        r["embedding_model"] = embedder.MODEL_NAME
        r["embed_input_hash"] = embedder.input_hash(embedder.document_input(r))
    return chunks, rows


def sync_rows(conn, rows):
    """Insert/update every chunk and delete ones no longer in the file."""
    with conn.cursor() as cur:
        cur.executemany(UPSERT, rows)
        cur.execute("DELETE FROM chunks WHERE NOT (chunk_id = ANY(%s))",
                    ([r["chunk_id"] for r in rows],))
        deleted = cur.rowcount
    conn.commit()
    return deleted


def embed_missing(conn, rows, batch_size):
    by_id = {r["chunk_id"]: r for r in rows}
    todo = [cid for (cid,) in conn.execute(
        "SELECT chunk_id FROM chunks WHERE embedding IS NULL ORDER BY chunk_id")]
    if not todo:
        print("All chunks already have embeddings.")
        return
    print(f"Embedding {len(todo)} chunks with {embedder.MODEL_NAME} "
          f"(first run downloads the model, ~600 MB)...")
    start = time.time()
    for i in range(0, len(todo), batch_size):
        ids = todo[i:i + batch_size]
        vectors = embedder.embed_documents([embedder.document_input(by_id[c]) for c in ids])
        with conn.cursor() as cur:
            cur.executemany("UPDATE chunks SET embedding = %s WHERE chunk_id = %s",
                            list(zip(vectors, ids)))
        conn.commit()   # save progress after every batch
        done = i + len(ids)
        rate = (time.time() - start) / done
        print(f"  {done}/{len(todo)} done, about {rate * (len(todo) - done) / 60:.0f} min left",
              flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--batch-size", type=int, default=64,
                    help="chunks embedded and saved per step (default 64)")
    ap.add_argument("--no-embed", action="store_true",
                    help="load text and metadata only; skip embeddings")
    args = ap.parse_args()

    if not CHUNKS.exists():
        sys.exit(f"{CHUNKS} not found. Run src/parsing/parse_filings.py first.")

    chunks, rows = load_rows()
    print(f"Read {len(chunks)} chunks; {len(chunks) - len(rows)} empty ones skipped "
          f"(e.g. 'Item 4. Not applicable.'); {len(rows)} to index.")

    with connect(with_vector=False) as conn:
        apply_schema(conn)
    with connect() as conn:
        deleted = sync_rows(conn, rows)
        print(f"Saved text and metadata. Removed {deleted} outdated chunks.")
        if not args.no_embed:
            embed_missing(conn, rows, args.batch_size)
        total, embedded = conn.execute(
            "SELECT count(*), count(embedding) FROM chunks").fetchone()
    print(f"Done. Database has {total} chunks, {embedded} with embeddings.")


if __name__ == "__main__":
    main()
