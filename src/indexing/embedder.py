"""Turn text into vectors with a free, local embedding model.

The same model must be used for documents (at indexing time) and for
questions (at search time), so both live here.
"""
import hashlib
from functools import lru_cache

MODEL_NAME = "nomic-ai/modernbert-embed-base"
DIMENSIONS = 768
MAX_TOKENS = 2048   # our longest chunks are ~1,100 tokens; nothing gets cut off

# This model expects these prefixes to tell questions and passages apart.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer  # slow import; load on demand
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    model.max_seq_length = MAX_TOKENS
    return model


def document_input(row):
    """What gets embedded for a chunk: a short context line plus the text.

    The context line (company, year, section) helps meaning search tell
    apart near-identical boilerplate from different filings.
    """
    header = (f"{row['company']} ({row['ticker']}) {row['form']} fiscal "
              f"{row['fiscal_year']}, {row['section_name']}")
    return f"{DOC_PREFIX}{header}\n{row['search_text']}"


def input_hash(text):
    return hashlib.sha1(f"{MODEL_NAME}\n{text}".encode("utf-8")).hexdigest()


def embed_documents(texts, batch_size=16):
    """texts must already include DOC_PREFIX (see document_input)."""
    return get_model().encode(texts, batch_size=batch_size, normalize_embeddings=True)


def embed_query(question):
    return get_model().encode([QUERY_PREFIX + question], normalize_embeddings=True)[0]
