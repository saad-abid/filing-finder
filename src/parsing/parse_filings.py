"""Parse downloaded 10-K HTML into page-aware, section-tagged chunks."""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/raw/manifest.json"
OUT = ROOT / "data/processed/chunks.jsonl"

SENTINEL = "[[[PAGEBREAK]]]"
MAX_CHARS = 3000
ITEM_RE = re.compile(r"^item\s+(\d{1,2}[abc]?)\s*[\.\:\-–—]*\s*(.*)$", re.I)
BLOCK_TAGS = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"]


def table_to_text(table):
    """Turn an HTML table into 'cell | cell | cell' rows."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        merged = []
        for c in filter(None, cells):
            if merged and merged[-1] == "$":
                merged[-1] = "$" + c
            elif merged and c in {")", "%", ")%"}:
                merged[-1] += c
            else:
                merged.append(c)
        if merged:
            rows.append(" | ".join(merged))
    return "\n".join(rows)


def html_to_pages(html):
    """Return a list of pages; each page is a list of non-empty text lines."""
    soup = BeautifulSoup(html, "lxml")

    # remove hidden XBRL header / hidden elements
    for tag in soup.find_all("ix:header"):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        if not getattr(tag, "decomposed", False):
            tag.decompose()

    # mark page breaks
    for tag in soup.find_all(style=re.compile(r"page-break", re.I)):
        if getattr(tag, "decomposed", False):
            continue
        style = tag.get("style", "")
        if re.search(r"page-break-before\s*:\s*always", style, re.I):
            tag.insert_before(NavigableString(f"\n{SENTINEL}\n"))
        if re.search(r"page-break-after\s*:\s*always", style, re.I):
            tag.insert_after(NavigableString(f"\n{SENTINEL}\n"))

    # tables -> text rows
    for table in soup.find_all("table"):
        table.replace_with(NavigableString("\n" + table_to_text(table) + "\n"))

    # keep line structure
    for br in soup.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for tag in soup.find_all(BLOCK_TAGS):
        tag.append(NavigableString("\n"))

    text = soup.get_text().replace("\xa0", " ")
    pages = []
    for raw in text.split(SENTINEL):
        lines = [re.sub(r"[ \t]+", " ", l).strip() for l in raw.split("\n")]
        lines = [l for l in lines if l]
        if lines:
            pages.append(lines)
    return pages


def printed_page_number(lines):
    """Try to read the page number printed at the bottom of the page."""
    for line in reversed(lines[-3:]):
        m = re.search(r"(?:^|\|\s*)(\d{1,3})$", line)
        if m:
            return m.group(1)
    return None


def parse_filing(meta):
    html = (ROOT / meta["local_path"]).read_text(encoding="utf-8", errors="ignore")
    pages = html_to_pages(html)
    chunks, section = [], "Front matter"

    for page_no, lines in enumerate(pages, start=1):
        printed = printed_page_number(lines)
        hits = sum(1 for l in lines if len(l) < 150 and ITEM_RE.match(l))
        is_toc = hits >= 6          # table-of-contents page
        buf, size, n = [], 0, 0
        buf_section = "Table of Contents" if is_toc else section

        def flush():
            nonlocal buf, size, n
            text = "\n".join(buf).strip()
            if len(text) >= 40:
                n += 1
                chunks.append({
                    "chunk_id": f"{meta['ticker']}_{meta['report_date']}_p{page_no:03d}_{n}",
                    "ticker": meta["ticker"],
                    "company": meta["company"],
                    "form": meta["form"],
                    "report_date": meta["report_date"],
                    "accession": meta["accession"],
                    "source_url": meta["source_url"],
                    "section": buf_section,
                    "page": page_no,
                    "printed_page": printed,
                    "text": text,
                })
            buf, size = [], 0

        for line in lines:
            m = ITEM_RE.match(line) if (not is_toc and len(line) < 150) else None
            if m:
                flush()
                section = f"Item {m.group(1).upper()}. {m.group(2).strip()}".strip()
                buf_section = section
            elif size + len(line) > MAX_CHARS:
                flush()
            buf.append(line)
            size += len(line) + 1
        flush()

    return pages, chunks


def main():
    manifest = json.loads(MANIFEST.read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with OUT.open("w", encoding="utf-8") as f:
        for meta in manifest:
            pages, chunks = parse_filing(meta)
            sections = {c["section"].split(".")[0] for c in chunks}
            flag = "  <-- CHECK: few pages found" if len(pages) < 20 else ""
            print(f"{meta['ticker']} {meta['report_date']}: "
                  f"{len(pages)} pages, {len(chunks)} chunks, "
                  f"{len(sections)} sections{flag}")
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
            total += len(chunks)
    print(f"\nDone. {total} chunks written to {OUT}")


if __name__ == "__main__":
    main()