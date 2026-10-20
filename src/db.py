"""Database connection helper (reads DATABASE_URL from .env)."""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db/schema.sql"


def connect(with_vector=True):
    """Open a connection. with_vector=False is needed before the extension exists."""
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is missing. Copy it from .env.example into .env.")
    try:
        conn = psycopg.connect(url, connect_timeout=10)
    except psycopg.OperationalError as e:
        raise SystemExit(f"Can't reach the database ({e}).\n"
                         "Is Docker Desktop running? Try: docker compose up -d")
    if with_vector:
        register_vector(conn)
    return conn


def apply_schema(conn):
    """Create the extension, table and indexes if they don't exist yet."""
    conn.execute(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
