# FilingFinder: Project Brief

## 1. Overview

FilingFinder is an internal research assistant for an independent investment research firm
that sells equity research to institutional clients (hedge funds, mutual funds and pension
funds). The firm has about 40 analysts. Analysts ask plain-English questions about SEC filings
and get answers that cite the exact filing and page, with the original passage shown so they
can verify it.

## 2. The problem

Each analyst covers about 15 US public companies, and spends roughly half of every week on
**source-document intake**: opening 10-Ks, finding the relevant sections (risk factors, MD&A,
segments), copy-pasting passages and comparing year over year. Only after that can they write
original analysis.

This intake work is boring, necessary, repeated across analysts, and the biggest drag on output.
Hiring more analysts doesn't fix it, because the workload grows with coverage.

## 3. What FilingFinder does

An analyst can:

1. Ask questions in plain English about any filing in the corpus.
2. Get an answer that cites the specific filing and page.
3. Click a citation to see the underlying passage.
4. Use it from a simple chat page in the browser.

## 4. Trust rules (the most important section)

The firm's business depends on being right, so the bot must:

- **Never invent facts.** If the answer isn't in the filings, say so.
- **Always cite.** Every claim points to a filing and page.
- **Show the passage** so the analyst can verify in one click.
- **Refuse to go beyond the filings**, even when asked to infer or speculate.

A wrong but confident answer is worse than no answer.

## 5. Sample corpus

10-K filings for **Apple, Amazon, Alphabet, Microsoft and NVIDIA**, fiscal years 2021 to 2025
(25 filings), downloaded from SEC EDGAR (public domain). The design should scale later to
10-Qs and other S&P 500 companies.

## 6. Example questions it must handle

1. How did Apple's revenue mix (iPhone, Services, Mac, iPad, Wearables) change from 2021 to 2025?
2. Compare Amazon's AWS operating income and margin with North America and International, 2021-2025.
3. How did NVIDIA describe Data Center demand, customer concentration and supply constraints over time?
4. How did Microsoft's description of Azure, AI infrastructure and capacity constraints change?
5. How did Alphabet's revenue trends differ across Search, YouTube ads, Network, subscriptions/devices and Cloud?
6. Which companies added or changed risk-factor language on AI, export controls, supply chain or regulation?
7. How did Apple and NVIDIA describe supplier concentration, and did the wording become more urgent?
8. Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon and NVIDIA.
9. What are each company's main geographic revenue exposures in the latest 10-K, and what changed year over year?
10. Do the filings prove generative AI improved margins? The bot should present the evidence that exists and **refuse to infer beyond it**.

## 7. How it works (RAG)

1. **Ingest:** download 10-Ks from EDGAR.
2. **Parse and chunk:** split each filing into small passages tagged with company, year, section and page.
3. **Index:** store embeddings plus keyword search data in Postgres with pgvector.
4. **Retrieve:** hybrid search (meaning plus keywords), filtered by company, year and section. Questions that span several companies or years pull passages from each.
5. **Generate:** Ollama (local)  answers only from the retrieved passages, with citations, or says "not found".

## 8. Build phases

| Phase | What | Status |
|---|---|---|
| 1 | Download filings from EDGAR | Done |
| 2 | Parse into page-aware, section-tagged chunks | Done |
| 3 | Embeddings, Postgres + pgvector, hybrid retrieval | Done |
| 4 | Cited answer generation with a "not found" path | In progress |
| 5 | Evaluation: citation accuracy and correct refusals | Planned |
| 6 | User interface: simple chat web app (ask a question, see the cited answer, click to view the passage) | Planned |
| 7 | Simple deployment and README | Planned |

## 9. Constraints

- About 40 analysts plus a few partners
- Keep it simple: a basic chat web app, no user accounts or login, no saved conversation history
- Deployment must be simple to set up and run, with no infrastructure team to maintain it
- Free local development (Docker); paid services only with approval

## 10. Out of scope

- Trading recommendations or stock picks
- External data (news, social media, alternative data)
- Any analysis not grounded in the filings
- Multi-client or multi-tenant use
- Billing, plans, paywalls
- Mobile app

## 11. Definition of done

A pilot group of five senior analysts uses it for a week and reports saving **at least 3 hours
per analyst per week**. For this project, that translates to: the 10 example questions return
correct, cited answers; unanswerable questions are refused; and every citation matches the
real filing page.