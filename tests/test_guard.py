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


# --- Phase 5 checks -------------------------------------------------------

APPLE_TABLE = ("Apple 10-K FY2025 | MD&A | page 23\n"
               "2025 | Change | 2024 | Change | 2023\n"
               "Mac | 33,708 | 12% | 29,984 | 2% | 29,357\n"
               "Services (1) | 109,158 | 14% | 96,169 | 13% | 85,200")
ALPHABET_TABLE = ("Alphabet 10-K FY2025 | Financial Statements | page 60\n"
                  "2023 | 2024 | 2025\n"
                  "Total revenues | $307,394 | $350,018 | $402,836\n"
                  "2023 | 2024 | 2025\n"
                  "EMEA (1) | 91,038 | 30 | 102,127 | 29 | 117,152 | 29")


def test_direction_word_must_match_the_numbers():
    shown = {1: "Apple 10-K FY2025 | MD&A | page 23\nMac | 35,190 | 33,708"}
    out = check(reply(("Mac revenue increased from $35,190 million to $33,708 million.", [1])), shown)
    assert out.status == "not_found" and "went from" in out.dropped[0][1]
    ok = check(reply(("Mac revenue decreased from $35,190 million to $33,708 million.", [1])), shown)
    assert ok.status == "answered"


def test_year_span_is_not_mistaken_for_figures():
    shown = {1: "Apple 10-K FY2021 | MD&A | page 21\n2021 | 2020\nWearables | 38,367 | 30,620",
             2: "Apple 10-K FY2025 | MD&A | page 23\n2025 | 2024\nWearables | 35,686 | 37,005"}
    out = check(reply(("From 2021 to 2025, Wearables revenue decreased from $38,367 million "
                       "to $35,686 million.", [1, 2])), shown)
    assert out.status == "answered"


def test_change_claims_need_two_years():
    one = {1: "Apple 10-K FY2023 | Risk Factors | page 6\nExport controls may affect the Company."}
    out = check(reply(("Apple added language on export controls.", [1])), one)
    assert "only one year" in out.dropped[0][1]
    two = {**one, 2: "Apple 10-K FY2021 | Risk Factors | page 9\nThe Company's operations are global."}
    assert check(reply(("Apple added language on export controls.", [1, 2])), two).status == "answered"


def test_figure_with_wrong_column_year_is_dropped():
    out = check(reply(("Mac net sales were $33,708 million in fiscal 2024.", [1])), {1: APPLE_TABLE})
    assert out.status == "not_found" and "column '2025'" in out.dropped[0][1]
    ok = check(reply(("Mac net sales were $33,708 million in fiscal 2025.", [1])), {1: APPLE_TABLE})
    assert ok.status == "answered"


def test_figure_with_wrong_row_label_is_dropped():
    out = check(reply(("EMEA revenue was $307,394 million in 2023.", [1])), {1: ALPHABET_TABLE})
    assert out.status == "not_found" and "Total revenues" in out.dropped[0][1]


def test_real_phase4_mistake_total_revenues_as_emea_is_dropped():
    # The model wrote "total revenues" but with the wrong year; the column check catches it
    out = check(reply(("Alphabet's total revenues were $307,394 million for EMEA in fiscal year 2025.", [1])),
                {1: ALPHABET_TABLE})
    assert out.status == "not_found"


def test_correctly_labelled_table_figures_pass():
    out = check(reply(("EMEA revenue was $117,152 million in 2025.", [1]),
                      ("Services net sales were $109,158 million in 2025, up 14%.", [2])),
                {1: ALPHABET_TABLE, 2: APPLE_TABLE})
    assert out.status == "answered" and len(out.sentences) == 2 and not out.dropped


def test_prose_figures_are_not_label_checked():
    shown = {1: "NVIDIA 10-K FY2024 | MD&A | page 36\nData Center revenue for fiscal year 2024 was $47.5 billion."}
    assert check(reply(("Data Center revenue was $47.5 billion in fiscal 2024.", [1])), shown).status == "answered"
