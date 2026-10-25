from src.evaluation.scorecard import grade_sentence, load_facts, score

FACTS = load_facts()


def verdicts(text, tickers):
    return {num: verdict for num, verdict, _ in grade_sentence(text, tickers, FACTS)}


def test_correct_figure_with_label_and_year():
    assert verdicts("Mac net sales were $35,190 million in 2021.", ["AAPL"]) == {"35190": "correct"}


def test_real_figure_with_wrong_year_is_caught():
    # FY2025 Americas figure presented as FY2024 (a real mistake from the Phase 4 run)
    v = verdicts("Apple's net sales for fiscal year 2024 were $178,353 million in the Americas.", ["AAPL"])
    assert v == {"178353": "wrong_label"}


def test_real_figure_with_wrong_row_is_caught():
    # Alphabet's 2023 total revenues presented as EMEA (a real mistake from the Phase 4 run)
    v = verdicts("Alphabet's revenues were $307,394 million for EMEA in fiscal year 2025.", ["GOOGL"])
    assert v == {"307394": "wrong_label"}
    _, why = [(n, w) for n, verdict, w in grade_sentence(
        "Alphabet's revenues were $307,394 million for EMEA in 2025.", ["GOOGL"], FACTS)][0]
    assert "Total revenues FY2023" in why


def test_unknown_figures_and_years_are_not_graded_as_wrong():
    assert verdicts("Data Center revenue was $47.5 billion in fiscal year 2024.", ["NVDA"]) == {"47.5": "unverified"}


def test_figures_only_match_the_cited_company():
    # 35,190 is an Apple figure; a sentence citing only NVIDIA can't claim it
    assert verdicts("Revenue was $35,190 million in 2021.", ["NVDA"]) == {"35190": "unverified"}


def test_score_totals_across_answers():
    results = [{"number": 1, "sentences": [
        {"text": "Mac net sales were $35,190 million in 2021.", "sources": [{"ticker": "AAPL"}]},
        {"text": "Americas net sales were $178,353 million in 2024.", "sources": [{"ticker": "AAPL"}]}]}]
    totals, problems = score(results, FACTS)
    assert totals["correct"] == 1 and totals["wrong_label"] == 1
    assert problems[0][0] == 1


def test_years_written_as_fy2021_are_recognised():
    assert verdicts("Mac revenue was $35,190 million in FY2021.", ["AAPL"]) == {"35190": "correct"}
