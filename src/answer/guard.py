"""Safety rules around the model: refuse out-of-scope questions, and check
every sentence of an answer before an analyst sees it.

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
FORM_NAME_RE = re.compile(r"\b(?:Form\s+)?10-[KQ]\b", re.I)


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
        result.sentences.append((text, valid))

    limitations = reply.get("limitations", "").strip()
    figures = {n for n in numbers_in(limitations) if not YEAR_RE.fullmatch(n)}
    if figures:
        result.dropped.append((limitations, "uncited numbers in limitations"))
    elif limitations:
        result.limitations = limitations

    result.status = "answered" if result.sentences else "not_found"
    return result
