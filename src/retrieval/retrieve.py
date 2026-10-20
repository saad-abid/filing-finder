"""Hybrid search over the indexed filings: meaning (vector) + keyword, with filters.

Try it from the project folder:
    python -m src.retrieval.retrieve "How did NVIDIA describe export controls in fiscal 2024?"

Comparison questions (several companies and/or years) are split into one
search per company-year group, each with its own share of the results, so
one company can't crowd out the others.
"""
import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import product

from src.db import connect
from src.indexing.embedder import embed_query
from src.retrieval.query_parser import QueryFilters, parse_query, search_text

RRF_K = 60          # standard Reciprocal Rank Fusion constant
CANDIDATES = 40     # rows fetched from each search method before merging

PASSAGE_COLS = """chunk_id, ticker, company, fiscal_year, report_date, accession,
    source_url, section_name, item_code, page, printed_page, text"""


@dataclass
class Passage:
    chunk_id: str
    ticker: str
    company: str
    fiscal_year: int
    report_date: object
    accession: str
    source_url: str
    section_name: str
    item_code: str
    page: int
    printed_page: int
    text: str
    score: float = 0.0
    found_by: set = field(default_factory=set)   # {"vector", "keyword"}

    def citation(self):
        page = f"p. {self.printed_page}" if self.printed_page else f"HTML page {self.page}"
        return f"{self.company} 10-K FY{self.fiscal_year}, {self.section_name}, {page}"


@dataclass
class RetrievalResult:
    filters: QueryFilters
    groups: list            # [(ticker or None, year or None), ...]
    passages: list          # [Passage], grouped in group order, best first
    missing: list           # groups with no filing in the corpus
    search_text: str = ""   # topic actually searched for (see query_parser.search_text)


def where_clause(ticker, year, f):
    conds, params = [], {}
    if ticker:
        conds.append("ticker = %(ticker)s")
        params["ticker"] = ticker
    if year:
        conds.append("fiscal_year = %(year)s")
        params["year"] = year
    if f.item_codes and f.financial_statements:
        conds.append("(item_code = ANY(%(codes)s) OR is_financial_statements)")
        params["codes"] = f.item_codes
    elif f.item_codes:
        conds.append("item_code = ANY(%(codes)s)")
        params["codes"] = f.item_codes
    elif f.financial_statements:
        conds.append("is_financial_statements")
    return " AND ".join(conds) or "TRUE", params


def vector_search(conn, qvec, where, params, n):
    sql = f"""SELECT {PASSAGE_COLS} FROM chunks
              WHERE {where} AND embedding IS NOT NULL
              ORDER BY embedding <=> %(qvec)s LIMIT %(n)s"""
    return conn.execute(sql, {**params, "qvec": qvec, "n": n}).fetchall()


def keyword_search(conn, question, where, params, n):
    # Match ANY of the question's words (plainto_tsquery would require all of
    # them), ranked by how densely they appear.
    sql = f"""WITH q AS (SELECT to_tsquery('english',
                  replace(plainto_tsquery('english', %(question)s)::text, ' & ', ' | ')) AS q)
              SELECT {PASSAGE_COLS} FROM chunks, q
              WHERE {where} AND tsv @@ q.q
              ORDER BY ts_rank_cd(tsv, q.q) DESC LIMIT %(n)s"""
    return conn.execute(sql, {**params, "question": question, "n": n}).fetchall()


def fuse(result_lists, k):
    """Reciprocal Rank Fusion: score = sum of 1/(60 + rank) across methods."""
    passages = {}
    for method, rows in result_lists.items():
        for rank, row in enumerate(rows, start=1):
            p = passages.get(row[0]) or Passage(*row)
            p.score += 1 / (RRF_K + rank)
            p.found_by.add(method)
            passages[row[0]] = p
    return sorted(passages.values(), key=lambda p: p.score, reverse=True)[:k]


def plan_groups(conn, f):
    """Turn filters into company-year groups to search separately.

    - named companies/years: one group per combination
    - "latest": each company's newest filing (plus the one before, if the
      question is about change)
    - "over time" with no years named: every year in the corpus
    - "which companies" with none named: every company
    """
    tickers = f.tickers
    if not tickers and (f.all_companies or (f.latest and not f.years)):
        tickers = [t for (t,) in conn.execute("SELECT DISTINCT ticker FROM chunks ORDER BY 1")]

    if f.latest and not f.years:
        years_by_ticker = defaultdict(list)
        for t, y in conn.execute("SELECT DISTINCT ticker, fiscal_year FROM chunks "
                                 "WHERE ticker = ANY(%s) ORDER BY 1, 2 DESC", (tickers,)):
            years_by_ticker[t].append(y)
        keep = 2 if f.over_time else 1
        return [(t, y) for t in tickers for y in years_by_ticker[t][:keep]]

    years = f.years
    if not years and f.over_time:
        years = [y for (y,) in conn.execute("SELECT DISTINCT fiscal_year FROM chunks ORDER BY 1")]
    return list(product(tickers or [None], years or [None]))


def in_corpus(available, ticker, year):
    return any((ticker is None or t == ticker) and (year is None or y == year)
               for t, y in available)


def retrieve(question, filters=None, total=30, min_per_group=3, conn=None):
    """Find the passages most relevant to `question`.

    filters: override what parse_query() would detect.
    total: rough passage budget, shared across company-year groups.
    """
    f = filters or parse_query(question)
    topic = search_text(question)
    own_conn = conn is None
    conn = conn or connect()
    try:
        groups = plan_groups(conn, f)
        available = conn.execute("SELECT DISTINCT ticker, fiscal_year FROM chunks").fetchall()
        per_group = max(min_per_group, total // len(groups))
        qvec = embed_query(topic)

        passages, missing = [], []
        for ticker, year in groups:
            if not in_corpus(available, ticker, year):
                missing.append((ticker, year))
                continue
            where, params = where_clause(ticker, year, f)
            passages += fuse({
                "vector": vector_search(conn, qvec, where, params, CANDIDATES),
                "keyword": keyword_search(conn, topic, where, params, CANDIDATES),
            }, per_group)
        return RetrievalResult(f, groups, passages, missing, topic)
    finally:
        if own_conn:
            conn.close()


def main():
    ap = argparse.ArgumentParser(description="Search the filings.")
    ap.add_argument("question")
    ap.add_argument("--total", type=int, default=30, help="passage budget (default 30)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    r = retrieve(args.question, total=args.total)
    f = r.filters
    print(f"Filters: companies={f.tickers or 'all'} years={f.years or ('latest' if f.latest else 'all')} "
          f"sections={f.item_codes or 'all'} financial_statements={f.financial_statements}")
    print(f"Searching for: {r.search_text!r}")
    print(f"Searched {len(r.groups)} group(s); {len(r.passages)} passages.")
    if r.missing:
        print("NOT IN CORPUS:", ", ".join(f"{t or 'any'} FY{y or 'any'}" for t, y in r.missing))
    by_group = defaultdict(list)
    for p in r.passages:
        by_group[(p.ticker, p.fiscal_year)].append(p)
    for (ticker, year), ps in by_group.items():
        print(f"\n=== {ticker} FY{year} ===")
        for p in ps:
            snippet = " ".join(p.text.split())[:160]
            print(f"  [{p.score:.4f} {'+'.join(sorted(p.found_by))}] {p.citation()}\n      {snippet}...")


if __name__ == "__main__":
    main()
