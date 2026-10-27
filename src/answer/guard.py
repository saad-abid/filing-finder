"""Safety rules around the model: refuse out-of-scope questions, and check
every sentence of an answer before the user sees it.

A wrong confident answer is worse than "not found", so anything that can't be
traced back to a cited passage is removed.
"""
import re
from dataclasses import dataclass, field

ADVICE_RE = re.compile(
    r"\b(should (i|we|you) (buy|sell|short|hold|invest)|buy or sell|"
    r"(good|bad) investment|price target|worth (buying|investing)|"
    r"stock (price )?(will|going to|go) (go )?(up|down|rise|fall)|"
    r"(undervalued|overvalued)|recommend (buying|selling|investing))\b", re.I)

REFUSAL_MESSAGE = ("I can't give investment advice or stock predictions. I can only report "
                   "what the 10-K filings say. Try asking what a filing discloses, e.g. "
                   "about revenue, risks or outlook statements.")

NUMBER_RE = re.compile(r"(\$)?\s?(\d[\d,]*(?:\.\d+)?)\s?(%|percent\b|billion\b|million\b|thousand\b)?", re.I)
CITATION_MARK_RE = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")
YEAR_RE = re.compile(r"(19|20)\d\d")
YEARS_IN_TEXT_RE = re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)")   # also finds "FY2021"
FORM_NAME_RE = re.compile(r"\b(?:Form\s+)?10-[KQ]\b", re.I)

UP_WORDS = ("increas", "grew", "grow", "rose", "rise", "rising")
VERB_RE = re.compile(r"\b(increas\w*|grew|grow\w*|rose|ris(?:e|es|ing)|decreas\w*|declin\w*|fell|dropp\w*)\b", re.I)
FIGURE = r"\$?\s?\(?-?\d[\d,]*(?:\.\d+)?\)?%?"
FROM_TO_RE = re.compile(rf"\bfrom\s+({FIGURE})(?:\s+[a-z]+){{0,3}}?\s+to\s+({FIGURE})", re.I)
CHANGE_RE = re.compile(
    r"\b(added|adds|removed|introduced|newly|no longer|for the first time|"
    r"became (?:more|less)|more urgent|less urgent)\b", re.I)
HEADER_RE = re.compile(r"(.+?) 10-K FY(\d{4})")    # passage header from prompts.passage_header
LABEL_STOP = {"and", "the", "for", "net", "total", "other", "inc.", "including"}
GENERIC_COLUMNS = {"change", "% change", "$ change", "total", "consolidated", ""}


@dataclass
class Checked:
    status: str                                    # "answered" or "not_found"
    sentences: list = field(default_factory=list)  # [(text, [citation numbers])]
    limitations: str = ""
    dropped: list = field(default_factory=list)    # [(text, reason)]


def refusal_reason(question):
    """A message if the question asks for advice or predictions, else None."""
    return REFUSAL_MESSAGE if ADVICE_RE.search(question) else None


def numbers_in(text):
    """Numbers as plain digit strings: '$201,183' -> '201183', '13%' -> '13'.

    Bare single digits are skipped: they mostly come from things like "Note 1"
    and would make the check noisy. A single digit that is clearly a figure
    ("$5 billion", "9%") is kept.
    """
    out = set()
    text = FORM_NAME_RE.sub(" ", text)   # "10-K" is a form name, not a figure
    for dollar, num, unit in NUMBER_RE.findall(text):
        n = num.replace(",", "").rstrip(".")
        if len(n.replace(".", "")) > 1 or dollar or unit:
            out.add(n)
    return out


def direction_problem(text):
    """'increased from A to B' needs B > A; 'decreased from A to B' needs B < A."""
    verbs = list(VERB_RE.finditer(text))
    for i, verb in enumerate(verbs):
        end = verbs[i + 1].start() if i + 1 < len(verbs) else len(text)
        for pair in FROM_TO_RE.finditer(text, verb.end(), end):
            a, b = pair.group(1), pair.group(2)
            if YEAR_RE.fullmatch(a) and YEAR_RE.fullmatch(b):
                continue   # "from 2021 to 2025" is a time span, not the figures
            up = verb.group(1).lower().startswith(UP_WORDS)
            if (up and signed(b) < signed(a)) or (not up and signed(b) > signed(a)):
                return f"says '{verb.group(1)}' but the figure went from {a} to {b}"
            break
    return None


def signed(figure):
    value = float(re.sub(r"[^\d.]", "", figure))
    return -value if "(" in figure or "-" in figure else value


