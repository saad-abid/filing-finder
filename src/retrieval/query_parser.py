"""Pull search filters (companies, years, sections) out of a plain-English question.

Rule-based on purpose: predictable, fast and easy to test. Anything it
doesn't recognise simply isn't filtered on, so a miss widens the search
instead of hiding results.
"""
import re
from dataclasses import dataclass, field

# Company names and tickers only. Product names (Azure, iPhone...) are left
# out because a question can mention a rival's product.
COMPANY_ALIASES = {
    "AAPL": ["apple", "aapl"],
    "AMZN": ["amazon", "amzn", "aws"],
    "GOOGL": ["alphabet", "google", "googl", "goog"],
    "MSFT": ["microsoft", "msft"],
    "NVDA": ["nvidia", "nvda"],
}

# Phrase -> 10-K item code. Only unambiguous phrases.
SECTION_PHRASES = {
    "risk factor": "1A",
    "md&a": "7",
    "management's discussion": "7",
    "management’s discussion": "7",
    "market risk": "7A",
    "legal proceeding": "3",
    "cybersecurity": "1C",
    "executive compensation": "11",
    "controls and procedures": "9A",
}
FINANCIAL_PHRASES = [
    "financial statement", "balance sheet", "income statement",
    "cash flow statement", "statement of operations", "notes to the",
]
LATEST_RE = re.compile(r"\b(latest|most recent|newest|current)\b", re.I)
# Questions about change need every year searched separately, even with no years named.
OVER_TIME_RE = re.compile(
    r"\b(over time|chang(e|ed|es|ing)|trends?|year over year|evolv(e|ed|ing)|"
    r"across the available|more urgent|less urgent|added|removed)\b", re.I)
# Questions about "which companies" need every company searched separately.
ALL_COMPANIES_RE = re.compile(r"\b(companies|each company|every company|all five)\b", re.I)
YEAR = r"(?:fy|fiscal(?:\s+year)?)?\s*'?(20[12]\d)"
RANGE_RE = re.compile(
    rf"(?:from\s+|between\s+)?{YEAR}\s*(?:-|–|—|to|through|thru|and)\s*{YEAR}", re.I)
SINGLE_YEAR_RE = re.compile(rf"\b{YEAR}\b", re.I)


# Words that describe the *question* rather than the *topic*. They appear all
# over the filings, so they only add noise to the search itself.
QUESTION_WORDS_RE = re.compile(
    r"\b(how|what|which|did|does|do|say|says|said|describe[sd]?|description|compare[sd]?|"
    r"change[sd]?|changing|added|removed|over time|year over year|trends?|differ(ed)?|become|became|"
    r"wording|more urgent|less urgent|latest|most recent|10-?ks?|filings?|"
    r"each company'?s?|which companies|companies|company'?s|"
    # section names become filters, so searching for them too just finds headings
    r"risk[- ]factors?( language)?|language|md&a|management[’']s discussion( and analysis)?|"
    r"financial statements?)\b", re.I)


# Aliases that are also a topic (AWS is Amazon's cloud segment): use them as a
# filter but keep them in the search text.
KEEP_IN_SEARCH = {"aws"}
EDGE_WORDS_RE = re.compile(
    r"^(?:(?:and|or|the|of|in|for|are|is|with|from|to|on|about)\b[\s,]*)+"
    r"|(?:[\s,]*\b(?:and|or|the|of|in|for|are|is|with|from|to|on|about))+$", re.I)


@dataclass
class QueryFilters:
    tickers: list = field(default_factory=list)       # [] = all companies
    years: list = field(default_factory=list)         # [] = all years
    latest: bool = False                              # newest filing per company
    item_codes: list = field(default_factory=list)    # [] = all sections
    financial_statements: bool = False
    over_time: bool = False                           # search each year separately
    all_companies: bool = False                       # search each company separately


def find_tickers(q):
    found = []
    for ticker, aliases in COMPANY_ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", q) for a in aliases):
            found.append(ticker)
    return found


def find_years(q):
    years = set()
    for a, b in RANGE_RE.findall(q):
        lo, hi = sorted((int(a), int(b)))
        years.update(range(lo, hi + 1))
    q_without_ranges = RANGE_RE.sub(" ", q)
    years.update(int(y) for y in SINGLE_YEAR_RE.findall(q_without_ranges))
    return sorted(years)


def search_text(question):
    """The topic part of a question, used for vector and keyword search.

    Company names and years are removed because filters already handle
    them; question words are removed because they match everywhere.
    'How did Apple describe supplier concentration in 2024?' -> 'supplier concentration'
    """
    q = RANGE_RE.sub(" ", question)
    q = SINGLE_YEAR_RE.sub(" ", q)
    for aliases in COMPANY_ALIASES.values():
        for a in aliases:
            if a not in KEEP_IN_SEARCH:
                q = re.sub(rf"\b{re.escape(a)}('s|’s)?\b", " ", q, flags=re.I)
    q = QUESTION_WORDS_RE.sub(" ", q)
    q = re.sub(r"\s*,[\s,]*", ", ", " ".join(q.split()))           # ",, ," -> ", "
    q = re.sub(r"\s+([?.])", r"\1", q)
    for _ in range(3):   # trim dangling connector words left behind at either end
        q = EDGE_WORDS_RE.sub("", q.strip(" ,?.")).strip(" ,?.")
    return q if len(q) >= 3 else question


def parse_query(question):
    q = question.lower()
    words = q.replace("-", " ")   # "risk-factor" -> "risk factor"; keep q for year ranges
    return QueryFilters(
        tickers=find_tickers(q),
        years=find_years(q),
        latest=bool(LATEST_RE.search(q)),
        item_codes=sorted({code for phrase, code in SECTION_PHRASES.items() if phrase in words}),
        financial_statements=any(p in words for p in FINANCIAL_PHRASES),
        over_time=bool(OVER_TIME_RE.search(words)),
        all_companies=bool(ALL_COMPANIES_RE.search(q)),
    )
