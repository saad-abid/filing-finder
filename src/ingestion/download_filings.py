"""Download 10-K filings from SEC EDGAR for the sample corpus."""
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
USER_AGENT = (os.getenv("SEC_USER_AGENT") or "").strip()
if not USER_AGENT:
    raise SystemExit("Set SEC_USER_AGENT in your .env file first.")
HEADERS = {"User-Agent": USER_AGENT}

COMPANIES = {
    "AAPL": {"name": "Apple", "cik": 320193},
    "AMZN": {"name": "Amazon", "cik": 1018724},
    "GOOGL": {"name": "Alphabet", "cik": 1652044},
    "MSFT": {"name": "Microsoft", "cik": 789019},
    "NVDA": {"name": "NVIDIA", "cik": 1045810},
}
FIRST_YEAR, LAST_YEAR = 2021, 2025   # fiscal period end year
RAW_DIR = ROOT / "data/raw"


def get(url):
    """GET with SEC-friendly pacing (limit is 10 requests/second)."""
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    time.sleep(0.2)
    return resp


def list_filings(cik):
    """Yield every filing for a company, including older history files."""
    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    blocks = [sub["filings"]["recent"]]
    for extra in sub["filings"].get("files", []):
        blocks.append(get(f"https://data.sec.gov/submissions/{extra['name']}").json())
    keys = ("accessionNumber", "form", "filingDate", "reportDate", "primaryDocument")
    for block in blocks:
        for i in range(len(block["accessionNumber"])):
            yield {k: block[k][i] for k in keys}


def main():
    manifest = []
    for ticker, info in COMPANIES.items():
        out_dir = RAW_DIR / ticker
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{info['name']} ({ticker})")

        for f in list_filings(info["cik"]):
            if f["form"] != "10-K" or not f["reportDate"]:
                continue
            year = int(f["reportDate"][:4])
            if not FIRST_YEAR <= year <= LAST_YEAR:
                continue

            acc = f["accessionNumber"].replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{info['cik']}/{acc}/{f['primaryDocument']}")
            path = out_dir / f"{ticker}_10K_{f['reportDate']}.htm"

            if path.exists():
                print(f"  skip   {path.name}")
            else:
                path.write_bytes(get(url).content)
                print(f"  saved  {path.name}")

            manifest.append({
                "ticker": ticker, "company": info["name"], "form": "10-K",
                "report_date": f["reportDate"], "filing_date": f["filingDate"],
                "accession": f["accessionNumber"], "source_url": url,
                "local_path": str(path.relative_to(ROOT)),
            })

    manifest.sort(key=lambda m: (m["ticker"], m["report_date"]))
    (RAW_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nDone. {len(manifest)} filings. Manifest: data/raw/manifest.json")


if __name__ == "__main__":
    main()