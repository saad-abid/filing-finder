from src.answer.guard import check, numbers_in, refusal_reason

SHOWN = {
    1: "Apple 10-K FY2024 | MD&A | page 23\niPhone | $201,183 | —% | $200,583\nServices | 96,169 | 13%",
    2: "Apple 10-K FY2024 | Risk Factors | page 8\nThe Company relies on single-source outsourcing partners.",
}


def reply(*sentences, limitations=""):
    return {"limitations": limitations,
            "sentences": [{"text": t, "citations": c} for t, c in sentences]}


def test_refuses_advice_and_predictions():
    assert refusal_reason("Should I buy NVIDIA stock?")
    assert refusal_reason("Will Apple's stock price go up next year?")
    assert refusal_reason("Is Microsoft undervalued?")
    assert refusal_reason("What is your price target for Amazon?")
    assert refusal_reason("How did NVIDIA describe export controls?") is None
    assert refusal_reason("What does Apple say about its stock repurchase program?") is None


def test_numbers_in_normalises_formats():
    assert numbers_in("iPhone sales were $201,183 million, up 13%.") == {"201183", "13"}
    assert numbers_in("FY2024 and $1.5 billion") == {"2024", "1.5"}
    assert numbers_in("Note 1 and two items") == set()      # single digits ignored


def test_keeps_sentences_backed_by_cited_passages():
    out = check(reply(("iPhone net sales were $201,183 million in 2024.", [1]),
                      ("Apple relies on single-source outsourcing partners.", [2])), SHOWN)
    assert out.status == "answered"
    assert [c for _, c in out.sentences] == [[1], [2]]
    assert out.dropped == []


def test_drops_sentence_with_number_not_in_cited_passage():
    out = check(reply(("iPhone net sales were $210 billion in 2024.", [1]),
                      ("Services grew 13%.", [1])), SHOWN)
    assert [t for t, _ in out.sentences] == ["Services grew 13%."]
    assert "210" in out.dropped[0][1]


def test_number_must_be_in_the_passage_it_cites_not_another_one():
    out = check(reply(("Services grew 13%.", [2])), SHOWN)   # 13% is in [1], not [2]
    assert out.status == "not_found"


def test_drops_uncited_and_invented_citations():
    out = check(reply(("Apple makes phones.", []), ("Apple sells Macs.", [7])), SHOWN)
    assert out.status == "not_found"
    assert [why for _, why in out.dropped] == ["no valid citation", "no valid citation"]


def test_keeps_valid_citations_and_ignores_invalid_ones_in_same_sentence():
    out = check(reply(("Apple relies on outsourcing partners.", [2, 9])), SHOWN)
    assert out.sentences == [("Apple relies on outsourcing partners.", [2])]


def test_strips_citation_marks_written_inside_the_text():
    out = check(reply(("Apple relies on outsourcing partners [2].", [2])), SHOWN)
    assert out.sentences[0][0] == "Apple relies on outsourcing partners."


def test_empty_answer_is_not_found():
    out = check(reply(limitations="Nothing relevant in the passages."), SHOWN)
    assert out.status == "not_found" and out.sentences == []


def test_limitations_kept_unless_they_contain_figures():
    ok = check(reply(("Services grew 13%.", [1]),
                     limitations="The filings for 2024 do not attribute margin changes to AI."), SHOWN)
    assert ok.limitations.startswith("The filings")
    bad = check(reply(("Services grew 13%.", [1]), limitations="AI added $5 billion of profit."), SHOWN)
    assert bad.limitations == "" and bad.dropped


def test_single_digit_figures_count_but_bare_digits_do_not():
    assert numbers_in("$5 billion and 9% growth") == {"5", "9"}
    assert numbers_in("See Note 7 and Item 8") == set()


def test_form_names_are_not_figures():
    assert numbers_in("The Form 10-K and 10-Q filings for 2024") == {"2024"}
    out = check(reply(limitations="The 10-K passages do not cover earnings calls."), SHOWN)
    assert out.limitations and not out.dropped
