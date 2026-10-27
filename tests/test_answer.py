from src.answer import prompts
from src.answer.answer import answer, format_answer
from src.answer.llm import LLMReply
from src.retrieval.retrieve import Passage, RetrievalResult
from src.retrieval.query_parser import QueryFilters


def passage(cid, ticker="AAPL", year=2024, text="The Company relies on outsourcing partners.", page=8):
    return Passage(cid, ticker, "Apple", year, None, "acc", "https://sec.gov/x", "Risk Factors",
                   "1A", page + 2, page, text)


def fake_retriever(passages, groups=((None, None),), missing=()):
    return lambda q: RetrievalResult(QueryFilters(), list(groups), passages, list(missing),
                                     "outsourcing partners")


def fake_llm(content):
    calls = []
    def llm(system, user, schema):
        calls.append(user)
        return LLMReply(content, "fake-model", 100, 20, 1.0)
    llm.calls = calls
    return llm


def test_select_passages_is_fair_across_groups():
    ps = [passage(f"a{i}", "AAPL") for i in range(5)] + [passage(f"n{i}", "NVDA") for i in range(5)]
    picked = prompts.select_passages(ps, n_groups=2)
    assert len(picked) == 4
    assert [p.ticker for p in picked] == ["AAPL", "NVDA", "AAPL", "NVDA"]


def test_select_passages_gives_every_group_one_when_many_groups():
    ps = [passage(f"{t}{y}", t, y) for t in ["AAPL", "NVDA", "MSFT"] for y in range(2021, 2026)]
    picked = prompts.select_passages(ps, n_groups=15)
    assert len({(p.ticker, p.fiscal_year) for p in picked}) == 15


def test_trim_passage_keeps_the_relevant_part():
    text = "\n".join([f"Unrelated line {i} about weather." for i in range(50)]
                     + ["The Company relies on single-source outsourcing partners."]
                     + [f"More unrelated text {i}." for i in range(50)])
    out = prompts.trim_passage(text, prompts.topic_words("outsourcing partners"), 300)
    assert "single-source outsourcing partners" in out
    assert len(out) <= 302 and out.startswith("…") and out.endswith("…")


def test_answer_cites_and_renumbers_sources():
    ps = [passage("p1", text="Unrelated."), passage("p2", page=9)]
    llm = fake_llm({"limitations": "",
                    "sentences": [{"text": "Apple relies on outsourcing partners.", "citations": [2]}]})
    a = answer("Does Apple rely on outsourcing partners?", fake_retriever(ps), llm)
    assert a.status == "answered"
    assert a.sentences == [("Apple relies on outsourcing partners.", [1])]   # [2] renumbered to [1]
    assert a.sources[0][0].chunk_id == "p2"
    assert "[1] Apple 10-K FY2024, Risk Factors, p. 9" in format_answer(a)


def test_answer_becomes_not_found_when_every_sentence_fails_the_check():
    llm = fake_llm({"limitations": "",
                    "sentences": [{"text": "Apple earned $999 billion.", "citations": [1]}]})
    a = answer("How much did Apple earn?", fake_retriever([passage("p1")]), llm)
    assert a.status == "not_found" and a.dropped


def test_advice_question_is_refused_without_searching_or_calling_the_model():
    def boom(*args):
        raise AssertionError("should not be called")
    a = answer("Should I buy Apple stock?", boom, boom)
    assert a.status == "refused"


def test_missing_years_are_passed_to_the_model_and_reported():
    llm = fake_llm({"limitations": "", "sentences": []})
    a = answer("NVIDIA risks in 2026", fake_retriever([passage("p1")], missing=[("NVDA", 2026)]), llm)
    assert "NVDA FY2026" in llm.calls[0]
    assert a.missing == [("NVDA", 2026)] and "NVDA FY2026" in format_answer(a)


def test_trim_keeps_the_table_header_with_the_years():
    rows = [f"Row {i} | {1000 + i} | {2000 + i} | {3000 + i}" for i in range(60)]
    text = "\n".join(["Revenue by region:", "2023 | 2024 | 2025"] + rows
                     + ["EMEA (1) | 91,038 | 102,127 | 117,152"] + rows)
    out = prompts.trim_passage(text, prompts.topic_words("EMEA"), 400)
    assert "2023 | 2024 | 2025" in out and "EMEA (1) | 91,038" in out