def change_problem(text, passages):
    """Claims that something was added/removed/became more urgent need two years to compare."""
    if not CHANGE_RE.search(text):
        return None
    years = {}
    for p in passages:
        m = HEADER_RE.match(p)
        if m:
            years.setdefault(m.group(1), set()).add(m.group(2))
    if any(len(ys) >= 2 for ys in years.values()):
        return None
    return "describes a change over time but cites only one year's filing"


def label_problem(text, passages):
    """A figure taken from a table must be described with its row label and column year.

    Catches real numbers attached to the wrong line or year, e.g. Alphabet's
    2023 total revenues presented as 2025 EMEA revenue. Only figures with 3+
    digits are checked; small numbers like percentages repeat across rows.
    """
    lower = text.lower()
    years = set(YEARS_IN_TEXT_RE.findall(text))
    for num in sorted(numbers_in(text)):
        if YEAR_RE.fullmatch(num) or len(num.split(".")[0]) < 3:
            continue
        spots = [s for p in passages for s in table_spots(p, num)]
        if spots and not any(spot_matches(row, col, lower, years) for row, col in spots):
            row, col = spots[0]
            where = f"row '{row}'" + (f", column '{col}'" if col else "")
            return f"{num} is in the table at {where}, which the sentence doesn't match"
    return None


def table_spots(passage, num):
    """[(row label, column header)] for each table cell in the passage holding `num`."""
    lines = passage.split("\n")
    spots = []
    for i, line in enumerate(lines):
        if " | " not in line:
            continue
        cells = [c.strip() for c in line.split(" | ")]
        for k, cell in enumerate(cells[1:], start=1):
            if num in numbers_in(cell):
                header = find_header(lines, i)
                col = None
                if header and len(header) == len(cells) - 1:
                    col = header[k - 1]
                elif header and len(header) == len(cells):
                    col = header[k]
                label = "" if numbers_in(cells[0]) else cells[0]
                spots.append((label, col))
    return spots


def find_header(lines, row_index):
    """The nearest table line above the row that holds column names or years, not amounts."""
    for j in range(row_index - 1, max(row_index - 30, -1), -1):
        line = lines[j]
        if " | " not in line or HEADER_RE.match(line):   # stop at prose or the passage title
            return None
        if "$" in line:
            continue
        amounts = [n for n in numbers_in(line) if not YEAR_RE.fullmatch(n)]
        if all(len(n.split(".")[0]) < 3 for n in amounts):
            return [c.strip() for c in line.split(" | ")]
    return None


def label_words(label):
    label = re.sub(r"\([^)]*\)", " ", label.lower())   # drop "(1)", "(in millions)"
    return [w for w in re.findall(r"[a-z][a-z&.]+", label) if len(w) > 2 and w not in LABEL_STOP]


def mentions(lower, words):
    return any(re.search(rf"\b{re.escape(w)}", lower) for w in words)


def spot_matches(row, col, lower, years):
    words = label_words(row)
    if words and not mentions(lower, words):
        return False
    if not col:
        return True
    col_year = re.search(r"(?:19|20)\d\d", col)
    if col_year:
        return not years or col_year.group(0) in years
    col_words = label_words(col)
    return not col_words or col.lower() in GENERIC_COLUMNS or mentions(lower, col_words)


def check(reply, shown):
    """Keep only sentences that cite real passages and whose numbers appear in them.

    reply: the model's JSON ({"sentences", "limitations"})
    shown: {passage number: exact text the model was shown for it}
    """
    result = Checked(status="not_found")
    for s in reply.get("sentences", []):
        text = CITATION_MARK_RE.sub("", s.get("text", "")).strip()
        if not text:
            continue
        cites = sorted({c for c in s.get("citations", []) if isinstance(c, int)})
        valid = [c for c in cites if c in shown]
        if not valid:
            result.dropped.append((text, "no valid citation"))
            continue
        cited_numbers = set().union(*(numbers_in(shown[c]) for c in valid))
        unsupported = numbers_in(text) - cited_numbers
        if unsupported:
            result.dropped.append((text, f"numbers not in cited passage: {', '.join(sorted(unsupported))}"))
            continue
        cited = [shown[c] for c in valid]
        problem = direction_problem(text) or change_problem(text, cited) or label_problem(text, cited)
        if problem:
            result.dropped.append((text, problem))
            continue
        result.sentences.append((text, valid))

    limitations = reply.get("limitations", "").strip()
    figures = {n for n in numbers_in(limitations) if not YEAR_RE.fullmatch(n)}
    if figures:
        result.dropped.append((limitations, "uncited numbers in limitations"))
    elif limitations:
        result.limitations = limitations

    result.status = "answered" if result.sentences else "not_found"
    return result
