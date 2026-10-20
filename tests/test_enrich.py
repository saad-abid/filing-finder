from src.indexing.enrich import (
    clean_lines, enrich, is_empty_item, item_code, section_name, table_header,
)


def chunk(text, section="Item 7. Management's Discussion", page=30, ticker="AAPL",
          report_date="2024-09-28", printed_page="28", n=1):
    return {
        "chunk_id": f"{ticker}_{report_date}_p{page:03d}_{n}", "ticker": ticker,
        "company": "Apple", "form": "10-K", "report_date": report_date,
        "accession": "x", "source_url": "u", "section": section, "page": page,
        "printed_page": printed_page, "text": text,
    }


def test_item_code_handles_label_variants():
    assert item_code("Item 1A. RISK FACTORS") == "1A"
    assert item_code("Item 1A. | Risk Factors") == "1A"
    assert item_code("Item 8.") == "8"
    assert item_code("Front matter") is None
    assert section_name("Item 7. | Management’s Discussion") == "Management's Discussion and Analysis"
    assert section_name("Table of Contents") == "Table of Contents"


def test_clean_lines_drops_headers_and_footers():
    text = ("Table of Contents | Alphabet Inc.\nItem 7\nRevenue grew.\n"
            "Total | $5 | $6\n(Continued)\nApple Inc. | 2024 Form 10-K | 23")
    assert clean_lines(text) == ["Revenue grew.", "Total | $5 | $6"]
    assert clean_lines("Revenue grew.\n39.") == ["Revenue grew."]


def test_clean_lines_keeps_item_headings_with_titles():
    assert clean_lines("Item 8.\nFinancial Statements") == ["Item 8.", "Financial Statements"]


def test_is_empty_item():
    assert is_empty_item(["Item 4. Mine Safety Disclosures", "Not applicable."])
    assert is_empty_item(["Item 1B. Unresolved Staff Comments", "None."])
    assert not is_empty_item(["Item 3. Legal Proceedings", "See Note 12."])


def test_table_header_returns_caption_and_first_row():
    lines = ["Net sales by category:", "2024 | 2023", "iPhone | $201 | $200"]
    assert table_header(lines) == ["Net sales by category:", "2024 | 2023"]
    assert table_header(["Just prose."]) == []


def test_enrich_repeats_header_on_split_table():
    first = chunk("Net sales by category:\n2024 | 2023\niPhone | $201 | $200", n=1)
    second = chunk("Mac | $30 | $29\nTotal | $391 | $383", n=2)
    rows = enrich([first, second])
    assert rows[1]["search_text"].startswith("Net sales by category:\n2024 | 2023\nMac")
    assert rows[1]["text"] == second["text"]   # original text shown to analysts is untouched


def test_enrich_does_not_join_tables_across_pages():
    first = chunk("2024 | 2023\niPhone | $201 | $200", page=30)
    second = chunk("Mac | $30 | $29", page=31)
    assert enrich([first, second])[1]["search_text"] == "Mac | $30 | $29"


def test_enrich_adds_metadata_and_skips_empty_items():
    rows = enrich([
        chunk("Item 4. Mine Safety Disclosures\nNot applicable.", section="Item 4. Mine Safety Disclosures"),
        chunk("Risk text here.", section="Item 1A. RISK FACTORS", printed_page=None, n=2),
    ])
    assert len(rows) == 1
    r = rows[0]
    assert (r["fiscal_year"], r["item_code"], r["section_name"]) == (2024, "1A", "Risk Factors")
    assert r["printed_page"] is None


def test_financial_statements_flag_follows_item_15_when_item_8_is_a_pointer():
    nvda = dict(ticker="NVDA", report_date="2025-01-26")
    rows = enrich([
        chunk("Item 8. Financial Statements\nSee Item 15.", section="Item 8. Financial Statements", **nvda),
        chunk("Consolidated balance sheet...", section="Item 15. Exhibits", n=2, **nvda),
        chunk("Item 8. Financial Statements\nBalance sheet", section="Item 8.", page=50),
        chunk("Balance sheet 2", section="Item 8.", page=51),
        chunk("Balance sheet 3", section="Item 8.", page=52),
        chunk("Exhibit index", section="Item 15. Exhibits", page=60),
    ])
    flags = {(r["ticker"], r["item_code"]): r["is_financial_statements"] for r in rows}
    assert flags[("NVDA", "15")] is True
    assert flags[("AAPL", "8")] is True
    assert flags[("AAPL", "15")] is False
