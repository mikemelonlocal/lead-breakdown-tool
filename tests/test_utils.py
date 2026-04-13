"""Tests for utils.py — normalization, column detection, formatting."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from utils import (
    _norm, get_col, is_currency_col, is_percent_col,
    validate_upload, extract_date_range_from_filename
)


class TestNorm:
    def test_basic(self):
        assert _norm("Quote Starts") == "quote_starts"

    def test_special_chars(self):
        assert _norm("CPL (Platform)") == "cpl_platform_"

    def test_whitespace(self):
        assert _norm("  Phone Clicks  ") == "phone_clicks"

    def test_empty(self):
        assert _norm("") == ""


class TestGetCol:
    def test_exact_match(self):
        df = pd.DataFrame(columns=["Quote Starts", "Phone Clicks"])
        assert get_col(df, ["quote_starts"]) == "Quote Starts"

    def test_substring_match(self):
        df = pd.DataFrame(columns=["Campaign IDs", "Landing Page"])
        assert get_col(df, ["campaign_id"]) == "Campaign IDs"

    def test_not_found(self):
        df = pd.DataFrame(columns=["A", "B"])
        assert get_col(df, ["xyz"]) is None

    def test_default(self):
        df = pd.DataFrame(columns=["A"])
        assert get_col(df, ["xyz"], default="fallback") == "fallback"


class TestCurrencyPercent:
    def test_cpl_is_currency(self):
        assert is_currency_col("cpl_platform") is True

    def test_spend_is_currency(self):
        assert is_currency_col("spend") is True

    def test_leads_not_currency(self):
        assert is_currency_col("leads") is False

    def test_share_is_percent(self):
        assert is_percent_col("lead_share_pct") is True

    def test_leads_not_percent(self):
        assert is_percent_col("leads") is False


class TestValidateUpload:
    def test_empty_df(self):
        issues = validate_upload(pd.DataFrame())
        assert any(level == "error" for level, _ in issues)

    def test_none(self):
        issues = validate_upload(None)
        assert any(level == "error" for level, _ in issues)

    def test_valid_df(self):
        df = pd.DataFrame({"Campaign IDs": ["A"], "Quote Starts": [1]})
        issues = validate_upload(df)
        assert len(issues) == 0

    def test_no_expected_columns(self):
        df = pd.DataFrame({"foo": [1], "bar": [2]})
        issues = validate_upload(df, "test.csv")
        assert any("expected columns" in msg.lower() for _, msg in issues)


class TestDateRange:
    def test_standard_filename(self):
        start, end = extract_date_range_from_filename(
            "campaign_report_2026-03-01_to_2026-03-31.csv"
        )
        assert start == "2026-03-01"
        assert end == "2026-03-31"

    def test_no_match(self):
        start, end = extract_date_range_from_filename("report.csv")
        assert start is None
        assert end is None
