"""Run the answer test set and report whether each answer behaves as expected.

Run from the project folder:  python -m src.answer.evaluate
Optional: --only 1,11,14   (case numbers) to run a subset; full run is slow on CPU.

"expect" in eval/answer_cases.json is one of: answered,
answered_with_limitations, not_found, refused.
"""
import argparse
import json
import sys
from pathlib import Path

from src.answer.answer import answer, format_answer

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "eval/answer_cases.json"


def outcome(a):
    if a.status == "answered" and a.limitations:
        return "answered_with_limitations"
    return a.status


def matches(expect, got):
    if expect == "answered":
        return got in ("answered", "answered_with_limitations")
    return expect == got


def to_record(number, case, a, got):
    """A JSON-friendly copy of one answer, for src.evaluation.scorecard."""
    def source(n):
        p, shown = a.sources[n - 1]
        return {"ticker": p.ticker, "fiscal_year": p.fiscal_year, "section": p.section_name,
                "printed_page": p.printed_page, "chunk_id": p.chunk_id,
                "shown": shown}   # exact text the model saw, so the guard can be re-run later
    return {
        "number": number, "question": case["question"], "expect": case["expect"], "got": got,
        "sentences": [{"text": t, "sources": [source(c) for c in cites]} for t, cites in a.sentences],
        "limitations": a.limitations,
        "dropped": [{"text": t, "reason": why} for t, why in a.dropped],
        "model": a.model, "seconds_model": round(a.seconds_model), "prompt_tokens": a.prompt_tokens,
    }


def main():
    ap = argparse.ArgumentParser(description="Answer test set report.")
    ap.add_argument("--only", help="comma-separated case numbers, e.g. 1,11,14")
    ap.add_argument("--verbose", action="store_true", help="print each full answer")
    ap.add_argument("--save", help="write all answers to this JSON file (for the scorecard)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    chosen = {int(x) for x in args.only.split(",")} if args.only else set(range(1, len(cases) + 1))
    passed = total = kept = dropped = 0
    records = []
    for i, case in enumerate(cases, start=1):
        if i not in chosen:
            continue
        a = answer(case["question"])
        got = outcome(a)
        ok = matches(case["expect"], got)
        records.append(to_record(i, case, a, got))
        if args.save:   # rewrite after every answer, so a long run can be stopped safely
            Path(args.save).parent.mkdir(parents=True, exist_ok=True)
            Path(args.save).write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
        total += 1
        passed += ok
        kept += len(a.sentences)
        dropped += len(a.dropped)
        print(f"{'PASS' if ok else 'FAIL'}  #{i:<2} expected {case['expect']:<26} got {got:<26} "
              f"{len(a.sentences)} kept, {len(a.dropped)} removed, model {a.seconds_model:.0f}s, "
              f"{a.prompt_tokens} tokens", flush=True)
        if args.verbose:
            print("    " + format_answer(a).replace("\n", "\n    ") + "\n", flush=True)

    print(f"\nBehaved as expected: {passed}/{total}.  Sentences kept: {kept}, "
          f"removed by safety check: {dropped}")


if __name__ == "__main__":
    main()
