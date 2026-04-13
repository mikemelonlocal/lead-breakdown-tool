"""
Campaign classification functions for Lead Analyzer.
Product, platform, device classification and UTM extraction.
"""
import re
import pathlib

import pandas as pd
import streamlit as st

from constants import UTM_TOKENS_FIXED, PLATFORM_RULES, _MELON_MAX_DEVICE_CODES


def load_campaign_mapping():
    """
    Load the campaign/ad group to Product/UTM mapping file.
    This is a static mapping used for enriching both Tab 1 and Tab 2 data.
    
    Returns:
        pd.DataFrame with columns: Campaign, Ad group, Product, UTM
    """
    mapping_path = pathlib.Path(__file__).parent / 'complete_utm_mapping.csv'
    
    # Fallback for different deployment scenarios
    if not mapping_path.exists():
        mapping_path = pathlib.Path('complete_utm_mapping.csv')
    
    if not mapping_path.exists():
        st.warning("⚠️ Campaign mapping file not found. Product/UTM enrichment will be unavailable.")
        return None
    
    try:
        mapping_df = pd.read_csv(mapping_path)
        
        # Validate required columns
        if 'Campaign' not in mapping_df.columns or 'Ad group' not in mapping_df.columns:
            st.error("❌ Mapping file missing required columns: Campaign, Ad group")
            return None
        
        return mapping_df
    except Exception as e:
        st.error(f"❌ Error loading campaign mapping: {e}")
        return None


def classify_platform(campaign_id: str, traffic_source: str) -> str:
    """Classify advertising platform based on campaign ID and traffic source."""
    s = (str(campaign_id) or "").upper()
    t = (str(traffic_source) or "").upper()
    
    if "QS" in s:
        return "Melon Max"
    if "MLLIST" in s:
        return "Listings"
    if "MLB" in s or "MLSB" in s:
        return "Microsoft"
    if "MLG" in s or "MLSG" in s:
        return "Google"
    if (("BD" in s) or ("BM" in s)) and (("BING" in t) or ("YAHOO" in t)):
        return "Microsoft"
    if (("GD" in s) or ("GM" in s)) and ("GOOGLE" in t):
        return "Google"
    if ("GOOGLE" in t) and ("QS" not in s):
        return "Google"
    if (("BING" in t) or ("YAHOO" in t)) and ("QS" not in s):
        return "Microsoft"
    
    return "Unknown"


@st.cache_resource
def _build_campaign_number_product_map():
    """Build a campaign-number-to-product lookup from the mapping CSV.

    Reads complete_utm_mapping.csv once and extracts the consensus product
    for each 3-4 digit campaign number found in UTM codes.  Falls back to
    a minimal hardcoded map if the CSV is unavailable.
    """
    try:
        mapping_path = pathlib.Path(__file__).parent / 'complete_utm_mapping.csv'
        if not mapping_path.exists():
            mapping_path = pathlib.Path('complete_utm_mapping.csv')
        if not mapping_path.exists():
            return {}

        mdf = pd.read_csv(mapping_path, usecols=['UTM', 'Product'])
        mdf['_utm'] = mdf['UTM'].fillna('').astype(str).str.upper()

        # Extract 3-4 digit campaign number from UTM codes like GD172, GM001, etc.
        mdf['_num'] = mdf['_utm'].str.extract(r'[A-Z]*[DM]?F?(\d{3,4})', expand=False)
        mdf = mdf.dropna(subset=['_num', 'Product'])

        # For each number, take the most common product (consensus)
        return (
            mdf.groupby('_num')['Product']
            .agg(lambda s: s.mode().iloc[0] if len(s.mode()) > 0 else None)
            .dropna()
            .to_dict()
        )
    except Exception:
        return {}


