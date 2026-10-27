"""Choose, trim and number passages, and write the instructions for the model.

The local model reads slowly on CPU, so it gets a small, fair selection of
passages, each trimmed to its most relevant part.
"""
import re
from collections import OrderedDict

CONTEXT_CHARS = 16000        # total passage text sent to the model (~4,000 tokens)
SINGLE_GROUP_PASSAGES = 8    # e.g. "Apple 2024 ..." (one company, one year)
MAX_PASSAGE_CHARS = 1800
MIN_PASSAGE_CHARS = 600

SYSTEM_PROMPT = """You answer questions about companies' SEC 10-K filings.
Use ONLY the numbered SEC 10-K passages you are given.

Rules:
1. Use only facts stated in the passages. Never use outside knowledge.
2. Every sentence must list the numbers of the passages that support it in "citations".
3. Copy numbers exactly as written in the passages, with units ("$201,183 million", "13%").
   Do not round, convert or calculate new numbers.
   For a number from a table, name its row label and the year from its column header,
   exactly as the table shows them. Never reuse one year's figures for another year.
   Say "increased" only if the later figure is larger, "decreased" only if it is smaller.
   Do not say a company "added", "removed" or "introduced" something; instead state
   what each year's filing says.
4. If the passages say anything relevant, answer with what they DO say, even if
   it is only part of the answer. Put what the passages do not cover in "limitations".
5. Only if no passage is relevant at all, return an empty "sentences" list.
6. Never predict, give investment advice, or claim causes the filings do not state.
   If the question asks you to prove or infer something the filings do not state,
   report only what they say and explain the gap in "limitations".
7. In comparisons, say when a company or year has no relevant passage.
8. At most 8 sentences. Plain, factual language."""

# Ollama forces the reply into this shape, so the code can check every sentence.
# There is no "status" field: small models tend to decide it before reading the
# passages. The code decides answered / not found after checking the sentences.
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["text", "citations"],
            },
        },
        "limitations": {"type": "string"},
    },
    "required": ["sentences", "limitations"],
}


def select_passages(passages, n_groups):
    """Pick passages fairly: round-robin across company-year groups, best first."""
    groups = OrderedDict()
    for p in passages:
        groups.setdefault((p.ticker, p.fiscal_year), []).append(p)
    if n_groups <= 1:
        limit = SINGLE_GROUP_PASSAGES
    else:
        limit = max(len(groups), min(12, 2 * len(groups)))
    picked, depth = [], 0
    while len(picked) < limit and any(depth < len(g) for g in groups.values()):
        for g in groups.values():
            if depth < len(g) and len(picked) < limit:
                picked.append(g[depth])
        depth += 1
    return picked


def passage_chars(n):
    return max(MIN_PASSAGE_CHARS, min(MAX_PASSAGE_CHARS, CONTEXT_CHARS // max(n, 1)))


def topic_words(search_text):
    """Lower-case word stems (first 5 letters) used to find the relevant part of a passage."""
    return {w[:5] for w in re.findall(r"[a-z][a-z0-9&]+", search_text.lower()) if len(w) > 3}


def trim_passage(text, words, max_chars):
    """Keep the run of lines around the line that best matches the topic."""
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    def score(line):
        return sum(1 for w in re.findall(r"[a-z][a-z0-9&]+", line.lower()) if w[:5] in words)
    best = max(range(len(lines)), key=lambda i: score(lines[i]))
    lo = hi = best
    size = len(lines[best])
    while True:   # grow the window one line at a time, alternating sides
        grew = False
        for i in (hi + 1, lo - 1):
            if 0 <= i < len(lines) and size + len(lines[i]) + 1 <= max_chars:
                size += len(lines[i]) + 1
                lo, hi = min(lo, i), max(hi, i)
                grew = True
        if not grew:
            break
    kept = "\n".join(lines[lo:hi + 1])[:max_chars]
    # If the window starts inside a table, keep the table's first line (its column
    # headers, usually the years). Without it the model can't tell which column is
    # which year, and mislabels figures.
    top = lo
    while top > 0 and " | " in lines[top - 1]:
        top -= 1
    header = lines[top] + "\n…" if top < lo and " | " in lines[lo] else ""
    return ("…" if top > 0 or (lo > 0 and not header) else "") + header + kept + \
        ("…" if hi < len(lines) - 1 else "")


def passage_header(p):
    page = f"page {p.printed_page}" if p.printed_page else f"HTML page {p.page}"
    return f"{p.company} 10-K FY{p.fiscal_year} | {p.section_name} | {page}"


def build_prompt(question, passages, search_text, missing=()):
    """Return (user_message, shown) where shown[n] is the exact text passage n showed."""
    words = topic_words(search_text)
    limit = passage_chars(len(passages))
    shown, blocks = {}, []
    for n, p in enumerate(passages, start=1):
        shown[n] = f"{passage_header(p)}\n{trim_passage(p.text, words, limit)}"
        blocks.append(f"[{n}] {shown[n]}")
    note = ""
    if missing:
        names = ", ".join(f"{t or 'any company'} FY{y or 'any year'}" for t, y in missing)
        note = f"\nNot in the filings collection: {names}. Say so if relevant.\n"
    user = f"Question: {question}\n{note}\nPassages:\n\n" + "\n\n".join(blocks)
    return user, shown
