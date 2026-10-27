"""Measure search accuracy on questions with a known correct passage.

Run from the project folder:  python -m src.retrieval.evaluate

Each case in eval/retrieval_cases.json names the company, year and a phrase
that only the correct passage(s) contain. A case passes if a passage with that
phrase is among the top K results for that company-year.
"""
import argparse
import json
import sys
from pathlib import Path

from src.db import connect
from src.retrieval.retrieve import retrieve

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "eval/retrieval_cases.json"


def rank_of_answer(result, case):
    """1-based rank of the first correct passage within its company-year, or None."""
    group = [p for p in result.passages
             if p.ticker == case["ticker"] and p.fiscal_year == case["year"]]
    phrase = case["must_contain"].lower()
    for rank, p in enumerate(group, start=1):
        if phrase in p.text.lower():
            return rank
    return None


def main():
    ap = argparse.ArgumentParser(description="Search accuracy report.")
    ap.add_argument("-k", type=int, default=5, help="count as a hit if within top K (default 5)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    hits_1 = hits_k = 0
    with connect() as conn:
        for case in cases:
            rank = rank_of_answer(retrieve(case["question"], conn=conn), case)
            hits_1 += rank == 1
            hits_k += rank is not None and rank <= args.k
            mark = "PASS" if rank and rank <= args.k else "FAIL"
            print(f"{mark}  rank {rank or '-':>2}  {case['ticker']} FY{case['year']}  {case['question']}")

    n = len(cases)
    print(f"\nTop 1: {hits_1}/{n} ({hits_1 / n:.0%})    Top {args.k}: {hits_k}/{n} ({hits_k / n:.0%})")


if __name__ == "__main__":
    main()