def classify_product(campaign_id: str, landing_page: str, platform: str) -> str:
    """Classify insurance product type based on landing page and campaign ID.

    Priority order:
    1. Melon Max prefix (QSA → Auto, QSH → Home)
    2. Landing page URL path — the most reliable signal for what the user
       actually saw. Checks the path portion only (domain is stripped so
       "insurancequotesouth.com" doesn't false-match on "quote").
    3. Campaign number from mapping CSV — used as fallback when the landing
       page is generic (e.g. a bare /quote page with no product keyword).
    """
    raw = (str(campaign_id) or "").strip()

    # Strip MD5 hash prefix (32 hex chars) if present
    # e.g. "149084BF90E9D889F9C32F2478957BE5MLBDF172-001RE2" -> "MLBDF172-001RE2"
    hash_match = re.match(r'^[0-9A-Fa-f]{32}(.+)$', raw)
    if hash_match:
        raw = hash_match.group(1)

    s_id = raw.upper()

    # ── 1. Melon Max: product encoded in campaign ID prefix ──
    if platform == "Melon Max":
        if "QSA" in s_id:
            return "Auto"
        if "QSH" in s_id:
            return "Home"

    # ── 2. Landing page path keywords (primary signal) ──
    s_lp = (str(landing_page) or "").lower()
    # Strip domain so "insurancequotesouth.com" doesn't false-match
    path_part = s_lp.split('/', 3)[-1] if '/' in s_lp else ''

    if "renters" in path_part:
        return "Renters"
    if "condo" in path_part:
        return "Condo"
    if "homeowners" in path_part or "home-insurance" in path_part:
        return "Home"
    if "auto" in path_part or "car-insurance" in path_part:
        return "Auto"

    # ── 3. Campaign number fallback (for generic/quote-only pages) ──
    num_match = re.search(
        r'(?:MLSG|MLSB|MLG|MLB|[GB])[DM]F?(\d{3,4})', s_id
    )
    if not num_match:
        num_match = re.search(r'F(\d{3,4})', s_id)
    if not num_match:
        num_match = re.search(r'(\d{3,4})', s_id)

    if num_match:
        campaign_num = num_match.group(1)
        product = _CAMPAIGN_NUM_PRODUCT_MAP.get(campaign_num)
        if product:
            return product

    return "Other"


def classify_device(campaign_id: str, platform: str) -> str:
    """
    Classify device based on campaign ID patterns found in the campaign ID string.
    
    Mobile patterns: AM, HM, GM, BM, MLBM, MLGM, MLSBM, MLSGM
    Desktop patterns: AD, HD, GD, BD, MLBD, MLGD, MLSBD, MLSGD
    Tablet patterns: AT, HT
    
    These patterns can appear anywhere in the campaign ID.
    """
    if pd.isna(campaign_id):
        return "Unknown"
    
    cid = str(campaign_id).upper()
    
    # Mobile patterns (check longer patterns first to avoid false matches)
    # e.g., MLSBM should match before BM
    mobile_patterns = ["MLSBM", "MLSGM", "MLBM", "MLGM", "AM", "HM", "GM", "BM"]
    for pattern in mobile_patterns:
        if pattern in cid:
            return "Mobile"
    
    # Desktop patterns (check longer patterns first)
    desktop_patterns = ["MLSBD", "MLSGD", "MLBD", "MLGD", "AD", "HD", "GD", "BD"]
    for pattern in desktop_patterns:
        if pattern in cid:
            return "Desktop"
    
    # Tablet patterns
    tablet_patterns = ["AT", "HT"]
    for pattern in tablet_patterns:
        if pattern in cid:
            return "Tablet"
    
    # No device pattern found
    return "Unknown"



# Module-level cache — built once on import
_CAMPAIGN_NUM_PRODUCT_MAP = _build_campaign_number_product_map()


def extract_utm_from_campaign_id(campaign_id, tokens=UTM_TOKENS_FIXED):
    """
    Extract UTM token from campaign ID.

    Returns the actual UTM code (e.g., "AM", "HM", "172"), never a product name.
    Uses the campaign number anchored to the platform prefix (e.g., MLGDF172 -> 172)
    so that ad group numbers after the dash (e.g., -001) don't false-match.
    """
    raw = str(campaign_id or "").strip()

    # Strip MD5 hash prefix if present
    hash_match = re.match(r'^[0-9A-Fa-f]{32}(.+)$', raw)
    if hash_match:
        raw = hash_match.group(1)

    upper = raw.upper()

    # Melon Max campaigns — return the device code
    if "QS" in upper:
        for code in _MELON_MAX_DEVICE_CODES:
            if code in upper:
                return code
        return "QS"

    # Listings
    if "MLLIST" in upper:
        return "MLLIST"

    # Extract campaign number anchored to platform+device prefix
    num_match = re.search(
        r'(?:MLSG|MLSB|MLG|MLB|[GB])[DM]F?(\d{3,4})', upper
    )
    if not num_match:
        num_match = re.search(r'F(\d{3,4})', upper)

    if num_match:
        return num_match.group(1)

    # Non-numeric tokens (PPR, PPA, PPH, PPC) — substring match
    for t in tokens:
        tt = str(t or "").strip()
        if not tt or tt in _MELON_MAX_DEVICE_CODES or tt == "MLLIST":
            continue
        if tt.isdigit():
            continue
        if tt.lower() in raw.lower():
            return tt

    return ""
