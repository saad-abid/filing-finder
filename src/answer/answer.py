"""Answer a question from the filings, with a citation on every sentence.

Run from the project folder:
    python -m src.answer.answer "How did Apple describe supplier concentration in 2024?"
    python -m src.answer.answer "..." --show-passages

Steps: refuse advice questions -> retrieve passages -> local model writes a
JSON answer -> guard.check() removes anything not backed by a cited passage.
"""
import argparse
import sys
import time
from dataclasses import dataclass, field

from src.answer import guard, prompts
from src.answer.llm import chat_json

NOT_FOUND_MESSAGE = "Not found in the filings. The retrieved passages don't answer this question."


@dataclass
class Answer:
    question: str
    status: str                                    # answered | not_found | refused
    sentences: list = field(default_factory=list)  # [(text, [source numbers])]
    sources: list = field(default_factory=list)    # [(Passage, text shown to model)], numbered from 1
    limitations: str = ""
    message: str = ""                              # for refused / not_found
    missing: list = field(default_factory=list)    # company-years not in the corpus
    dropped: list = field(default_factory=list)    # [(sentence, reason)] removed by the guard
    model: str = ""
    seconds_search: float = 0.0
    seconds_model: float = 0.0
    prompt_tokens: int = 0


def answer(question, retriever=None, llm=chat_json):
    """retriever/llm can be swapped (tests use fakes)."""
    reason = guard.refusal_reason(question)
    if reason:
        return Answer(question, "refused", message=reason)

    if retriever is None:
        from src.retrieval.retrieve import retrieve as retriever   # loads the embedding model
    start = time.time()
    found = retriever(question)
    searched = time.time() - start

    passages = prompts.select_passages(found.passages, len(found.groups))
    if not passages:
        return Answer(question, "not_found", message=NOT_FOUND_MESSAGE,
                      missing=found.missing, seconds_search=searched)

    user, shown = prompts.build_prompt(question, passages, found.search_text, found.missing)
    reply = llm(prompts.SYSTEM_PROMPT, user, prompts.ANSWER_SCHEMA)
    checked = guard.check(reply.content, shown)

    result = Answer(question, checked.status, limitations=checked.limitations,
                    missing=found.missing, dropped=checked.dropped, model=reply.model,
                    seconds_search=searched, seconds_model=reply.seconds,
                    prompt_tokens=reply.prompt_tokens)
    if checked.status != "answered":
        result.message = NOT_FOUND_MESSAGE
        return result

    # Renumber so the analyst sees sources 1, 2, 3... in the order first cited.
    renumber = {}
    for _, cites in checked.sentences:
        for c in cites:
            renumber.setdefault(c, len(renumber) + 1)
    result.sentences = [(text, [renumber[c] for c in cites]) for text, cites in checked.sentences]
    result.sources = [(passages[old - 1], shown[old]) for old in renumber]
    return result


def format_answer(a, show_passages=False):
    lines = []
    if a.status == "answered":
        for text, cites in a.sentences:
            lines.append(f"{text} {''.join(f'[{c}]' for c in cites)}")
        if a.limitations:
            lines.append(f"\nLimits of the evidence: {a.limitations}")
    else:
        lines.append(a.message)
        if a.limitations:
            lines.append(f"Details: {a.limitations}")
    if a.missing:
        lines.append("\nNot in the filings collection: "
                     + ", ".join(f"{t or 'any'} FY{y or 'any'}" for t, y in a.missing))
    if a.sources:
        lines.append("\nSources:")
        for n, (p, shown_text) in enumerate(a.sources, start=1):
            lines.append(f"  [{n}] {p.citation()}  {p.source_url}")
            if show_passages:
                body = shown_text.split("\n", 1)[1] if "\n" in shown_text else shown_text
                lines.append("      " + body.replace("\n", "\n      ") + "\n")
    if a.dropped:
        lines.append(f"\n({len(a.dropped)} sentence(s) removed by the safety check:)")
        for text, why in a.dropped:
            lines.append(f"  - {why}: {text[:120]}")
    if a.model:
        lines.append(f"\n[{a.model} | search {a.seconds_search:.1f}s | model {a.seconds_model:.0f}s "
                     f"| read {a.prompt_tokens} tokens]")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Answer a question from the 10-K filings.")
    ap.add_argument("question")
    ap.add_argument("--show-passages", action="store_true", help="print each cited passage")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_answer(answer(args.question), args.show_passages))


if __name__ == "__main__":
    main()
