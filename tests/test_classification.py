"""Tests for classification.py — product, platform, device classification."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from classification import (
    classify_product, classify_platform, classify_device,
    _build_campaign_number_product_map
)


# ── classify_product ──

class TestClassifyProduct:
    """Landing page takes priority, campaign number is fallback."""

    def test_landing_page_renters_wins_over_auto_campaign(self):
        assert classify_product("MLBDF001-001RE2", "/renters-insurance", "Microsoft") == "Renters"

    def test_landing_page_condo(self):
        assert classify_product("MLGDF001", "/en/quote/condo", "Google") == "Condo"

    def test_landing_page_homeowners(self):
        assert classify_product("MLGDF001", "/homeowners-insurance", "Google") == "Home"

    def test_landing_page_auto(self):
        assert classify_product("MLGDF172", "/auto-insurance", "Google") == "Auto"

    def test_generic_page_falls_back_to_campaign_number(self):
        assert classify_product("MLBDF172-001RE2", "/en/quote", "Microsoft") == "Renters"

    def test_generic_page_falls_back_001_auto(self):
        assert classify_product("MLBDF001-001RE2", "/", "Microsoft") == "Auto"

    def test_generic_page_falls_back_170_home(self):
        assert classify_product("MLGDF170-001HV", "/en/quote/", "Google") == "Home"

    def test_md5_hash_stripped(self):
        cid = "149084BF90E9D889F9C32F2478957BE5MLBDF172-001RE2"
        assert classify_product(cid, "/", "Microsoft") == "Renters"

    def test_md5_hash_does_not_match_digits_from_hash(self):
        cid = "149084BF90E9D889F9C32F2478957BE5MLBDF001-001RE2"
        assert classify_product(cid, "/", "Microsoft") == "Auto"

    def test_melon_max_auto(self):
        assert classify_product("MLQSAM", "", "Melon Max") == "Auto"

    def test_melon_max_home(self):
        assert classify_product("MLQSHM", "", "Melon Max") == "Home"

    def test_unknown_returns_other(self):
        assert classify_product("UNKNOWNCAMPAIGN", "/", "Unknown") == "Other"

    def test_empty_inputs(self):
        assert classify_product("", "", "Unknown") == "Other"

    def test_domain_with_quote_does_not_match_auto(self):
        """The domain 'insurancequotesouth.com' should not trigger Auto."""
        assert classify_product("UNKNOWNCAMPAIGN", "https://insurancequotesouth.com/", "Unknown") == "Other"


# ── classify_platform ──

class TestClassifyPlatform:
    def test_melon_max(self):
        assert classify_platform("MLQSAM", "") == "Melon Max"

    def test_google_mlg(self):
        assert classify_platform("MLGDF172-001", "Google Ads Desktop") == "Google"

    def test_microsoft_mlb(self):
        assert classify_platform("MLBDF001-001", "Bing/Yahoo Ads Desktop") == "Microsoft"

    def test_listings(self):
        assert classify_platform("MLLIST", "") == "Listings"

    def test_google_traffic_fallback(self):
        assert classify_platform("UNKNOWN", "Google") == "Google"

    def test_bing_traffic_fallback(self):
        assert classify_platform("UNKNOWN", "Bing") == "Microsoft"

    def test_unknown(self):
        assert classify_platform("", "") == "Unknown"


# ── classify_device ──

class TestClassifyDevice:
    def test_google_mobile(self):
        assert classify_device("MLGM001-1", "Google") == "Mobile"

    def test_google_desktop(self):
        assert classify_device("MLGD001-1", "Google") == "Desktop"

    def test_tablet(self):
        assert classify_device("AT", "Melon Max") == "Tablet"

    def test_unknown(self):
        assert classify_device("MLLIST", "Listings") == "Unknown"


# ── _build_campaign_number_product_map ──

class TestCampaignNumberMap:
    def test_map_has_entries(self):
        m = _build_campaign_number_product_map()
        assert len(m) > 0

    def test_001_is_auto(self):
        m = _build_campaign_number_product_map()
        assert m.get("001") == "Auto"

    def test_172_is_renters(self):
        m = _build_campaign_number_product_map()
        assert m.get("172") == "Renters"

    def test_170_is_home(self):
        m = _build_campaign_number_product_map()
        assert m.get("170") == "Home"

    def test_120_is_condo(self):
        m = _build_campaign_number_product_map()
        assert m.get("120") == "Condo"
