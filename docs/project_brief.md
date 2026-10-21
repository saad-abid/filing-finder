# FilingFinder: Project Brief

## 1. What it is

FilingFinder is a personal learning project: a small assistant that answers plain-English
questions about company annual reports (SEC 10-K filings). Every answer cites the exact filing
and page, and shows the original passage so it can be checked.

I built it to learn how retrieval-augmented generation (RAG) works end to end: getting real
documents, splitting them into searchable pieces, combining meaning and keyword search, and
having a local AI model answer only from what it found.

## 2. Why

10-K filings are long (60 to 110 pages each), and comparing what companies say across several
years means a lot of searching and copy-pasting. A tool that finds the right passages and
summarises them with sources makes that much faster, and it's a realistic problem for practising
RAG.

## 3. Ground rules

The most important part of the project: answers must be trustworthy.

- **Never invent facts.** If the answer isn't in the filings, say "not found".
- **Always cite.** Every sentence points to a filing and page.
- **Show the passage** so the answer can be verified.
- **Don't go beyond the filings.** No speculation, predictions or investment advice.

A wrong but confident answer is worse than no answer.

## 4. Data

10-K filings for **Apple, Amazon, Alphabet, Microsoft and NVIDIA**, fiscal years 2021 to 2025
(25 filings), downloaded free from SEC EDGAR (public domain).

## 5. Example questions

1. How did Apple's revenue mix (iPhone, Services, Mac, iPad, Wearables) change from 2021 to 2025?
2. Compare Amazon's AWS operating income with North America and International, 2021-2025.
3. How did NVIDIA describe Data Center demand, customer concentration and supply constraints over time?
4. How did Microsoft's description of Azure, AI infrastructure and capacity constraints change?
5. How did Alphabet's revenue trends differ across Search, YouTube ads, Network, subscriptions/devices and Cloud?
6. Which companies changed risk-factor language on AI, export controls, supply chain or regulation?
7. How did Apple and NVIDIA describe supplier concentration over time?
8. Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon and NVIDIA.
9. What are each company's main geographic revenue exposures in the latest 10-K?
10. Do the filings prove generative AI improved margins? (It should show the evidence and **refuse to infer beyond it**.)

## 6. How it works

1. **Download:** fetch the 10-Ks from SEC EDGAR.
2. **Split:** cut each filing into small passages labelled with company, year, section and page.
3. **Index:** store the passages in Postgres with pgvector, with embeddings for meaning search
   and a keyword index.
4. **Search:** hybrid search (meaning plus keywords), filtered by company, year and section.
   Comparison questions search each company and year separately.
5. **Answer:** a local model in Ollama writes the answer only from the retrieved passages, with
   a citation on every sentence. A safety check removes any sentence that can't be traced back
   to its source.

## 7. Build phases

| Phase | What | Status |
|---|---|---|
| 1 | Download filings from EDGAR | Done |
| 2 | Split into page-aware, section-tagged passages | Done |
| 3 | Embeddings, Postgres + pgvector, hybrid search | Done |
| 4 | Cited answers with a local model and a safety check | In progress |
| 5 | Evaluation: are the answers and citations correct? | Planned |
| 6 | User interface: simple chat web app (React) | Planned |
| 7 | Simple deployment and README | Planned |

## 8. Keep it simple

- Free and local: Docker for the database, Ollama for the AI model, no paid services.
- A basic chat page: ask a question, read the cited answer, click to see the passage.
- No user accounts, login or saved history.
- Easy to set up and run.

## 9. Done when

- The 10 example questions get correct, cited answers.
- Questions the filings can't answer get "not found", and advice questions are refused.
- Every citation points to the right filing and page.
