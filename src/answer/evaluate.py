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


def main():
    ap = argparse.ArgumentParser(description="Answer test set report.")
    ap.add_argument("--only", help="comma-separated case numbers, e.g. 1,11,14")
    ap.add_argument("--verbose", action="store_true", help="print each full answer")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    chosen = {int(x) for x in args.only.split(",")} if args.only else set(range(1, len(cases) + 1))
    passed = total = kept = dropped = 0
    for i, case in enumerate(cases, start=1):
        if i not in chosen:
            continue
        a = answer(case["question"])
        got = outcome(a)
        ok = matches(case["expect"], got)
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
