"""Tests for extract_utm_from_campaign_id — UTM extraction edge cases."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from classification import extract_utm_from_campaign_id


class TestExtractUtm:
    """All the edge cases discovered during development."""

    # Melon Max device codes
    def test_melon_max_auto_mobile(self):
        assert extract_utm_from_campaign_id("MLQSAM") == "AM"

    def test_melon_max_home_desktop(self):
        assert extract_utm_from_campaign_id("MLQSHD") == "HD"

    def test_melon_max_unknown_device(self):
        assert extract_utm_from_campaign_id("MLQSXX") == "QS"

    # Melon Max false positive prevention
    def test_print_campaign_does_not_match_am(self):
        """PRINT:3P7RP3K4000AM348 contains 'AM' but is not Melon Max."""
        assert extract_utm_from_campaign_id("PRINT:3P7RP3K4000AM348") == ""

    # Campaign number extraction
    def test_google_desktop_172(self):
        assert extract_utm_from_campaign_id("MLGDF172-001HVT1") == "172"

    def test_microsoft_desktop_001(self):
        assert extract_utm_from_campaign_id("MLBDF001-001RE2") == "001"

    def test_campaign_number_not_ad_group(self):
        """MLGDF172-001: should extract 172 (campaign), not 001 (ad group)."""
        assert extract_utm_from_campaign_id("MLGDF172-001HVT1") == "172"

    def test_four_digit_code(self):
        assert extract_utm_from_campaign_id("MLSGD0055-1R") == "0055"

    def test_short_prefix_gd(self):
        assert extract_utm_from_campaign_id("GD205-1") == "205"

    def test_short_prefix_gm(self):
        assert extract_utm_from_campaign_id("GM001") == "001"

    # MD5 hash prefix
    def test_md5_hash_stripped(self):
        cid = "AABBAABB" * 4 + "MLBDF172-001RE2"
        assert extract_utm_from_campaign_id(cid) == "172"

    # Listings
    def test_mllist(self):
        assert extract_utm_from_campaign_id("MLLIST") == "MLLIST"

    # Non-numeric tokens
    def test_ppr_token(self):
        assert extract_utm_from_campaign_id("PPR-CAMPAIGN") == "PPR"

    # Edge cases
    def test_empty_string(self):
        assert extract_utm_from_campaign_id("") == ""

    def test_none(self):
        assert extract_utm_from_campaign_id(None) == ""

    def test_gd004(self):
        assert extract_utm_from_campaign_id("MLGD004-10") == "004"
