"""Add clean metadata and search text to parsed chunks before indexing.

Pure functions only (no database, no model) so they are easy to test.
"""
import re
from collections import Counter

ITEM_RE = re.compile(r"^Item (\d{1,2}[A-C]?)\.", re.I)

# Standard 10-K item names, so filters and citations don't depend on how
# each company capitalises or punctuates its headings.
ITEM_NAMES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "[Reserved]",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}

# Page headers/footers repeated on every page; they add noise to search.
BOILERPLATE_RE = re.compile(
    r"(table of contents(\s*\|.*)?"            # "Table of Contents | Alphabet Inc."
    r"|item \d{1,2}[a-c]?"                     # running header "Item 7" (no title)
    r"|\(continued\)"
    r"|.+\|\s*\d{4} form 10-k\s*\|\s*\d{1,3}"  # "Apple Inc. | 2024 Form 10-K | 23"
    r")",
    re.I,
)
PAGE_NUMBER_RE = re.compile(r"\d{1,3}\.?")
EMPTY_BODIES = {"", "none.", "none", "not applicable.", "not applicable", "[reserved]"}


def item_code(section):
    """'Item 1A. | Risk Factors' -> '1A'; 'Front matter' -> None."""
    m = ITEM_RE.match(section)
    return m.group(1).upper() if m else None


def section_name(section):
    code = item_code(section)
    if code:
        return ITEM_NAMES.get(code, section)
    return "Table of Contents" if section == "Table of Contents" else "Front Matter"


def clean_lines(text):
    """Drop header/footer lines; keep everything else in order."""
    lines = text.split("\n")
    out = [l for l in lines if not BOILERPLATE_RE.fullmatch(l.strip())]
    if out and PAGE_NUMBER_RE.fullmatch(out[-1].strip()):   # trailing page number
        out.pop()
    return out


def is_empty_item(lines):
    """True for chunks like 'Item 4. Mine Safety Disclosures / Not applicable.'"""
    body = [l for l in lines if not ITEM_RE.match(l)]
    return " ".join(body).strip().lower() in EMPTY_BODIES


def is_table_row(line):
    return " | " in line


def table_header(lines):
    """Caption + first row of the table that ends `lines`, or [] if none."""
    if not lines or not is_table_row(lines[-1]):
        return []
    start = len(lines) - 1
    while start > 0 and is_table_row(lines[start - 1]):
        start -= 1
    caption = [lines[start - 1]] if start > 0 else []
    return caption + [lines[start]]


def page_key(chunk):
    return (chunk["ticker"], chunk["report_date"], chunk["page"])


def financial_statement_codes(chunks):
    """Per filing, which item codes hold the financial statements.

    Usually Item 8. Some filers (e.g. NVIDIA) leave Item 8 as a one-line
    pointer and put the statements under Item 15, so flag both there.
    """
    item8 = Counter((c["ticker"], c["report_date"]) for c in chunks
                    if item_code(c["section"]) == "8")
    filings = {(c["ticker"], c["report_date"]) for c in chunks}
    return {f: {"8", "15"} if item8[f] <= 2 else {"8"} for f in filings}


def enrich(chunks):
    """Return index-ready rows. Skips chunks with no real content."""
    fs_codes = financial_statement_codes(chunks)
    rows, prev, prev_search = [], None, []
    for c in chunks:
        lines = clean_lines(c["text"])
        code = item_code(c["section"])
        if is_empty_item(lines):
            prev, prev_search = c, []
            continue

        # A table cut in two by the chunk size limit: repeat its header on
        # the second half so the numbers keep their column labels.
        search = lines
        if (prev and page_key(prev) == page_key(c)
                and lines and is_table_row(lines[0])):
            search = table_header(prev_search) + lines

        printed = c["printed_page"]
        rows.append({
            **c,
            "fiscal_year": int(c["report_date"][:4]),
            "item_code": code,
            "section_name": section_name(c["section"]),
            "is_financial_statements": code in fs_codes[(c["ticker"], c["report_date"])],
            "printed_page": int(printed) if printed else None,
            "search_text": "\n".join(search).strip(),
        })
        prev, prev_search = c, search
    return rows
