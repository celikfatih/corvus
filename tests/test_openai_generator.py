import pytest
from src.infrastructure.openai_generator import find_closest_option

def test_find_closest_option_exact_match():
    """Verify that exact matches are correctly returned."""
    options = ["Yes", "No", "Maybe"]
    assert find_closest_option("Yes", options) == "Yes"
    assert find_closest_option("No", options) == "No"

def test_find_closest_option_case_insensitive_and_whitespace():
    """Verify casing and surrounding whitespace are normalized."""
    options = ["  Agree  ", "Disagree", "Neutral"]
    # Should strip whitespace and ignore casing
    assert find_closest_option("agree", options) == "  Agree  "
    assert find_closest_option("neutral ", options) == "Neutral"
    assert find_closest_option("DISAGREE", options) == "Disagree"

def test_find_closest_option_turkish_normalization():
    """Verify that Turkish character variations (dotted/dotless i, etc.) are matched."""
    options = ["Kesinlikle Katılıyorum", "Katılmıyorum", "Kararsızım"]
    
    # Matching dotless 'ı' and dotted 'i' or general capitalization differences
    assert find_closest_option("kesinlikle katiliyorum", options) == "Kesinlikle Katılıyorum"
    assert find_closest_option("KATILMIYORUM", options) == "Katılmıyorum"
    assert find_closest_option("kararsizim", options) == "Kararsızım"

    # Testing specific character replacements (ç -> c, ş -> s, etc.)
    options_special = ["Çok güçlü", "Başarılı", "Emin değilim"]
    assert find_closest_option("cok guclu", options_special) == "Çok güçlü"
    assert find_closest_option("basarili", options_special) == "Başarılı"

def test_find_closest_option_partial_substring():
    """Verify that partial substring variations match successfully."""
    options = ["Part-time Long Term Internship", "Full-time Job", "Unemployed"]
    
    # Substring matches
    assert find_closest_option("Long Term", options) == "Part-time Long Term Internship"
    assert find_closest_option("Part-time", options) == "Part-time Long Term Internship"
    assert find_closest_option("Full-time", options) == "Full-time Job"

def test_find_closest_option_fallback():
    """Verify that if absolutely no match is found, it falls back gracefully to the first option."""
    options = ["Option A", "Option B", "Option C"]
    # 'Something completely random' has no overlap with options
    assert find_closest_option("Something completely random", options) == "Option A"

def test_find_closest_option_empty_options():
    """Verify that if options list is empty or None, it returns the value itself."""
    assert find_closest_option("Value", []) == "Value"
    assert find_closest_option("Value", None) == "Value"
