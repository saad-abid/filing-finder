"""Grade the figures in saved answers against known-correct values from the filings.

Run from the project folder:
    python -m src.answer.evaluate --save eval/results/latest.json     (slow: runs the model)
    python -m src.evaluation.scorecard eval/results/latest.json       (instant)

Each number in a kept answer sentence is graded as:
  correct      - a known figure, and the sentence names its label and year
  wrong_label  - a real figure from the filings, but attached to the wrong label or year
  unverified   - not in eval/facts.json, so it can't be graded automatically

Facts are compared by value, so a figure counts as correct for whichever
company/label/year it really belongs to. The label check is "the sentence
mentions one of the label's keywords"; the year check is "the sentence
mentions that year". Both are deliberately simple, so a long list sentence
with many years can still hide a swap between two of its own years.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from src.answer.guard import YEAR_RE, YEARS_IN_TEXT_RE, numbers_in

ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "eval/facts.json"


def load_facts(path=FACTS):
    """{(ticker, digits): [(label, keywords, year)]} for quick lookup by value."""
    index = {}
    for f in json.loads(Path(path).read_text(encoding="utf-8")):
        for year, value in f["values"].items():
            digits = value.replace(",", "")
            index.setdefault((f["ticker"], digits), []).append((f["label"], f["keywords"], int(year)))
    return index


def grade_sentence(text, tickers, facts):
    """[(number, verdict, explanation)] for every figure in one sentence."""
    lower = text.lower()
    years = {int(y) for y in YEARS_IN_TEXT_RE.findall(text)}
    graded = []
    for num in sorted(numbers_in(text)):
        if YEAR_RE.fullmatch(num):
            continue
        known = [k for t in tickers for k in facts.get((t, num), [])]
        if not known:
            graded.append((num, "unverified", ""))
        elif any(y in years and any(w in lower for w in kw) for _, kw, y in known):
            graded.append((num, "correct", ""))
        else:
            actual = "; ".join(f"{label} FY{y}" for label, _, y in known)
            graded.append((num, "wrong_label", f"{num} is really {actual}"))
    return graded


def score(results, facts):
    totals, problems = Counter(), []
    for case in results:
        for s in case.get("sentences", []):
            tickers = sorted({src["ticker"] for src in s["sources"]})
            for num, verdict, why in grade_sentence(s["text"], tickers, facts):
                totals[verdict] += 1
                if verdict == "wrong_label":
                    problems.append((case["number"], s["text"], why))
    return totals, problems


def recheck(results):
    """Re-apply the current guard to saved answers without re-running the model.

    Uses the passage text the model saw if it was saved, otherwise the full
    passage from the database (older result files). Returns new results with
    only the sentences that still pass, plus what was removed.
    """
    from src.answer.guard import check
    db_text = {}
    missing = {s["chunk_id"] for c in results for sent in c.get("sentences", [])
               for s in sent["sources"] if "shown" not in s}
    if missing:
        from src.db import connect
        from src.retrieval.retrieve import PASSAGE_COLS, Passage
        from src.answer.prompts import passage_header
        with connect() as conn:
            for row in conn.execute(f"SELECT {PASSAGE_COLS} FROM chunks WHERE chunk_id = ANY(%s)",
                                    (list(missing),)):
                p = Passage(*row)
                db_text[p.chunk_id] = f"{passage_header(p)}\n{p.text}"

    out, removed = [], []
    for case in results:
        kept = []
        for sent in case.get("sentences", []):
            shown = {i: s.get("shown") or db_text[s["chunk_id"]]
                     for i, s in enumerate(sent["sources"], start=1)}
            reply = {"sentences": [{"text": sent["text"], "citations": list(shown)}], "limitations": ""}
            checked = check(reply, shown)
            if checked.sentences:
                kept.append(sent)
            else:
                removed += [(case["number"], text, why) for text, why in checked.dropped]
        out.append({**case, "sentences": kept})
    return out, removed


def main():
    ap = argparse.ArgumentParser(description="Grade figures in saved answers.")
    ap.add_argument("results", help="JSON file written by: python -m src.answer.evaluate --save ...")
    ap.add_argument("--recheck", action="store_true",
                    help="first re-apply the current safety check to the saved answers")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    if args.recheck:
        results, removed = recheck(results)
        print(f"Re-check with the current guard removed {len(removed)} more sentence(s):")
        for number, text, why in removed:
            print(f"  #{number}: {why}\n      \"{text[:160]}\"")
        print()
    totals, problems = score(results, load_facts())
    graded = totals["correct"] + totals["wrong_label"]
    print(f"Figures checked against the filings: {graded}")
    if graded:
        print(f"  correct:     {totals['correct']} ({totals['correct'] / graded:.0%})")
        print(f"  wrong label: {totals['wrong_label']} ({totals['wrong_label'] / graded:.0%})")
    print(f"Figures not in eval/facts.json (not graded): {totals['unverified']}")
    for number, text, why in problems:
        print(f"\n  #{number}: {why}\n      \"{text[:160]}\"")


if __name__ == "__main__":
    main()
