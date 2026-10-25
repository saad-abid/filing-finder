from src.retrieval.query_parser import parse_query


def test_single_company_year_range():
    f = parse_query("Across Apple's 2021-2025 10-Ks, how did the revenue mix change?")
    assert f.tickers == ["AAPL"]
    assert f.years == [2021, 2022, 2023, 2024, 2025]


def test_fiscal_year_range_with_words():
    f = parse_query("How did NVIDIA describe demand from fiscal 2021 through fiscal 2025?")
    assert f.tickers == ["NVDA"]
    assert f.years == [2021, 2022, 2023, 2024, 2025]


def test_several_companies_and_aliases():
    f = parse_query("Compare capex for Microsoft, Alphabet, Amazon and NVIDIA.")
    assert f.tickers == ["AMZN", "GOOGL", "MSFT", "NVDA"]
    assert f.years == []
    assert parse_query("Google Cloud revenue").tickers == ["GOOGL"]
    assert parse_query("AWS operating income").tickers == ["AMZN"]


def test_no_company_means_all_companies():
    f = parse_query("Which companies changed risk-factor language between 2021 and 2025?")
    assert f.tickers == []
    assert f.years == [2021, 2022, 2023, 2024, 2025]
    assert f.item_codes == ["1A"]   # hyphenated "risk-factor" still counts
    assert parse_query("risk factors about export controls").item_codes == ["1A"]


def test_single_years_and_latest():
    f = parse_query("Apple FY2023 vs 2025 services revenue")
    assert f.years == [2023, 2025]
    assert parse_query("geographic revenue in the latest 10-K").latest


def test_sections_and_financial_statements():
    assert parse_query("What does MD&A say about Azure?").item_codes == ["7"]
    assert parse_query("NVIDIA balance sheet inventory").financial_statements
    assert not parse_query("NVIDIA supply constraints").financial_statements


def test_words_containing_aliases_do_not_match():
    assert parse_query("an applesauce company").tickers == []


def test_over_time_questions_without_years():
    f = parse_query("How did NVIDIA describe Data Center demand and supply constraints over time?")
    assert f.tickers == ["NVDA"] and f.years == [] and f.over_time
    assert parse_query("How did Microsoft's description of Azure change?").over_time
    assert not parse_query("Compare capital expenditures for Microsoft and Alphabet.").over_time


def test_which_companies_means_every_company():
    f = parse_query("Which companies added or changed risk-factor language on export controls?")
    assert f.all_companies and f.over_time and f.item_codes == ["1A"]
    assert parse_query("What are each company's main geographic revenue exposures?").all_companies
    assert not parse_query("What did Apple say about suppliers?").all_companies


def test_search_text_keeps_only_the_topic():
    from src.retrieval.query_parser import search_text
    assert search_text("How did Apple describe supplier concentration in 2024?") == "supplier concentration"
    assert search_text("Compare capital expenditures for Microsoft, Alphabet, Amazon and NVIDIA.") \
        .startswith("capital expenditures")
    # AWS is a filter (Amazon) *and* the topic, so it stays
    assert search_text("Compare Amazon's AWS operating income, 2021-2025.") == "AWS operating income"
    # nothing left after cleaning -> fall back to the full question
    assert search_text("What did Apple say in 2024?") == "What did Apple say in 2024?"


def test_search_text_adds_the_words_filings_use():
    from src.retrieval.query_parser import search_text
    s = search_text("What are each company's main geographic revenue exposures?")
    assert s.startswith("main geographic revenue exposures") and "United States" in s
    assert search_text("Compare capex for Microsoft.").endswith("capital expenditures")
    assert search_text("How did Apple describe supplier concentration in 2024?") == "supplier concentration"
