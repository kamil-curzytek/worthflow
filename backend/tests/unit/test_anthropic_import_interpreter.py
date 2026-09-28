import pytest

from app.services.ai.anthropic_import_interpreter import _parse_interpretation
from app.services.ai.import_interpreter import ImportInterpreterError


def test_parses_clean_json():
    text = """
    {
      "summary": "Found two accounts.",
      "accounts": [
        {
          "source_label": "Revolut",
          "suggested_name": "Revolut",
          "suggested_currency": "PLN",
          "suggested_type": "checking",
          "suggested_asset_class": "cash",
          "entries": [{"date": "2024-01-01", "value": "1000.50"}]
        }
      ],
      "warnings": []
    }
    """
    result = _parse_interpretation(text)
    assert result.summary == "Found two accounts."
    assert len(result.accounts) == 1
    assert result.accounts[0].suggested_name == "Revolut"
    assert result.accounts[0].entries[0].value == "1000.50"


def test_strips_markdown_code_fence():
    text = '```json\n{"summary": "ok", "accounts": [], "warnings": []}\n```'
    result = _parse_interpretation(text)
    assert result.summary == "ok"


def test_extracts_json_surrounded_by_commentary():
    text = (
        "Sure, here is the mapping:\n"
        '{"summary": "ok", "accounts": [], "warnings": []}\n'
        "Hope that helps!"
    )
    result = _parse_interpretation(text)
    assert result.summary == "ok"


def test_raises_on_unparseable_response():
    with pytest.raises(ImportInterpreterError):
        _parse_interpretation("Sorry, I can't help with that.")


def test_unrecognized_currency_defaults_to_eur_with_warning():
    text = """
    {
      "summary": "ok",
      "accounts": [
        {
          "source_label": "Foo",
          "suggested_name": "Foo",
          "suggested_currency": "GBP",
          "suggested_type": "checking",
          "suggested_asset_class": "cash",
          "entries": []
        }
      ],
      "warnings": []
    }
    """
    result = _parse_interpretation(text)
    assert result.accounts[0].suggested_currency == "EUR"
    assert any("GBP" in w for w in result.warnings)


def test_unrecognized_type_and_asset_class_default_to_other():
    text = """
    {
      "summary": "ok",
      "accounts": [
        {
          "source_label": "Foo",
          "suggested_name": "Foo",
          "suggested_currency": "EUR",
          "suggested_type": "not-a-real-type",
          "suggested_asset_class": "not-a-real-class",
          "entries": []
        }
      ],
      "warnings": []
    }
    """
    result = _parse_interpretation(text)
    assert result.accounts[0].suggested_type == "other"
    assert result.accounts[0].suggested_asset_class == "other"
    assert len(result.warnings) == 2


def test_skips_entries_with_bad_date_or_value():
    text = """
    {
      "summary": "ok",
      "accounts": [
        {
          "source_label": "Foo",
          "suggested_name": "Foo",
          "suggested_currency": "EUR",
          "suggested_type": "checking",
          "suggested_asset_class": "cash",
          "entries": [
            {"date": "not-a-date", "value": "100"},
            {"date": "2024-01-01", "value": "not-a-number"},
            {"date": "2024-02-01", "value": "250.75"}
          ]
        }
      ],
      "warnings": []
    }
    """
    result = _parse_interpretation(text)
    assert len(result.accounts[0].entries) == 1
    assert result.accounts[0].entries[0].date == "2024-02-01"
    assert len(result.warnings) == 2
