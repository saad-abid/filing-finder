from src.retrieval.query_parser import QueryFilters
from src.retrieval.retrieve import fuse, in_corpus, where_clause


def row(cid, ticker="AAPL", year=2024):
    return (cid, ticker, "Apple", year, None, "acc", "url", "Risk Factors", "1A", 10, 8, "text")


def test_fuse_rewards_passages_found_by_both_methods():
    out = fuse({
        "vector":  [row("a"), row("b"), row("c")],
        "keyword": [row("c"), row("d")],
    }, k=10)
    assert out[0].chunk_id == "c"            # ranked by both methods
    assert out[0].found_by == {"vector", "keyword"}
    assert out[1].chunk_id == "a"            # rank 1 in one method
    assert {p.chunk_id for p in out[2:4]} == {"b", "d"}   # both rank 2 in one method: tie


def test_fuse_respects_k():
    assert len(fuse({"vector": [row(str(i)) for i in range(10)]}, k=3)) == 3


def test_in_corpus():
    available = [("AAPL", 2024), ("NVDA", 2025)]
    assert in_corpus(available, "AAPL", 2024)
    assert not in_corpus(available, "NVDA", 2026)
    assert in_corpus(available, None, 2025)
    assert in_corpus(available, "AAPL", None)


def test_where_clause_combines_filters():
    where, params = where_clause("NVDA", 2024, QueryFilters(item_codes=["7"], financial_statements=True))
    assert where == ("ticker = %(ticker)s AND fiscal_year = %(year)s AND "
                     "(item_code = ANY(%(codes)s) OR is_financial_statements)")
    assert params == {"ticker": "NVDA", "year": 2024, "codes": ["7"]}
    assert where_clause(None, None, QueryFilters()) == ("TRUE", {})
