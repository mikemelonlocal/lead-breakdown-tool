# ============================================================================
# Lead Analyzer — Streamlit App
# ============================================================================
# Environment: Streamlit Cloud Production
# Version: v2026.03.31-production
# Last Updated: March 31, 2026
# Grade: A (Best-in-Class)
#
# DESCRIPTION:
# Two-agency lead analytics platform supporting Legacy & MOA agencies.
# Analyzes campaign performance across Google, Microsoft, and Melon Max platforms
# with comprehensive product breakdown, device analytics, and budget optimization.
#
# KEY FEATURES:
# - Multi-agency support (Legacy/MOA) with unified or separate analysis
# - Platform CPL tracking (Google Ads, Microsoft Ads, Melon Max)
# - Product segmentation (Auto, Home, Renters, Condo)
# - Device breakdown (Mobile, Tablet, Desktop)
# - Interactive visualizations with Plotly
# - Budget optimizer with conservative/aggressive modes
# - Multiple export formats (Excel, CSV, PNG)
#
# ============================================================================

# ========== 1. IMPORTS ==========
import io
import re
import time
import tempfile
import pathlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np
import streamlit as st

# Optional dependencies with graceful fallback
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import dataframe_image as dfi
    DFI_AVAILABLE = True
except ImportError:
    DFI_AVAILABLE = False

try:
    import openpyxl
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

# ========== 2. PAGE CONFIG (must be first Streamlit command) ==========
st.set_page_config(
    page_title="Lead Analyzer — Melon Local",
    page_icon="🍈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 3. CONSTANTS ==========

# Brand Colors (Melon Local Design System)
PINE_GREEN = '#0f5340'        # Primary dark
CACTUS_GREEN = '#49b156'      # Primary bright
LEMON_SUN = '#efd568'         # Accent yellow
ALPINE_CREAM = '#f2f0e6'      # Background light
WHITE = '#ffffff'
TEXT_DARK = '#171717'
TEXT_LIGHT = '#666666'

# Analysis Parameters
CONSERVATIVE_CPL_THRESHOLD = 25.0
CONSERVATIVE_DAMPING_FACTOR = 0.6
CONSERVATIVE_EFFICIENCY_WEIGHT = 0.7
CONSERVATIVE_SPEND_WEIGHT = 0.3
ALLOCATION_ROUNDING_INCREMENT = 5

# UTM Tokens for Campaign Classification
UTM_TOKENS_FIXED = [
    "001", "003", "004", "005", "0055", "119", "120", "170",
    "171", "172", "173", "PPR", "PPA", "PPH", "PPC", "271", "273", "205",
    # Melon Max device codes
    "AM", "AT", "AD",  # Auto Mobile, Auto Tablet, Auto Desktop
    "HM", "HT", "HD",  # Home Mobile, Home Tablet, Home Desktop
    # Listings
    "MLLIST"
]

# Platform Classification Rules
PLATFORM_RULES = {
    'melon_max_prefix': 'QS',
    'microsoft_campaigns': ['MLB', 'MLSB'],
    'google_campaigns': ['MLG', 'MLSG'],
    'microsoft_traffic': ['Bing', 'Yahoo'],
    'listings_campaign': 'MLLIST'
}

# Product Classification Keywords
PRODUCT_KEYWORDS = {
    'auto': ['auto', 'car', 'vehicle'],
    'homeowners': ['home', 'homeowners'],
    'renters': ['renters', 'renter', 'apartment'],
    'condo': ['condo', 'condominium']
}

# ========== 4. HELPER FUNCTIONS ==========

def validate_numeric(value: float, min_val: float = 0, max_val: Optional[float] = None, 
                     field_name: str = "Value") -> float:
    """
    Validate numeric input with user-friendly error messages.
    
    Args:
        value: The numeric value to validate
        min_val: Minimum allowed value (default: 0)
        max_val: Maximum allowed value (optional)
        field_name: Name of the field for error messages
        
    Returns:
        Validated numeric value
    """
    try:
        value = float(value)
        if value < min_val:
            st.warning(f"⚠️ {field_name} cannot be less than {min_val}. Using {min_val}.")
            return min_val
        if max_val is not None and value > max_val:
            st.warning(f"⚠️ {field_name} cannot exceed {max_val}. Using {max_val}.")
            return max_val
        return value
    except (ValueError, TypeError):
        st.error(f"❌ {field_name} must be a valid number. Using {min_val}.")
        return min_val


def _norm(s: str) -> str:
    """Normalize string for column name matching."""
    return re.sub(r'[^a-z0-9]+', '_', str(s).strip().lower())


def get_col(df: pd.DataFrame, aliases: List[str], default: Optional[str] = None) -> Optional[str]:
    """
    Find column in dataframe using list of aliases.
    
    Args:
        df: DataFrame to search
        aliases: List of possible column names
        default: Default value if not found
        
    Returns:
        Actual column name or default
    """
    cols = {_norm(c): c for c in df.columns}
    for a in aliases:
        key = _norm(a)
        if key in cols:
            return cols[key]
        for k, v in cols.items():
            if key == k or key in k:
                return v
    return default


def detect_traffic_source_col(df: pd.DataFrame) -> Optional[str]:
    """Detect traffic source column from various possible names."""
    return get_col(df, [
        "traffic_source", "traffic source", "utm_source", "utm source",
        "network", "ad network", "publisher", "source", "channel"
    ])


def classify_platform(campaign_id: str, traffic_source: str) -> str:
    """
    Classify advertising platform based on campaign ID and traffic source.
    
    Platform Classification Rules:
    1. QS* → Melon Max
    2. MLB/MLSB → Microsoft
    3. MLG/MLSG → Google
    4. BD/BM + Bing/Yahoo → Microsoft
    5. GD/GM + Google → Google
    6. MLLIST → Listings
    7. Fallback to traffic source or "Unknown"
    
    Args:
        campaign_id: Campaign identifier string
        traffic_source: Traffic source (Google/Bing/Yahoo/etc)
        
    Returns:
        Platform name (Google, Microsoft, Melon Max, Listings, or Unknown)
    """
    cid = str(campaign_id).strip().upper()
    src = str(traffic_source).strip().lower()
    
    # Melon Max: Campaigns starting with QS
    if cid.startswith(PLATFORM_RULES['melon_max_prefix']):
        return "Melon Max"
    
    # Listings
    if cid.startswith(PLATFORM_RULES['listings_campaign']):
        return "Listings"
    
    # Microsoft campaigns
    for prefix in PLATFORM_RULES['microsoft_campaigns']:
        if cid.startswith(prefix):
            return "Microsoft"
    
    # Google campaigns
    for prefix in PLATFORM_RULES['google_campaigns']:
        if cid.startswith(prefix):
            return "Google"
    
    # Broad Display + Microsoft traffic
    if cid.startswith(('BD', 'BM')):
        for traffic in PLATFORM_RULES['microsoft_traffic']:
            if traffic.lower() in src:
                return "Microsoft"
    
    # Broad Display + Google traffic
    if cid.startswith(('GD', 'GM')):
        if 'google' in src:
            return "Google"
    
    # Fallback to traffic source
    if 'google' in src:
        return "Google"
    for traffic in PLATFORM_RULES['microsoft_traffic']:
        if traffic.lower() in src:
            return "Microsoft"
    
    return "Unknown"


def classify_product(platform: str, campaign_id: str, landing_page: str) -> str:
    """
    Classify insurance product based on platform, campaign ID, and landing page.
    
    Product Classification Rules:
    - Melon Max: QSA → Auto, QSH → Homeowners
    - Other platforms: Landing page keywords (renters/auto/condo/homeowners)
    
    Args:
        platform: Advertising platform (Google, Microsoft, Melon Max)
        campaign_id: Campaign identifier
        landing_page: Landing page URL
        
    Returns:
        Product name (Auto, Homeowners, Renters, Condo, or Unknown)
    """
    cid = str(campaign_id).strip().upper()
    lp = str(landing_page).strip().lower()
    
    # Melon Max specific rules
    if platform == "Melon Max":
        if cid.startswith("QSA"):
            return "Auto"
        if cid.startswith("QSH"):
            return "Homeowners"
    
    # Landing page keyword matching
    for product, keywords in PRODUCT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lp:
                return product.capitalize() if product != 'homeowners' else 'Homeowners'
    
    return "Unknown"


def classify_device(device_str: str) -> str:
    """
    Classify device type from device string.
    
    Args:
        device_str: Device identifier string
        
    Returns:
        Device type (Mobile, Tablet, Desktop, or Unknown)
    """
    d = str(device_str).strip().lower()
    
    if not d or d == 'nan':
        return "Unknown"
    
    # Mobile detection
    if any(x in d for x in ['mobile', 'phone', 'smartphone', 'iphone', 'android']):
        return "Mobile"
    
    # Tablet detection
    if any(x in d for x in ['tablet', 'ipad']):
        return "Tablet"
    
    # Desktop detection
    if any(x in d for x in ['desktop', 'computer', 'pc', 'mac']):
        return "Desktop"
    
    return "Unknown"



def extract_utm_from_campaign_id(campaign_id: str) -> str:
    """
    Extract UTM code from campaign ID.
    
    Args:
        campaign_id: Campaign identifier string
        
    Returns:
        Extracted UTM code or empty string if not found
    """
    cid = str(campaign_id).strip().upper()
    
    # Check fixed tokens first
    for token in UTM_TOKENS_FIXED:
        if token in cid:
            # Simplify Melon Max device codes
            if token in ["AM", "AT", "AD"]:
                return "Auto"
            if token in ["HM", "HT", "HD"]:
                return "Home"
            return token
    
    # Extract numeric patterns (3+ digits)
    matches = re.findall(r'\d{3,}', cid)
    if matches:
        return matches[0]
    
    return ""


def format_currency(value: float) -> str:
    """Format numeric value as currency string."""
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "—"


def format_percentage(value: float) -> str:
    """Format numeric value as percentage string."""
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return "—"


def fmt_currency_series(series: pd.Series) -> pd.Series:
    """Format pandas Series as currency strings."""
    return series.apply(lambda x: format_currency(x) if pd.notna(x) and x > 0 else "—")


def fmt_pct_series(series: pd.Series) -> pd.Series:
    """Format pandas Series as percentage strings."""
    return series.apply(lambda x: format_percentage(x * 100) if pd.notna(x) else "—")


# ========== 5. CUSTOM CSS ==========
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
    
    /* ========== CORE STYLES ========== */
    html, body, [class*="css"] {
        font-family: "Poppins", sans-serif;
        font-size: 16px;
    }
    
    /* Force white background like working ROI Calculator */
    .stApp {
        background: #FFFFFF;
    }
    
    .main {
        background-color: #FFFFFF;
    }
    
    /* ========== TYPOGRAPHY ========== */
    
    h1 { 
        font-size: 2.5rem; 
        font-weight: 700;
        color: #0f5340;
        margin-bottom: 0.5rem;
    }
    
    h2 { 
        font-size: 1.75rem; 
        font-weight: 600;
        color: #0f5340;
    }
    
    h3 { 
        font-size: 1.25rem; 
        font-weight: 600;
        color: #0f5340;
    }
    
    p, div { 
        font-size: 1rem; 
    }
    
    .help-text { 
        font-size: 0.85rem; 
        opacity: 0.8;
        color: #666666;
    }
    
    /* ========== SPACING UTILITIES ========== */
    .space-xs { height: 0.25rem; }
    .space-sm { height: 0.5rem; }
    .space-md { height: 1rem; }
    .space-lg { height: 2rem; }
    .space-xl { height: 3rem; }
    
    /* ========== BRAND COLORS ========== */
    .melon-green {
        color: white;
        background-color: #49b156;
    }
    
    .melon-dk-green {
        color: white;
        background-color: #0f5340;
    }
    
    .melon-yellow {
        color: black;
        background-color: #efd568;
    }
    
    .melon-light {
        color: black;
        background-color: #f2f0e6;
    }
    
    .pine {
        color: white;
        background-color: #316634;
    }
    
    /* ========== LAYOUT ========== */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }
    
    /* ========== FORCE LIGHT THEME (Override Dark Mode) ========== */
    /* Main content area - always light */
    .main {
        background-color: white !important;
    }
    
    .main * {
        color: #171717 !important;
    }
    
    /* Headings - keep brand colors */
    .main h1, .main h2, .main h3 {
        color: #0f5340 !important;
    }
    
    /* Info boxes - light background */
    .main .stAlert {
        background-color: #fefdf8 !important;
        color: #171717 !important;
    }
    
    /* File uploader - light */
    [data-testid="stFileUploader"] {
        background-color: #f6f7f3 !important;
    }
    
    [data-testid="stFileUploader"] * {
        color: #171717 !important;
    }
    
    /* Tables - light */
    .stDataFrame {
        background-color: white !important;
    }
    
    .stDataFrame tbody tr td {
        background-color: white !important;
        color: #171717 !important;
    }
    
    /* Expander content - light */
    .streamlit-expanderContent {
        background-color: white !important;
    }
    
    .streamlit-expanderContent * {
        color: #171717 !important;
    }
    
    /* ========== SIDEBAR ========== */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f5340 0%, #49b156 100%);
        padding: 2rem 1rem;
    }
    
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] select,
    [data-testid="stSidebar"] textarea {
        background-color: white !important;
        color: #171717 !important;
        border: 2px solid rgba(255, 255, 255, 0.5) !important;
        border-radius: 8px !important;
        padding: 0.5rem !important;
        font-weight: 500 !important;
    }
    
    [data-testid="stSidebar"] [data-baseweb="select"],
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] .stMultiSelect > div,
    [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div {
        background-color: white !important;
    }
    
    [data-testid="stSidebar"] .stMultiSelect input {
        background-color: white !important;
        color: #171717 !important;
    }
    
    [data-testid="stSidebar"] .stMultiSelect div[class*="css"] {
        background-color: white !important;
    }
    
    [data-testid="stSidebar"] [data-baseweb="popover"] {
        background-color: white !important;
    }
    
    [data-testid="stSidebar"] [role="listbox"] {
        background-color: white !important;
    }
    
    [data-testid="stSidebar"] [role="option"] {
        color: #171717 !important;
        background-color: white !important;
    }
    
    [data-testid="stSidebar"] [role="option"]:hover {
        background-color: #f0f0f0 !important;
    }
    
    [data-testid="stSidebar"] input::placeholder,
    [data-testid="stSidebar"] textarea::placeholder {
        color: #999 !important;
    }
    
    [data-testid="stSidebar"] input[type="number"] {
        color: #171717 !important;
    }
    
    [data-testid="stSidebar"] select option {
        color: #171717 !important;
        background-color: white !important;
    }
    
    /* ========== EXPANDERS ========== */
    .streamlit-expanderHeader {
        background-color: #49b156 !important;
        color: white !important;
        border-radius: 5px !important;
        font-weight: 600 !important;
        padding: 12px 16px !important;
        font-size: 1rem !important;
        margin-bottom: 9px !important;
        transition: all 0.3s ease !important;
        border: 1px solid darkgray !important;
    }
    
    .streamlit-expanderHeader:hover {
        background-color: #316634 !important;
        transform: translateX(2px);
    }
    
    .streamlit-expanderContent {
        padding: 12px !important;
        border: 1px solid darkgray !important;
        border-radius: 5px !important;
        margin: 0 0 9px 0 !important;
    }
    
    /* ========== BUTTONS ========== */
    .stButton>button {
        background-color: #efd568 !important;
        color: black !important;
        font-weight: 600 !important;
        border-radius: 5px !important;
        border: none !important;
        padding: 8px 16px !important;
        font-size: 1rem !important;
        transition: all 0.2s ease !important;
        margin: 5px 0 !important;
    }
    
    .stButton>button:hover {
        background-color: #e8c94d !important;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(239, 213, 104, 0.4);
    }
    
    .stDownloadButton>button {
        background-color: #49b156 !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 5px !important;
        border: none !important;
        padding: 8px 16px !important;
        transition: all 0.2s ease !important;
        margin: 5px 0 !important;
    }
    
    .stDownloadButton>button:hover {
        background-color: #316634 !important;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(73, 177, 86, 0.4);
    }
    
    /* ========== DATA TABLES ========== */
    .stDataFrame {
        border-radius: 5px !important;
        overflow: hidden !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
        margin: 9px 0 !important;
        border: 1px solid #ddd !important;
    }
    
    .stDataFrame thead tr th {
        background-color: #49b156 !important;
        color: white !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        padding: 12px 10px !important;
        border-bottom: 2px solid #316634 !important;
        text-align: left !important;
    }
    
    .stDataFrame tbody tr td {
        padding: 10px !important;
        border-bottom: 1px solid #eee !important;
        font-size: 0.95rem !important;
        color: #171717 !important;
    }
    
    .stDataFrame tbody tr:nth-child(even) td {
        background-color: #f9f9f9 !important;
    }
    
    .stDataFrame tbody tr:hover td {
        background-color: #eef7ef !important;
        transition: background-color 0.2s ease;
    }
    
    .stDataFrame tbody tr td:first-child {
        font-weight: 500;
    }
    
    /* ========== FILE UPLOADER ========== */
    [data-testid="stFileUploader"] {
        background-color: #f6f7f3;
        border: 2px dashed #49b156;
        border-radius: 5px;
        padding: 20px;
        transition: all 0.3s ease;
        margin: 9px 0;
    }
    
    [data-testid="stFileUploader"]:hover {
        border-color: #efd568;
        background-color: #fefdf8;
    }
    
    /* ========== PILLS/TAGS ========== */
    .stMultiSelect [data-baseweb="tag"] {
        background-color: #49b156 !important;
        color: white !important;
        border-radius: 15px !important;
        padding: 4px 8px !important;
        margin: 4px !important;
        font-weight: 500 !important;
        line-height: 15px !important;
    }
    
    .stMultiSelect [data-baseweb="tag"] svg {
        fill: white !important;
    }
    
    /* ========== DIVIDERS ========== */
    hr {
        border: none;
        border-top: 1px solid #abb6b6 !important;
        margin: 20px 0 !important;
    }
    
    /* ========== ALERT BOXES ========== */
    .stAlert {
        border-radius: 5px !important;
        border-left: 4px solid #efd568 !important;
        padding: 12px !important;
        margin: 9px 0 !important;
        background-color: #fefdf8 !important;
    }
    
    /* ========== CONTAINERS ========== */
    .element-container {
        margin-bottom: 9px;
    }
    
    /* Hide footer only */
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ========== 6. SESSION STATE INITIALIZATION ==========
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.legacy_spend_google = 0.0
    st.session_state.legacy_spend_ms = 0.0
    st.session_state.legacy_spend_mm = 0.0
    st.session_state.moa_spend_google = 0.0
    st.session_state.moa_spend_ms = 0.0
    st.session_state.moa_spend_mm = 0.0
    st.session_state.sb_csv_style = "Raw numbers"
    st.session_state.add_device_column = False

# ========== 7. MAIN CONTENT - HEADER ==========

# Banner with Melon Local colors and rounded design
st.markdown(
    """
    <div style='padding:1.5rem 2rem;border-radius:16px;margin-bottom:1.5rem;
                background: white;
                border:3px solid #47B74F;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                text-align:center;'>
        <span style='font-size:1.5em;font-weight:700;color:#114e38;'>🍈 Melon Local Lead Analyzer</span>
    </div>
    """, unsafe_allow_html=True
)

st.markdown("""
<div style='margin-bottom:2rem;'>
    <h1 style='color:#114e38;font-size:2.5rem;font-weight:700;margin:0;padding:0;border:none;display:block;'>
        Lead Analyzer — CPL by Platform and Product
    </h1>
    <p style='color:#47B74F;font-size:1.2rem;margin-top:0.5rem;font-weight:500;'>
        Fresh, local leads delivered daily — now with powerful analytics.
    </p>
</div>
""", unsafe_allow_html=True)

# ========== HELP DOCUMENTATION ==========
with st.expander("ℹ️ Help: How to Use This Analyzer", expanded=False):
    st.markdown("""
    ### 📂 Getting Started
    1. Upload CSV or Excel files for **Legacy** and/or **MOA** agencies
    2. Enter monthly spend amounts in the sidebar for each platform
    3. Use filters to focus on specific domains or devices
    
    ### 🎯 What You'll Get
    - **Platform CPL**: Cost per lead by Google, Microsoft, Melon Max
    - **Product Breakdown**: Performance by Auto, Home, Renters, Condo
    - **Device Analysis**: Mobile vs. Tablet vs. Desktop metrics
    - **Budget Optimizer**: AI-powered spend allocation recommendations
    
    ### 📊 Understanding the Data
    - **Leads (Total)** = Quote Starts + Phone Clicks + SMS Clicks
    - **Platform CPL** = Total Spend ÷ Total Leads
    - **TOTAL rows** exclude Listings (unless toggled off in sidebar)
    
    ### 🔧 Platform Classification Rules
    - **Melon Max**: Campaign IDs starting with "QS"
    - **Microsoft**: MLB/MLSB campaigns or Bing/Yahoo traffic
    - **Google**: MLG/MLSG campaigns or Google traffic
    - **Listings**: MLLIST campaigns
    
    ### 💡 Pro Tips
    - Use **Domain Filter** to focus on specific websites
    - Enable **Device Breakdown** for granular mobile/tablet/desktop insights
    - Try **Conservative Mode** in Budget Optimizer for safer spend recommendations
    - Export to Excel for deeper analysis in your preferred tool
    
    ### 📥 Export Options
    - **Excel**: Comprehensive report with all data tables
    - **CSV**: Individual tables for easy import elsewhere
    - **PNG**: Formatted tables as images for presentations
    """)

st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)

# ---------- Helper Functions ----------
def _norm(s):
    """Normalize string for column name matching."""
    return re.sub(r'[^a-z0-9]+', '_', str(s).strip().lower())


def get_col(df, aliases, default=None):
    """Find column in dataframe using list of aliases."""
    cols = {_norm(c): c for c in df.columns}
    for a in aliases:
        key = _norm(a)
        if key in cols:
            return cols[key]
        for k, v in cols.items():
            if key == k or key in k:
                return v
    return default


def detect_traffic_source_col(df):
    """Detect traffic source column from various possible names."""
    return get_col(df, [
        "traffic_source", "traffic source", "utm_source", "utm source",
        "network", "ad network", "publisher", "source", "channel"
    ])


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


def classify_product(campaign_id: str, landing_page: str, platform: str) -> str:
    """Classify insurance product type based on campaign ID and landing page."""
    s_id = (str(campaign_id) or "").upper()
    
    if platform == "Melon Max":
        if "QSA" in s_id:
            return "Auto"
        if "QSH" in s_id:
            return "Homeowners"
    
    s_lp = (str(landing_page) or "").lower()
    if "renters" in s_lp:
        return "Renters"
    if "quote" in s_lp or "auto" in s_lp:
        return "Auto"
    if "condo" in s_lp:
        return "Condo"
    if "homeowners" in s_lp:
        return "Homeowners"
    
    return "Other"


def choose_source_column(df):
    """Choose or construct a source column for grouping."""
    src = get_col(df, ["source"])
    if src:
        return src
    
    company = get_col(df, ["company_name", "company"])
    channel = get_col(df, ["media-channel", "media_channel", "channel"])
    
    if company and channel:
        df["_source_tmp"] = df[company].astype(str).fillna("") + " / " + df[channel].astype(str).fillna("")
        return "_source_tmp"
    if company:
        return company
    if channel:
        return channel
    
    cid = get_col(df, ["campaign_id", "campaign id", "campaign"])
    if cid:
        return cid
    
    df["_source_tmp"] = df.index.astype(str)
    return "_source_tmp"


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


@st.cache_data(show_spinner=False)
def pretty_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Convert column names to pretty, title-cased headers."""
    df = df.copy()
    df.columns = [re.sub(r"_+", " ", str(c)).strip().title() for c in df.columns]
    df.columns = [re.sub(r"\bSms\b", "SMS", c) for c in df.columns]
    df.rename(columns={"Cpl Platform": "Platform CPL", "Sms Clicks": "SMS Clicks"}, inplace=True)
    return df


def drop_effective_cost_basis(df: pd.DataFrame) -> pd.DataFrame:
    """Remove effective_cost_basis column if present."""
    cols = [c for c in df.columns if _norm(c) != "effective_cost_basis"]
    return df[cols].copy()


def is_currency_col(name: str) -> bool:
    """Check if column name indicates currency values."""
    n = name.lower()
    return any(tok in n for tok in ["spend", "cost", "cpl", "budget"])


def is_percent_col(name: str) -> bool:
    """Check if column name indicates percentage values."""
    n = name.lower()
    return "share" in n or n.endswith("%") or n.endswith("_pct") or n == "lead_share_within_platform"


def fmt_currency_series(s):
    """Format series as currency strings."""
    return pd.to_numeric(s, errors="coerce").apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")


def fmt_percent_series(s, places=1):
    """Format series as percentage strings."""
    return pd.to_numeric(s, errors="coerce").apply(lambda x: f"{x:.{places}f}%" if pd.notna(x) else "")


def hide_index_styler(df_png: pd.DataFrame):
    """Create a styler that hides the index for export."""
    sty = df_png.style
    try:
        sty = sty.hide(axis="index")
    except Exception:
        try:
            sty = sty.hide_index()
        except Exception:
            pass
    return sty


def prepare_df_for_png(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare dataframe for PNG export with formatting and 1-based index."""
    d = pretty_headers(df.copy())
    
    for col in d.columns:
        col_l = str(col).lower()
        if is_currency_col(col_l):
            d[col] = fmt_currency_series(d[col])
        elif is_percent_col(col_l):
            ser = pd.to_numeric(d[col], errors="coerce")
            if ser.fillna(0).gt(1).any():
                d[col] = ser.apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
            else:
                d[col] = ser.apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    
    d.index = np.arange(1, len(d) + 1)
    return d


def safe_sheet_name(name: str) -> str:
    """Sanitize sheet name for Excel (<=31 chars, no special chars)."""
    name = re.sub(r'[\[\]\:\*\?\/\\]', ' ', name)
    name = name.strip()
    return name[:31] if len(name) > 31 else name


def df_to_csv_bytes(df: pd.DataFrame, style: str = "raw") -> bytes:
    """Convert dataframe to CSV bytes with optional formatting."""
    if df is None or getattr(df, "empty", False):
        return b""
    
    if style == "raw":
        return df.to_csv(index=False).encode("utf-8")
    
    dff = df.copy()
    for col in dff.columns:
        col_l = str(col).lower()
        if is_currency_col(col_l):
            dff[col] = pd.to_numeric(dff[col], errors="coerce").apply(
                lambda x: f"${x:,.2f}" if pd.notna(x) else ""
            )
        elif is_percent_col(col_l):
            series = pd.to_numeric(dff[col], errors="coerce")
            if pd.notna(series).any() and (series.fillna(0).gt(1).any()):
                dff[col] = series.apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
            else:
                dff[col] = series.apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    
    return dff.to_csv(index=False).encode("utf-8")


def build_excel(sheets: dict):
    """Build Excel workbook with multiple sheets and formatting."""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine="xlsxwriter") as xw:
        wb = xw.book
        fmt_currency = wb.add_format({"num_format": "$#,##0.00"})
        fmt_percent = wb.add_format({"num_format": "0.0%"})
        fmt_bold_row = wb.add_format({"bold": True})
        
        for sheet_name, df in sheets.items():
            if df is None or getattr(df, "empty", False):
                continue
            
            sheet_name = safe_sheet_name(sheet_name)
            df = drop_effective_cost_basis(df)
            df = pretty_headers(df)
            df.to_excel(xw, sheet_name, index=False)
            
            ws = xw.sheets[sheet_name]
            
            # Auto-size columns and apply formatting
            for i, col in enumerate(df.columns):
                max_len = max(len(str(col)), *(df[col].astype(str).map(len).tolist() or [0])) + 2
                ws.set_column(i, i, min(max_len, 60))
                
                col_l = str(col).lower()
                if any(tok in col_l for tok in ["spend", "cost", "cpl", "budget"]):
                    ws.set_column(i, i, None, fmt_currency)
                if "share" in col_l or col_l.endswith("%") or col_l.endswith("_pct"):
                    ws.set_column(i, i, None, fmt_percent)
            
            # Bold TOTAL rows
            for key in ["Platform", "Product", "Agency"]:
                if key in df.columns:
                    total_rows = df.index[df[key].astype(str).str.upper() == "TOTAL"].tolist()
                    for r in total_rows:
                        ws.set_row(r + 1, None, fmt_bold_row)
    
    output.seek(0)
    return output


def extract_utm_from_campaign_id(campaign_id, tokens=UTM_TOKENS_FIXED):
    """
    Extract UTM token from campaign ID.
    
    For Melon Max campaigns:
    - AT, AM, AD (Auto + device) → "Auto"
    - HT, HM, HD (Home + device) → "Home"
    
    For other campaigns: returns the matched token as-is
    """
    s = str(campaign_id or "")
    low = s.lower()
    
    # Check for Melon Max Auto codes (AT, AM, AD)
    if any(code in s.upper() for code in ["AT", "AM", "AD"]):
        # Check if this is actually a Melon Max campaign (has QS)
        if "QS" in s.upper():
            return "Auto"
    
    # Check for Melon Max Home codes (HT, HM, HD)
    if any(code in s.upper() for code in ["HT", "HM", "HD"]):
        # Check if this is actually a Melon Max campaign (has QS)
        if "QS" in s.upper():
            return "Home"
    
    # For all other campaigns, use standard token matching
    for t in tokens:
        tt = str(t or "").strip()
        if not tt:
            continue
        if tt.lower() in low:
            return tt
    
    return ""


def display_table_with_total(df, total_identifier_col="platform", total_value="TOTAL", filters=None):
    """
    Display a dataframe with optional multi-column filtering and TOTAL row separated.
    
    Args:
        df: DataFrame to display
        total_identifier_col: Column name that contains the TOTAL marker
        total_value: Value that identifies the TOTAL row (default "TOTAL")
        filters: Dict of {column_name: unique_key} for columns to add filters for
                 e.g., {"platform": "leg_plat", "product": "leg_prod"}
    """
    if df is None or df.empty:
        st.info("No data available.")
        return
    
    df_display = df.copy()
    
    # Add filtering if requested
    if filters:
        filter_cols = st.columns(len(filters))
        
        for idx, (col_name, filter_key) in enumerate(filters.items()):
            if col_name in df.columns:
                # Get unique values (excluding TOTAL and empty/blank values)
                all_values = sorted([
                    x for x in df[col_name].dropna().unique() 
                    if str(x).upper() != total_value.upper() and str(x).strip() != ""
                ])
                
                if all_values:
                    with filter_cols[idx]:
                        selected = st.multiselect(
                            f"🔍 {col_name.title()}:",
                            options=all_values,
                            default=all_values,
                            key=filter_key
                        )
                        
                        # Apply filter (but keep TOTAL row)
                        if selected:
                            df_display = df_display[
                                df_display[col_name].isin(selected) | 
                                (df_display[total_identifier_col].astype(str).str.upper() == total_value.upper())
                            ]
                        else:
                            # If nothing selected, show only TOTAL
                            df_display = df_display[
                                df_display[total_identifier_col].astype(str).str.upper() == total_value.upper()
                            ]
    
    df_pretty = pretty_headers(df_display)
    
    # Find the column name after pretty_headers transformation
    total_col_pretty = None
    for col in df_pretty.columns:
        if _norm(col) == _norm(total_identifier_col):
            total_col_pretty = col
            break
    
    if total_col_pretty and total_col_pretty in df_pretty.columns:
        # Check if there's a TOTAL row
        mask = df_pretty[total_col_pretty].astype(str).str.upper() == total_value.upper()
        if mask.any():
            # Split into data and total
            df_data = df_pretty[~mask].copy()
            df_total = df_pretty[mask].copy()
            
            # Display data table (sortable)
            if not df_data.empty:
                st.dataframe(df_data, use_container_width=True, hide_index=True)
            else:
                st.info("No data matches the selected filters.")
            
            # Display total row (non-sortable, styled differently)
            st.markdown("**Total:**")
            st.dataframe(df_total, use_container_width=True, hide_index=True)
            return
    
    # Fallback: display as-is if no TOTAL row found
    st.dataframe(df_pretty, use_container_width=True, hide_index=True)


# ---------- Core Analysis Function ----------
@st.cache_data(show_spinner=False, hash_funcs={dict: lambda d: str(sorted(d.items()))})
def analyze(df, spends_input, spend_column=None, hide_unknown=False, add_device_column=False, exclude_listings_from_totals=False):
    """
    Analyze lead data and compute metrics by platform, product, agency, and source.
    
    Args:
        df: Input dataframe with lead data
        spends_input: Dict of {agency: {platform: spend_float}}
        spend_column: Optional column name for spend data in df
        hide_unknown: Whether to filter out "Unknown" platform
        add_device_column: Whether to add device as a grouping column in aggregations
        exclude_listings_from_totals: Whether to exclude Listings from TOTAL row calculations
        
    Returns:
        Dict of result dataframes
    """
    # Detect columns
    col_campaign = get_col(df, ["campaign_id", "campaign id", "campaign"])
    col_landing = get_col(df, ["landing_page", "landing page", "final url", "url", "path"])
    col_domain = get_col(df, ["domain", "site", "hostname"])
    col_qs = get_col(df, ["quote_starts", "quote start", "qs", "quotes", "quote starts"])
    col_phone = get_col(df, ["phone_clicks", "phone clicks", "phone", "calls"])
    col_sms = get_col(df, ["sms_clicks", "sms clicks", "sms", "text clicks"])
    col_traffic = detect_traffic_source_col(df)

    # Create default columns if missing
    to_num = lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0)
    
    if col_qs is None:
        df["_qs"] = 0.0
        col_qs = "_qs"
    if col_phone is None:
        df["_phone"] = 0.0
        col_phone = "_phone"
    if col_sms is None:
        df["_sms"] = 0.0
        col_sms = "_sms"
    
    df[col_qs] = to_num(df[col_qs])
    df[col_phone] = to_num(df[col_phone])
    df[col_sms] = to_num(df[col_sms])

    if col_campaign is None:
        df["_cid"] = ""
        col_campaign = "_cid"
    if col_landing is None:
        df["_lp"] = ""
        col_landing = "_lp"
    if col_domain is None:
        df["_dm"] = ""
        col_domain = "_dm"
    if col_traffic is None:
        df["_ts"] = ""
        col_traffic = "_ts"

    # Classify platform and product
    df["platform"] = df.apply(lambda r: classify_platform(r[col_campaign], r[col_traffic]), axis=1)
    df["domain"] = df[col_domain].astype(str)
    df["product"] = df.apply(lambda r: classify_product(r[col_campaign], r[col_landing], r["platform"]), axis=1)
    
    # Classify device based on campaign ID patterns
    df["device"] = df.apply(lambda r: classify_device(r[col_campaign], r["platform"]), axis=1)

    if hide_unknown:
        df = df[df["platform"] != "Unknown"].copy()

    col_source = choose_source_column(df)
    df["source"] = df[col_source].astype(str)
    df["lead_opportunities"] = df[col_qs] + df[col_phone] + df[col_sms]

    # Optional spend column
    spend_col = None
    if spend_column:
        c = get_col(df, [spend_column])
        if c:
            spend_col = c
            df[spend_col] = pd.to_numeric(df[spend_col], errors="coerce").fillna(0.0)

    # Helper: platform spend overall (sum per agency or from CSV if provided)
    def platform_spend_overall(platform):
        if spend_col:
            v = df.loc[df["platform"] == platform, spend_col].sum()
            if v and v > 0:
                return float(v)
        # sum manual spends from all agencies
        total = 0.0
        for ag in spends_input:
            spend_val = float(spends_input.get(ag, {}).get(platform, 0.0))
            total += spend_val
        return total

    # Helper: platform spend for (platform, agency)
    def platform_spend_by_agency(platform, agency):
        if spend_col:
            v = df.loc[(df["platform"] == platform) & (df["agency"] == agency), spend_col].sum()
            if v and v > 0:
                return float(v)
        return float(spends_input.get(agency, {}).get(platform, 0.0))

    # ---------- Aggregate by Platform ----------
    # Conditionally add device column to groupby
    group_cols = ["device", "platform"] if add_device_column else ["platform"]
    
    plat = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        leads=("lead_opportunities", "sum")
    )
    
    # Calculate spend
    if add_device_column:
        # When device breakdown is enabled, distribute spend proportionally by leads within each platform
        # First get total spend per platform
        platform_totals = {}
        for platform in plat["platform"].unique():
            platform_totals[platform] = platform_spend_overall(platform)
        
        # Then distribute proportionally based on leads
        def calc_device_spend(row):
            platform = row["platform"]
            total_spend = platform_totals[platform]
            # Get total leads for this platform across all devices
            platform_leads = plat[plat["platform"] == platform]["leads"].sum()
            if platform_leads > 0:
                # Distribute spend proportionally
                return (row["leads"] / platform_leads) * total_spend
            return 0.0
        
        plat["spend"] = plat.apply(calc_device_spend, axis=1)
    else:
        # No device breakdown - simple platform spend
        plat["spend"] = plat["platform"].apply(platform_spend_overall)
    
    plat["cpl_platform"] = np.where(plat["leads"] > 0, plat["spend"] / plat["leads"], np.nan)
    
    # Filter out rows where all metrics are zero AND spend is zero
    # Keep rows with spend even if they have no leads yet
    plat = plat[
        (plat["quote_starts"] > 0) | 
        (plat["phone_clicks"] > 0) | 
        (plat["sms_clicks"] > 0) | 
        (plat["leads"] > 0) |
        (plat["spend"] > 0)
    ].reset_index(drop=True)
    
    # Add platforms with budget but no data yet
    # Get all platforms that have spend but aren't in the aggregated data
    all_platforms_with_spend = set()
    for agency_spends in spends_input.values():
        for platform, spend in agency_spends.items():
            if spend > 0:
                all_platforms_with_spend.add(platform)
    
    existing_platforms = set(plat["platform"].unique())
    missing_platforms = all_platforms_with_spend - existing_platforms
    
    if missing_platforms:
        # Add rows for platforms with budget but no data
        missing_rows = []
        for platform in missing_platforms:
            if add_device_column:
                # Add a single row with empty device for platforms with no data
                missing_rows.append({
                    "device": "",
                    "platform": platform,
                    "quote_starts": 0,
                    "phone_clicks": 0,
                    "sms_clicks": 0,
                    "leads": 0,
                    "spend": platform_spend_overall(platform),
                    "cpl_platform": np.nan
                })
            else:
                missing_rows.append({
                    "platform": platform,
                    "quote_starts": 0,
                    "phone_clicks": 0,
                    "sms_clicks": 0,
                    "leads": 0,
                    "spend": platform_spend_overall(platform),
                    "cpl_platform": np.nan
                })
        
        if missing_rows:
            plat = pd.concat([plat, pd.DataFrame(missing_rows)], ignore_index=True)
    
    # Build TOTAL row
    # Optionally exclude Listings from totals
    plat_for_totals = plat[plat["platform"] != "Listings"].copy() if exclude_listings_from_totals else plat.copy()
    
    totals_plat = {
        "platform": "TOTAL",
        "quote_starts": plat_for_totals["quote_starts"].sum(),
        "phone_clicks": plat_for_totals["phone_clicks"].sum(),
        "sms_clicks": plat_for_totals["sms_clicks"].sum(),
        "leads": plat_for_totals["leads"].sum(),
        "spend": plat_for_totals["spend"].sum(),
    }
    if add_device_column:
        totals_plat["device"] = ""  # Empty for TOTAL row
    tot_leads = totals_plat["leads"]
    totals_plat["cpl_platform"] = (totals_plat["spend"] / tot_leads) if tot_leads > 0 else np.nan
    plat_out = pd.concat([plat, pd.DataFrame([totals_plat])], ignore_index=True)

    # ---------- Aggregate by Product ----------
    group_cols = ["device", "product"] if add_device_column else ["product"]
    
    prod_tot = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        leads=("lead_opportunities", "sum")
    ).sort_values("leads", ascending=False).reset_index(drop=True)
    
    # Filter out rows where all metrics are zero
    prod_tot = prod_tot[
        (prod_tot["quote_starts"] > 0) | 
        (prod_tot["phone_clicks"] > 0) | 
        (prod_tot["sms_clicks"] > 0) | 
        (prod_tot["leads"] > 0)
    ].reset_index(drop=True)
    
    # For TOTAL row, use dataframe filtered to exclude Listings if option is enabled
    if exclude_listings_from_totals:
        df_for_prod_totals = df[df["platform"] != "Listings"].copy()
        prod_for_totals = df_for_prod_totals.groupby(group_cols, as_index=False).agg(
            quote_starts=(col_qs, "sum"),
            phone_clicks=(col_phone, "sum"),
            sms_clicks=(col_sms, "sum"),
            leads=("lead_opportunities", "sum")
        )
    else:
        prod_for_totals = prod_tot.copy()
    
    totals_prod = {
        "product": "TOTAL",
        "quote_starts": prod_for_totals["quote_starts"].sum(),
        "phone_clicks": prod_for_totals["phone_clicks"].sum(),
        "sms_clicks": prod_for_totals["sms_clicks"].sum(),
        "leads": prod_for_totals["leads"].sum()
    }
    if add_device_column:
        totals_prod["device"] = ""
    prod_tot_out = pd.concat([prod_tot, pd.DataFrame([totals_prod])], ignore_index=True)

    # ---------- Aggregate by Product × Platform ----------
    group_cols = ["device", "platform", "product"] if add_device_column else ["platform", "product"]
    
    prod_grp = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        lead_opportunities=("lead_opportunities", "sum")
    )
    
    # Filter out rows where all metrics are zero
    prod_grp = prod_grp[
        (prod_grp["quote_starts"] > 0) | 
        (prod_grp["phone_clicks"] > 0) | 
        (prod_grp["sms_clicks"] > 0) | 
        (prod_grp["lead_opportunities"] > 0)
    ].reset_index(drop=True)
    
    groupby_cols = ["device", "platform"] if add_device_column else ["platform"]
    prod_grp["lead_share_within_platform"] = (
        prod_grp.groupby(groupby_cols)["lead_opportunities"].transform(lambda s: s / s.sum() if s.sum() > 0 else 0)
    )

    # ---------- Aggregate by Device (if available) ----------
    device_overview = None
    if "device" in df.columns:
        device_overview = df.groupby("device", as_index=False).agg(
            quote_starts=(col_qs, "sum"),
            phone_clicks=(col_phone, "sum"),
            sms_clicks=(col_sms, "sum"),
            leads=("lead_opportunities", "sum")
        ).sort_values("leads", ascending=False).reset_index(drop=True)
        
        # Filter out zero rows
        device_overview = device_overview[
            (device_overview["quote_starts"] > 0) | 
            (device_overview["phone_clicks"] > 0) | 
            (device_overview["sms_clicks"] > 0) | 
            (device_overview["leads"] > 0)
        ].reset_index(drop=True)
        
        # Add TOTAL row
        if not device_overview.empty:
            totals_device = {
                "device": "TOTAL",
                "quote_starts": device_overview["quote_starts"].sum(),
                "phone_clicks": device_overview["phone_clicks"].sum(),
                "sms_clicks": device_overview["sms_clicks"].sum(),
                "leads": device_overview["leads"].sum()
            }
            device_overview = pd.concat([device_overview, pd.DataFrame([totals_device])], ignore_index=True)
    
    # ---------- Aggregate by Device × Platform (if available) ----------
    device_platform = None
    if "device" in df.columns:
        device_platform = df.groupby(["device", "platform"], as_index=False).agg(
            quote_starts=(col_qs, "sum"),
            phone_clicks=(col_phone, "sum"),
            sms_clicks=(col_sms, "sum"),
            leads=("lead_opportunities", "sum")
        ).sort_values("leads", ascending=False).reset_index(drop=True)
        
        # Filter out zero rows
        device_platform = device_platform[
            (device_platform["quote_starts"] > 0) | 
            (device_platform["phone_clicks"] > 0) | 
            (device_platform["sms_clicks"] > 0) | 
            (device_platform["leads"] > 0)
        ].reset_index(drop=True)

    # ---------- Aggregate by Source ----------
    group_cols = ["device", "source", "domain", "platform", "agency"] if add_device_column else ["source", "domain", "platform", "agency"]
    
    src_grp = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        lead_opportunities=("lead_opportunities", "sum")
    )
    
    # Filter out rows where all metrics are zero
    src_grp = src_grp[
        (src_grp["quote_starts"] > 0) | 
        (src_grp["phone_clicks"] > 0) | 
        (src_grp["sms_clicks"] > 0) | 
        (src_grp["lead_opportunities"] > 0)
    ].reset_index(drop=True)

    # ---------- Aggregate by Agency ----------
    group_cols = ["device", "agency"] if add_device_column else ["agency"]
    
    agency_overview = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        leads=("lead_opportunities", "sum")
    ).sort_values("leads", ascending=False).reset_index(drop=True)
    
    # Filter out rows where all metrics are zero
    agency_overview = agency_overview[
        (agency_overview["quote_starts"] > 0) | 
        (agency_overview["phone_clicks"] > 0) | 
        (agency_overview["sms_clicks"] > 0) | 
        (agency_overview["leads"] > 0)
    ].reset_index(drop=True)
    
    # For TOTAL row, use dataframe filtered to exclude Listings if option is enabled
    if exclude_listings_from_totals:
        df_for_agency_totals = df[df["platform"] != "Listings"].copy()
        agency_for_totals = df_for_agency_totals.groupby(group_cols, as_index=False).agg(
            quote_starts=(col_qs, "sum"),
            phone_clicks=(col_phone, "sum"),
            sms_clicks=(col_sms, "sum"),
            leads=("lead_opportunities", "sum")
        )
    else:
        agency_for_totals = agency_overview.copy()
    
    totals_ag = {
        "agency": "TOTAL",
        "quote_starts": agency_for_totals["quote_starts"].sum(),
        "phone_clicks": agency_for_totals["phone_clicks"].sum(),
        "sms_clicks": agency_for_totals["sms_clicks"].sum(),
        "leads": agency_for_totals["leads"].sum()
    }
    if add_device_column:
        totals_ag["device"] = ""
    agency_overview_out = pd.concat([agency_overview, pd.DataFrame([totals_ag])], ignore_index=True)

    # ---------- Aggregate by Platform × Agency ----------
    group_cols = ["device", "platform", "agency"] if add_device_column else ["platform", "agency"]
    
    plat_agency = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        leads=("lead_opportunities", "sum")
    )
    
    # Calculate spend first before filtering
    if add_device_column:
        # Distribute spend proportionally by leads within each platform-agency combination
        platform_agency_totals = {}
        for _, row in plat_agency.iterrows():
            key = (row["platform"], row["agency"])
            if key not in platform_agency_totals:
                platform_agency_totals[key] = platform_spend_by_agency(row["platform"], row["agency"])
        
        def calc_device_agency_spend(row):
            key = (row["platform"], row["agency"])
            total_spend = platform_agency_totals[key]
            # Get total leads for this platform-agency combo across all devices
            platform_agency_leads = plat_agency[
                (plat_agency["platform"] == row["platform"]) & 
                (plat_agency["agency"] == row["agency"])
            ]["leads"].sum()
            if platform_agency_leads > 0:
                return (row["leads"] / platform_agency_leads) * total_spend
            return 0.0
        
        plat_agency["spend"] = plat_agency.apply(calc_device_agency_spend, axis=1)
    else:
        # No device breakdown
        plat_agency["spend"] = plat_agency.apply(
            lambda r: platform_spend_by_agency(r["platform"], r["agency"]), axis=1
        )
    
    plat_agency["cpl_platform"] = np.where(
        plat_agency["leads"] > 0, 
        plat_agency["spend"] / plat_agency["leads"], 
        np.nan
    )
    
    # Filter out rows where all metrics AND spend are zero
    plat_agency = plat_agency[
        (plat_agency["quote_starts"] > 0) | 
        (plat_agency["phone_clicks"] > 0) | 
        (plat_agency["sms_clicks"] > 0) | 
        (plat_agency["leads"] > 0) |
        (plat_agency["spend"] > 0)
    ].reset_index(drop=True)
    
    # Add platform-agency combinations with budget but no data yet
    existing_combos = set(zip(plat_agency["platform"], plat_agency["agency"]))
    missing_rows = []
    
    for agency, agency_spends in spends_input.items():
        for platform, spend in agency_spends.items():
            if spend > 0 and (platform, agency) not in existing_combos:
                if add_device_column:
                    missing_rows.append({
                        "device": "",
                        "platform": platform,
                        "agency": agency,
                        "quote_starts": 0,
                        "phone_clicks": 0,
                        "sms_clicks": 0,
                        "leads": 0,
                        "spend": spend,
                        "cpl_platform": np.nan
                    })
                else:
                    missing_rows.append({
                        "platform": platform,
                        "agency": agency,
                        "quote_starts": 0,
                        "phone_clicks": 0,
                        "sms_clicks": 0,
                        "leads": 0,
                        "spend": spend,
                        "cpl_platform": np.nan
                    })
    
    if missing_rows:
        plat_agency = pd.concat([plat_agency, pd.DataFrame(missing_rows)], ignore_index=True)
    
    groupby_cols = ["device", "platform"] if add_device_column else ["platform"]
    totals_pa = plat_agency.groupby(groupby_cols, as_index=False).agg(
        quote_starts=("quote_starts", "sum"),
        phone_clicks=("phone_clicks", "sum"),
        sms_clicks=("sms_clicks", "sum"),
        leads=("leads", "sum"),
        spend=("spend", "sum")
    )
    totals_pa["cpl_platform"] = np.where(
        totals_pa["leads"] > 0, 
        totals_pa["spend"] / totals_pa["leads"], 
        np.nan
    )
    totals_pa["agency"] = "TOTAL"
    
    plat_agency_out = pd.concat([
        plat_agency, 
        totals_pa[["platform", "agency", "quote_starts", "phone_clicks", "sms_clicks", "leads", "spend", "cpl_platform"]]
    ], ignore_index=True)

    # ---------- Aggregate by Product × Platform × Agency ----------
    group_cols = ["device", "product", "platform", "agency"] if add_device_column else ["product", "platform", "agency"]
    
    prod_plat_agency = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        leads=("lead_opportunities", "sum")
    )
    
    # Filter out rows where all metrics are zero
    prod_plat_agency = prod_plat_agency[
        (prod_plat_agency["quote_starts"] > 0) | 
        (prod_plat_agency["phone_clicks"] > 0) | 
        (prod_plat_agency["sms_clicks"] > 0) | 
        (prod_plat_agency["leads"] > 0)
    ].reset_index(drop=True)
    
    groupby_cols = ["device", "platform", "agency"] if add_device_column else ["platform", "agency"]
    prod_plat_agency["lead_share_within_platform_agency"] = (
        prod_plat_agency.groupby(groupby_cols)["leads"].transform(
            lambda s: s / s.sum() if s.sum() > 0 else 0
        )
    )

    # ---------- Aggregate by Product × Agency ----------
    group_cols = ["device", "product", "agency"] if add_device_column else ["product", "agency"]
    
    prod_agency = df.groupby(group_cols, as_index=False).agg(
        quote_starts=(col_qs, "sum"),
        phone_clicks=(col_phone, "sum"),
        sms_clicks=(col_sms, "sum"),
        leads=("lead_opportunities", "sum")
    )
    
    # Filter out rows where all metrics are zero
    prod_agency = prod_agency[
        (prod_agency["quote_starts"] > 0) | 
        (prod_agency["phone_clicks"] > 0) | 
        (prod_agency["sms_clicks"] > 0) | 
        (prod_agency["leads"] > 0)
    ].reset_index(drop=True)

    # ---------- Aggregate UTM Overview (Combined) ----------
    utm_overview = None
    if col_campaign:
        df_utm = df.copy()
        df_utm["utm"] = df_utm[col_campaign].apply(extract_utm_from_campaign_id)
        df_utm["utm"] = df_utm["utm"].replace("", "Unmatched")
        
        group_cols = ["device", "platform", "utm"] if add_device_column else ["platform", "utm"]
        
        utm_overview = df_utm.groupby(group_cols, as_index=False).agg(
            quote_starts=(col_qs, "sum"),
            phone_clicks=(col_phone, "sum"),
            sms_clicks=(col_sms, "sum"),
            leads=("lead_opportunities", "sum")
        ).sort_values(["platform", "leads", "utm"], ascending=[True, False, True]).reset_index(drop=True)
        
        # Filter out rows where all metrics are zero
        utm_overview = utm_overview[
            (utm_overview["quote_starts"] > 0) | 
            (utm_overview["phone_clicks"] > 0) | 
            (utm_overview["sms_clicks"] > 0) | 
            (utm_overview["leads"] > 0)
        ].reset_index(drop=True)
        
        # Add TOTAL row
        totals_utm = {
            "platform": "",
            "utm": "TOTAL",
            "quote_starts": utm_overview["quote_starts"].sum(),
            "phone_clicks": utm_overview["phone_clicks"].sum(),
            "sms_clicks": utm_overview["sms_clicks"].sum(),
            "leads": utm_overview["leads"].sum()
        }
        if add_device_column:
            totals_utm["device"] = ""
        utm_overview = pd.concat([utm_overview, pd.DataFrame([totals_utm])], ignore_index=True)

    return {
        "platform_overview": plat_out,
        "by_product_total": prod_tot_out,
        "by_product_platform": prod_grp,
        "by_source": src_grp,
        "agency_overview": agency_overview_out,
        "platform_agency": plat_agency_out,
        "product_platform_agency": prod_plat_agency,
        "product_agency": prod_agency,
        "utm_overview": utm_overview,
        "device_overview": device_overview,
        "device_platform": device_platform
    }


# ---------- Sidebar Configuration ----------
with st.sidebar:
    # Melon Local logo text
    st.markdown("""
    <div style='text-align:center;padding:1rem 0;margin-bottom:1rem;'>
        <div style='font-size:2em;'>🍈</div>
        <div style='font-size:1.3em;font-weight:700;color:#F1CB20;'>melon local</div>
        <div style='font-size:0.9em;opacity:0.8;'>Lead Analyzer</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.header("💰 Budget Inputs")
    
    st.markdown("**Legacy**")
    legacy_google = st.number_input("Legacy — Google Spend", value=0.0, min_value=0.0, step=100.0, format="%.2f", key="legacy_spend_google", help="Monthly ad spend for Legacy agency on Google Ads")
    legacy_ms = st.number_input("Legacy — Microsoft Spend", value=0.0, min_value=0.0, step=100.0, format="%.2f", key="legacy_spend_ms", help="Monthly ad spend for Legacy agency on Microsoft Ads")
    legacy_mm = st.number_input("Legacy — Melon Max Spend", value=0.0, min_value=0.0, step=100.0, format="%.2f", key="legacy_spend_mm", help="Monthly ad spend for Legacy agency on Melon Max")
    
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    
    st.markdown("**MOA**")
    moa_google = st.number_input("MOA — Google Spend", value=0.0, min_value=0.0, step=100.0, format="%.2f", key="moa_spend_google", help="Monthly ad spend for MOA agency on Google Ads")
    moa_ms = st.number_input("MOA — Microsoft Spend", value=0.0, min_value=0.0, step=100.0, format="%.2f", key="moa_spend_ms", help="Monthly ad spend for MOA agency on Microsoft Ads")
    moa_mm = st.number_input("MOA — Melon Max Spend", value=0.0, min_value=0.0, step=100.0, format="%.2f", key="moa_spend_mm", help="Monthly ad spend for MOA agency on Melon Max")

    st.markdown("---")
    spend_col = st.text_input("Optional spend column name (in uploads)", placeholder="e.g., Spend, Cost", key="sb_spend_col")
    csv_style = st.radio("CSV number style", options=["Raw numbers", "With $ and % symbols"], index=0, key="sb_csv_style")
    hide_unknown = st.checkbox("Hide 'Unknown' platform", False, key="gf_hide_unknown")
    exclude_listings_from_totals = st.checkbox(
        "Exclude 'Listings' from TOTAL rows",
        False,
        key="exclude_listings_totals",
        help="When enabled, Listings will still appear in tables but won't be included in TOTAL row calculations"
    )


# ---------- File Upload ----------
c1, c2 = st.columns(2)
with c1:
    up_legacy = st.file_uploader("Upload Legacy file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="upload_legacy")
with c2:
    up_moa = st.file_uploader("Upload MOA file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="upload_moa")


@st.cache_data(show_spinner="📂 Loading file...")
def load_uploaded(file):
    """Load uploaded CSV or Excel file with caching."""
    suffix = pathlib.Path(file.name).suffix.lower()
    
    if suffix == ".csv":
        return pd.read_csv(file)
    elif suffix in (".xlsx", ".xls"):
        if not EXCEL_OK:
            st.error("Excel support requires the 'openpyxl' package. Please install it or upload a CSV.")
            return None
        try:
            return pd.read_excel(file, engine="openpyxl")
        except Exception as e:
            st.error(f"Could not read Excel file: {e}")
            return None
    else:
        st.error("Unsupported file type.")
        return None


# ---------- Main Processing ----------
dfs = []
if up_legacy:
    df_legacy = load_uploaded(up_legacy)
    if df_legacy is not None:
        df_legacy = df_legacy.copy()
        df_legacy["agency"] = "Legacy"
        dfs.append(df_legacy)

if up_moa:
    df_moa = load_uploaded(up_moa)
    if df_moa is not None:
        df_moa = df_moa.copy()
        df_moa["agency"] = "MOA"
        dfs.append(df_moa)

if not dfs:
    st.info("Upload at least one file (Legacy or MOA) to begin.")
else:
    df_in = pd.concat(dfs, ignore_index=True)

    # Sidebar Filters
    with st.sidebar:
        st.markdown("---")
        st.subheader("Filters")
        
        # Domain filter
        domain_col = get_col(df_in, ["domain", "site", "hostname"])
        if domain_col:
            all_domains = sorted([str(x) for x in df_in[domain_col].dropna().unique()])
            sel_domains = st.multiselect("Filter by domain:", options=all_domains, default=all_domains, key="flt_domains")
        else:
            sel_domains = []
            st.info("No 'Domain' column found in uploads.")
        
        # Device breakdown toggle
        st.markdown("---")
        st.markdown("**Device Breakdown:**")
        add_device_column = st.checkbox(
            "📱 Add device column to all tables",
            value=False,
            key="add_device_column",
            help="When enabled, adds a 'Device' column (Mobile/Tablet/Desktop) to all aggregation tables."
        )

    # Apply domain filter (but preserve all Listings data regardless of domain filter)
    if domain_col and sel_domains:
        # Classify platform first so we can preserve Listings
        df_in_temp = df_in.copy()
        
        # Temporarily classify platforms to identify Listings
        col_campaign_temp = get_col(df_in_temp, ["campaign_id", "campaign id", "campaign"])
        col_traffic_temp = detect_traffic_source_col(df_in_temp)
        
        if col_campaign_temp:
            df_in_temp["_platform_temp"] = df_in_temp.apply(
                lambda r: classify_platform(
                    r[col_campaign_temp], 
                    r[col_traffic_temp] if col_traffic_temp else ""
                ), 
                axis=1
            )
        else:
            df_in_temp["_platform_temp"] = "Unknown"
        
        # Apply domain filter to non-Listings data only
        filtered_df = df_in_temp[df_in_temp[domain_col].astype(str).isin(sel_domains)].copy()
        
        # Get all Listings data (regardless of domain)
        listings_df = df_in_temp[df_in_temp["_platform_temp"] == "Listings"].copy()
        
        # Combine filtered data with all Listings data
        df_in = pd.concat([filtered_df, listings_df], ignore_index=True).drop_duplicates()
        
        # Remove temporary column
        if "_platform_temp" in df_in.columns:
            df_in = df_in.drop(columns=["_platform_temp"])

    # Prepare per-agency spend dict
    spends = {
        "Legacy": {"Google": legacy_google, "Microsoft": legacy_ms, "Melon Max": legacy_mm},
        "MOA": {"Google": moa_google, "Microsoft": moa_ms, "Melon Max": moa_mm},
    }
    
    # Debug: Show spend inputs
    if add_device_column:
        st.info(f"💰 Spend inputs - Legacy: Google=${legacy_google}, MS=${legacy_ms}, MM=${legacy_mm} | MOA: Google=${moa_google}, MS=${moa_ms}, MM=${moa_mm}")

    # Enhanced loading with progress feedback
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("📂 Loading data...")
        progress_bar.progress(20)
        time.sleep(0.3)
        
        status_text.text("🔍 Classifying platforms...")
        progress_bar.progress(40)
        time.sleep(0.2)
        
        status_text.text("📊 Computing CPL metrics...")
        progress_bar.progress(60)
        
        results = analyze(
            df_in.copy(),
            spends_input=spends,
            spend_column=spend_col.strip() or None,
            hide_unknown=hide_unknown,
            add_device_column=add_device_column,
            exclude_listings_from_totals=exclude_listings_from_totals
        )
        
        status_text.text("📈 Aggregating results...")
        progress_bar.progress(90)
        time.sleep(0.2)
        
        status_text.text("✅ Analysis complete!")
        progress_bar.progress(100)
        time.sleep(0.5)
        
    finally:
        # Clean up progress indicators
        progress_bar.empty()
        status_text.empty()


    # ---------- AGENCY-SPECIFIC SECTIONS ----------
    has_legacy_file = up_legacy is not None
    has_moa_file = up_moa is not None

    for agency_name in ["Legacy", "MOA"]:
        ag_mask = df_in.get("agency", "") == agency_name
        ag_has_rows = ag_mask.any()
        # Determine default expansion: expand if this agency file was uploaded
        default_expanded = has_legacy_file if agency_name == "Legacy" else has_moa_file

        with st.expander(f"{agency_name} — Overview", expanded=bool(default_expanded)):
            if not ag_has_rows:
                st.info(f"No data uploaded for {agency_name}.")
                continue

            sub_df = df_in[ag_mask].copy()
            sub_spends = {agency_name: spends[agency_name]}
            single = analyze(sub_df, sub_spends, spend_column=spend_col.strip() or None, hide_unknown=hide_unknown, add_device_column=add_device_column, exclude_listings_from_totals=exclude_listings_from_totals)
            
            # Platform Overview
            with st.expander(f"{agency_name}: Platform Overview (Platform CPL + TOTAL)", expanded=True):
                plat = single["platform_overview"].copy()
                
                # Add charts
                if PLOTLY_AVAILABLE:
                    plat_chart = plat[plat["platform"] != "TOTAL"].copy()
                    
                    if not plat_chart.empty:
                        # Chart controls
                        chart_col1, chart_col2, chart_col3 = st.columns([2, 2, 2])
                        
                        with chart_col1:
                            chart_type = st.selectbox(
                                "Chart Type:",
                                options=["Bar", "Line", "Area"],
                                key=f"{agency_name}_plat_chart_type"
                            )
                        
                        with chart_col2:
                            metric_to_show = st.selectbox(
                                "Metric:",
                                options=["Leads (Total)", "Quote Starts", "Phone Clicks", "SMS Clicks", "CPL"],
                                key=f"{agency_name}_plat_metric"
                            )
                        
                        with chart_col3:
                            show_values = st.checkbox(
                                "Show Values",
                                value=True,
                                key=f"{agency_name}_plat_show_values"
                            )
                        
                        # Map metric selection to column name
                        metric_map = {
                            "Leads (Total)": "leads",
                            "Quote Starts": "quote_starts",
                            "Phone Clicks": "phone_clicks",
                            "SMS Clicks": "sms_clicks",
                            "CPL": "cpl_platform"
                        }
                        
                        metric_col = metric_map[metric_to_show]
                        
                        # Device breakdown chart (when device column exists)
                        if "device" in plat_chart.columns:
                            # Prepare data
                            chart_data = plat_chart.copy()
                            if metric_col == "cpl_platform":
                                chart_data[metric_col] = pd.to_numeric(chart_data[metric_col], errors="coerce")
                                chart_data = chart_data[chart_data[metric_col] > 0]
                            
                            # Create chart based on type
                            if chart_type == "Bar":
                                fig = px.bar(
                                    chart_data,
                                    x="platform",
                                    y=metric_col,
                                    color="device",
                                    title=f"{agency_name}: {metric_to_show} by Platform & Device",
                                    labels={"platform": "Platform", metric_col: metric_to_show, "device": "Device"},
                                    color_discrete_map={
                                        "Mobile": "#49b156",
                                        "Desktop": "#0f5340",
                                        "Tablet": "#efd568",
                                        "Unknown": "#cccccc"
                                    },
                                    text=metric_col if show_values else None,
                                    barmode="group"
                                )
                            elif chart_type == "Line":
                                fig = px.line(
                                    chart_data,
                                    x="platform",
                                    y=metric_col,
                                    color="device",
                                    title=f"{agency_name}: {metric_to_show} by Platform & Device",
                                    labels={"platform": "Platform", metric_col: metric_to_show, "device": "Device"},
                                    color_discrete_map={
                                        "Mobile": "#49b156",
                                        "Desktop": "#0f5340",
                                        "Tablet": "#efd568",
                                        "Unknown": "#cccccc"
                                    },
                                    markers=True
                                )
                            else:  # Area
                                fig = px.area(
                                    chart_data,
                                    x="platform",
                                    y=metric_col,
                                    color="device",
                                    title=f"{agency_name}: {metric_to_show} by Platform & Device",
                                    labels={"platform": "Platform", metric_col: metric_to_show, "device": "Device"},
                                    color_discrete_map={
                                        "Mobile": "#49b156",
                                        "Desktop": "#0f5340",
                                        "Tablet": "#efd568",
                                        "Unknown": "#cccccc"
                                    }
                                )
                            
                            if show_values and chart_type == "Bar":
                                if metric_col == "cpl_platform":
                                    fig.update_traces(texttemplate='$%{text:.2f}', textposition='outside')
                                else:
                                    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                            
                            fig.update_layout(
                                height=400,
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            st.markdown("---")
                        else:
                            # Regular platform charts (when device breakdown is OFF)
                            plat_agg = plat_chart.copy()
                            
                            # Prepare data based on metric
                            if metric_col == "cpl_platform":
                                plat_agg[metric_col] = pd.to_numeric(plat_agg[metric_col], errors="coerce")
                                plat_agg = plat_agg[plat_agg[metric_col] > 0]
                            
                            # Create chart based on type
                            if chart_type == "Bar":
                                fig = px.bar(
                                    plat_agg,
                                    x="platform",
                                    y=metric_col,
                                    title=f"{agency_name}: {metric_to_show} by Platform",
                                    labels={"platform": "Platform", metric_col: metric_to_show},
                                    color=metric_col,
                                    color_continuous_scale=["#eef7ef", "#49b156"] if metric_col != "cpl_platform" else ["#49b156", "#efd568", "#f28c82"],
                                    text=metric_col if show_values else None
                                )
                            elif chart_type == "Line":
                                fig = px.line(
                                    plat_agg,
                                    x="platform",
                                    y=metric_col,
                                    title=f"{agency_name}: {metric_to_show} by Platform",
                                    labels={"platform": "Platform", metric_col: metric_to_show},
                                    markers=True,
                                    color_discrete_sequence=["#49b156"]
                                )
                            else:  # Area
                                fig = px.area(
                                    plat_agg,
                                    x="platform",
                                    y=metric_col,
                                    title=f"{agency_name}: {metric_to_show} by Platform",
                                    labels={"platform": "Platform", metric_col: metric_to_show},
                                    color_discrete_sequence=["#49b156"]
                                )
                            
                            if show_values and chart_type == "Bar":
                                if metric_col == "cpl_platform":
                                    fig.update_traces(texttemplate='$%{text:.2f}', textposition='outside')
                                else:
                                    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                            
                            fig.update_layout(
                                showlegend=False,
                                height=400,
                                margin=dict(l=20, r=20, t=40, b=20)
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            st.markdown("---")
                
                for c in [x for x in ["spend", "cpl_platform"] if x in plat.columns]:
                    plat[c] = fmt_currency_series(plat[c])
                
                # Build filters - add device if column exists
                filters = {"platform": f"{agency_name}_plat_platform"}
                if "device" in plat.columns:
                    filters["device"] = f"{agency_name}_plat_device"
                
                display_table_with_total(
                    plat, 
                    "platform", 
                    "TOTAL",
                    filters=filters
                )
                
                if DFI_AVAILABLE:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        df_png = prepare_df_for_png(plat.copy())
                        style = hide_index_styler(df_png)
                        dfi.export(style, tmp.name)
                        with open(tmp.name, "rb") as f:
                            st.download_button(
                                f"⬇️ Download {agency_name} Platform Overview (PNG)", 
                                f.read(), 
                                file_name=f"{agency_name.lower()}_platform_overview.png", 
                                mime="image/png", 
                                use_container_width=True
                            )

            # UTM Overview
            with st.expander(f"{agency_name}: UTM Overview (Platform × UTM + TOTAL)", expanded=False):
                # Use the original filtered dataframe before analyze() processing
                # The sub_df might have modified columns from analyze()
                utm_source_df = df_in[ag_mask].copy()
                
                camp_col = get_col(utm_source_df, ["campaign_id", "campaign"])
                
                if camp_col is None:
                    st.info("No Campaign ID column found for UTM overview.")
                else:
                    # Get the original column names from the raw data
                    qs_col = get_col(utm_source_df, ["quote_starts", "qs", "quote_start", "quotes", "quote starts"])
                    ph_col = get_col(utm_source_df, ["phone_clicks", "phone clicks", "phone", "calls"])
                    sms_col = get_col(utm_source_df, ["sms_clicks", "sms clicks", "sms", "text clicks"])
                    
                    # Convert to numeric first
                    to_num = lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0)
                    
                    if qs_col:
                        utm_source_df["_qs"] = to_num(utm_source_df[qs_col])
                    else:
                        utm_source_df["_qs"] = 0.0
                        
                    if ph_col:
                        utm_source_df["_phone"] = to_num(utm_source_df[ph_col])
                    else:
                        utm_source_df["_phone"] = 0.0
                        
                    if sms_col:
                        utm_source_df["_sms"] = to_num(utm_source_df[sms_col])
                    else:
                        utm_source_df["_sms"] = 0.0
                    
                    utm_source_df["_leads"] = utm_source_df["_qs"] + utm_source_df["_phone"] + utm_source_df["_sms"]
                    
                    # Extract UTM and add platform classification
                    utm_source_df["utm"] = utm_source_df[camp_col].apply(extract_utm_from_campaign_id)
                    utm_source_df["utm"] = utm_source_df["utm"].replace("", "Unmatched")
                    
                    # Get platform column (should already exist from analyze, but let's be safe)
                    traffic_col = detect_traffic_source_col(utm_source_df)
                    if "platform" not in utm_source_df.columns:
                        utm_source_df["platform"] = utm_source_df.apply(
                            lambda r: classify_platform(r[camp_col], r[traffic_col] if traffic_col else ""), 
                            axis=1
                        )
                    
                    # Add device if device breakdown is enabled
                    if add_device_column:
                        if "device" not in utm_source_df.columns:
                            utm_source_df["device"] = utm_source_df.apply(
                                lambda r: classify_device(r[camp_col], r["platform"]), 
                                axis=1
                            )
                        group_cols = ["device", "platform", "utm"]
                    else:
                        group_cols = ["platform", "utm"]
                    
                    utm_over = utm_source_df.groupby(group_cols, as_index=False).agg(
                        quote_starts=("_qs", "sum"),
                        phone_clicks=("_phone", "sum"),
                        sms_clicks=("_sms", "sum"),
                        leads=("_leads", "sum")
                    ).sort_values(["platform", "leads", "utm"], ascending=[True, False, True]).reset_index(drop=True)
                    
                    # Filter out rows where all metrics are zero
                    utm_over = utm_over[
                        (utm_over["quote_starts"] > 0) | 
                        (utm_over["phone_clicks"] > 0) | 
                        (utm_over["sms_clicks"] > 0) | 
                        (utm_over["leads"] > 0)
                    ].reset_index(drop=True)
                    
                    # Add TOTAL row (calculate before adding)
                    totals = {
                        "platform": "",
                        "utm": "TOTAL",
                        "quote_starts": utm_over["quote_starts"].sum(),
                        "phone_clicks": utm_over["phone_clicks"].sum(),
                        "sms_clicks": utm_over["sms_clicks"].sum(),
                        "leads": utm_over["leads"].sum()
                    }
                    if add_device_column:
                        totals["device"] = ""
                    total_row = pd.DataFrame([totals])
                    
                    # Concatenate and reset index to ensure TOTAL is always last
                    utm_over = pd.concat([utm_over, total_row], ignore_index=True)
                    
                    # Build filters dict based on available columns
                    utm_filters = {}
                    if "device" in utm_over.columns:
                        utm_filters["device"] = f"{agency_name}_utm_device"
                    if "platform" in utm_over.columns:
                        utm_filters["platform"] = f"{agency_name}_utm_platform"
                    if "utm" in utm_over.columns:
                        utm_filters["utm"] = f"{agency_name}_utm_source"
                    
                    display_table_with_total(utm_over, "utm", "TOTAL", filters=utm_filters if utm_filters else None)
                    
                    if DFI_AVAILABLE:
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            df_png = prepare_df_for_png(utm_over.copy())
                            style = hide_index_styler(df_png)
                            dfi.export(style, tmp.name)
                            with open(tmp.name, "rb") as f:
                                st.download_button(
                                    f"⬇️ Download {agency_name} UTM Overview (PNG)", 
                                    f.read(), 
                                    file_name=f"utm_overview_{agency_name.lower()}.png", 
                                    mime="image/png", 
                                    use_container_width=True
                                )

            # By Product
            with st.expander(f"{agency_name}: By Product (All Platforms)", expanded=False):
                prod_tot = single["by_product_total"].copy()
                
                # Add chart with controls
                if PLOTLY_AVAILABLE:
                    prod_chart = prod_tot[prod_tot["product"] != "TOTAL"].copy()
                    
                    if not prod_chart.empty:
                        # Chart controls
                        chart_col1, chart_col2, chart_col3 = st.columns([2, 2, 2])
                        
                        with chart_col1:
                            prod_chart_type = st.selectbox(
                                "Chart Type:",
                                options=["Pie", "Bar", "Donut"],
                                key=f"{agency_name}_prod_chart_type"
                            )
                        
                        with chart_col2:
                            prod_metric = st.selectbox(
                                "Metric:",
                                options=["Leads (Total)", "Quote Starts", "Phone Clicks", "SMS Clicks"],
                                key=f"{agency_name}_prod_metric"
                            )
                        
                        # Map metric selection
                        prod_metric_map = {
                            "Leads (Total)": "leads",
                            "Quote Starts": "quote_starts",
                            "Phone Clicks": "phone_clicks",
                            "SMS Clicks": "sms_clicks"
                        }
                        
                        prod_metric_col = prod_metric_map[prod_metric]
                        
                        # If device column exists, aggregate for chart
                        if "device" in prod_chart.columns:
                            prod_agg = prod_chart.groupby("product", as_index=False)[prod_metric_col].sum()
                        else:
                            prod_agg = prod_chart[["product", prod_metric_col]].copy()
                        
                        # Create chart based on type
                        if prod_chart_type in ["Pie", "Donut"]:
                            fig_pie = px.pie(
                                prod_agg,
                                values=prod_metric_col,
                                names="product",
                                title=f"{agency_name}: {prod_metric} Distribution by Product",
                                color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"],
                                hole=0.4 if prod_chart_type == "Donut" else 0
                            )
                            fig_pie.update_traces(
                                textposition='inside',
                                textinfo='percent+label',
                                hovertemplate=f'<b>%{{label}}</b><br>{prod_metric}: %{{value:,.0f}}<br>Share: %{{percent}}<extra></extra>'
                            )
                            fig_pie.update_layout(height=400)
                            st.plotly_chart(fig_pie, use_container_width=True)
                        else:  # Bar
                            fig_bar = px.bar(
                                prod_agg,
                                x="product",
                                y=prod_metric_col,
                                title=f"{agency_name}: {prod_metric} by Product",
                                labels={"product": "Product", prod_metric_col: prod_metric},
                                color=prod_metric_col,
                                color_continuous_scale=["#eef7ef", "#49b156"],
                                text=prod_metric_col
                            )
                            fig_bar.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                            fig_bar.update_layout(
                                showlegend=False,
                                height=400
                            )
                            st.plotly_chart(fig_bar, use_container_width=True)
                        
                        st.markdown("---")
                
                # Build filters - add device if column exists
                filters = {"product": f"{agency_name}_prod_product"}
                if "device" in prod_tot.columns:
                    filters["device"] = f"{agency_name}_prod_device"
                
                display_table_with_total(
                    prod_tot, 
                    "product", 
                    "TOTAL", 
                    filters=filters
                )
                
                if DFI_AVAILABLE:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        df_png = prepare_df_for_png(single["by_product_total"].copy())
                        style = hide_index_styler(df_png)
                        dfi.export(style, tmp.name)
                        with open(tmp.name, "rb") as f:
                            st.download_button(
                                f"⬇️ Download {agency_name} By Product (PNG)", 
                                f.read(), 
                                file_name=f"{agency_name.lower()}_by_product_total.png", 
                                mime="image/png", 
                                use_container_width=True
                            )

            # By Product × Platform
            with st.expander(f"{agency_name}: By Product × Platform (Volumes + % Share)", expanded=False):
                bpp = single["by_product_platform"].copy()
                bpp["lead_share_pct"] = pd.to_numeric(bpp["lead_share_within_platform"], errors="coerce") * 100.0
                
                # Add chart with controls
                if PLOTLY_AVAILABLE:
                    bpp_chart = bpp.copy()
                    
                    # Chart controls
                    chart_col1, chart_col2, chart_col3 = st.columns([2, 2, 2])
                    
                    with chart_col1:
                        bpp_chart_type = st.selectbox(
                            "Chart Type:",
                            options=["Stacked Bar", "Grouped Bar", "Line", "Area", "Heatmap", "Scatter"],
                            key=f"{agency_name}_bpp_chart_type"
                        )
                    
                    with chart_col2:
                        bpp_metric = st.selectbox(
                            "Metric:",
                            options=["Lead Opportunities", "Quote Starts", "Phone Clicks", "SMS Clicks", "Lead Share %"],
                            key=f"{agency_name}_bpp_metric"
                        )
                    
                    with chart_col3:
                        bpp_show_values = st.checkbox(
                            "Show Values",
                            value=True,
                            key=f"{agency_name}_bpp_show_values"
                        )
                    
                    # Map metric selection
                    bpp_metric_map = {
                        "Lead Opportunities": "lead_opportunities",
                        "Quote Starts": "quote_starts",
                        "Phone Clicks": "phone_clicks",
                        "SMS Clicks": "sms_clicks",
                        "Lead Share %": "lead_share_pct"
                    }
                    
                    bpp_metric_col = bpp_metric_map[bpp_metric]
                    
                    # Aggregate if device column exists
                    if "device" in bpp_chart.columns and bpp_metric_col != "lead_share_pct":
                        bpp_agg = bpp_chart.groupby(["platform", "product"], as_index=False)[bpp_metric_col].sum()
                    else:
                        bpp_agg = bpp_chart[["platform", "product", bpp_metric_col]].copy()
                    
                    if not bpp_agg.empty:
                        # Create chart based on type
                        if bpp_chart_type == "Stacked Bar":
                            fig_bpp = px.bar(
                                bpp_agg,
                                x="platform",
                                y=bpp_metric_col,
                                color="product",
                                title=f"{agency_name}: {bpp_metric} by Platform & Product",
                                labels={"platform": "Platform", bpp_metric_col: bpp_metric, "product": "Product"},
                                color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"],
                                text=bpp_metric_col if bpp_show_values else None,
                                barmode="stack"
                            )
                        elif bpp_chart_type == "Grouped Bar":
                            fig_bpp = px.bar(
                                bpp_agg,
                                x="platform",
                                y=bpp_metric_col,
                                color="product",
                                title=f"{agency_name}: {bpp_metric} by Platform & Product",
                                labels={"platform": "Platform", bpp_metric_col: bpp_metric, "product": "Product"},
                                color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"],
                                text=bpp_metric_col if bpp_show_values else None,
                                barmode="group"
                            )
                        elif bpp_chart_type == "Line":
                            fig_bpp = px.line(
                                bpp_agg,
                                x="platform",
                                y=bpp_metric_col,
                                color="product",
                                title=f"{agency_name}: {bpp_metric} by Platform & Product",
                                labels={"platform": "Platform", bpp_metric_col: bpp_metric, "product": "Product"},
                                color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"],
                                markers=True
                            )
                        elif bpp_chart_type == "Area":
                            fig_bpp = px.area(
                                bpp_agg,
                                x="platform",
                                y=bpp_metric_col,
                                color="product",
                                title=f"{agency_name}: {bpp_metric} by Platform & Product",
                                labels={"platform": "Platform", bpp_metric_col: bpp_metric, "product": "Product"},
                                color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"]
                            )
                        elif bpp_chart_type == "Heatmap":
                            # Pivot for heatmap
                            heatmap_data = bpp_agg.pivot(index="product", columns="platform", values=bpp_metric_col)
                            fig_bpp = px.imshow(
                                heatmap_data,
                                title=f"{agency_name}: {bpp_metric} Heatmap",
                                labels=dict(x="Platform", y="Product", color=bpp_metric),
                                color_continuous_scale=["#f2f0e6", "#efd568", "#49b156", "#0f5340"],
                                text_auto=True if bpp_show_values else False
                            )
                        else:  # Scatter
                            fig_bpp = px.scatter(
                                bpp_agg,
                                x="platform",
                                y=bpp_metric_col,
                                color="product",
                                size=bpp_metric_col,
                                title=f"{agency_name}: {bpp_metric} by Platform & Product",
                                labels={"platform": "Platform", bpp_metric_col: bpp_metric, "product": "Product"},
                                color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"]
                            )
                        
                        if bpp_show_values and bpp_chart_type in ["Stacked Bar", "Grouped Bar"]:
                            if bpp_metric_col == "lead_share_pct":
                                fig_bpp.update_traces(texttemplate='%{text:.1f}%', textposition='inside')
                            else:
                                fig_bpp.update_traces(texttemplate='%{text:,.0f}', textposition='inside')
                        
                        fig_bpp.update_layout(
                            height=400,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        st.plotly_chart(fig_bpp, use_container_width=True)
                        
                        st.markdown("---")
                
                # Determine columns to display
                display_cols = ["platform", "product", "quote_starts", "phone_clicks", "sms_clicks", "lead_opportunities", "lead_share_pct"]
                if "device" in bpp.columns:
                    display_cols.insert(0, "device")  # Add device as first column
                
                bpp_display = bpp[display_cols].copy()
                
                # Add filters - conditionally add device filter
                num_filters = 2 + (1 if "device" in bpp_display.columns else 0)
                filter_cols = st.columns(num_filters)
                bpp_filtered = bpp_display.copy()
                
                col_idx = 0
                if "device" in bpp_filtered.columns:
                    with filter_cols[col_idx]:
                        device_vals = sorted(bpp_filtered["device"].unique())
                        sel_dev = st.multiselect(
                            "🔍 Device:",
                            options=device_vals,
                            default=device_vals,
                            key=f"{agency_name}_bpp_device"
                        )
                        if sel_dev:
                            bpp_filtered = bpp_filtered[bpp_filtered["device"].isin(sel_dev)]
                    col_idx += 1
                
                with filter_cols[col_idx]:
                    if "platform" in bpp_filtered.columns:
                        plat_vals = sorted(bpp_filtered["platform"].unique())
                        sel_plat = st.multiselect(
                            "🔍 Platform:",
                            options=plat_vals,
                            default=plat_vals,
                            key=f"{agency_name}_bpp_platform"
                        )
                        if sel_plat:
                            bpp_filtered = bpp_filtered[bpp_filtered["platform"].isin(sel_plat)]
                col_idx += 1
                
                with filter_cols[col_idx]:
                    if "product" in bpp_filtered.columns:
                        prod_vals = sorted(bpp_filtered["product"].unique())
                        sel_prod = st.multiselect(
                            "🔍 Product:",
                            options=prod_vals,
                            default=prod_vals,
                            key=f"{agency_name}_bpp_product"
                        )
                        if sel_prod:
                            bpp_filtered = bpp_filtered[bpp_filtered["product"].isin(sel_prod)]
                
                bpp_filtered["lead_share_pct"] = fmt_percent_series(bpp_filtered["lead_share_pct"], places=1)
                
                if not bpp_filtered.empty:
                    st.dataframe(pretty_headers(bpp_filtered), use_container_width=True, hide_index=True)
                else:
                    st.info("No data matches the selected filters.")
                
                if DFI_AVAILABLE:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        df_png = prepare_df_for_png(bpp_display.copy())
                        style = hide_index_styler(df_png)
                        dfi.export(style, tmp.name)
                        with open(tmp.name, "rb") as f:
                            st.download_button(
                                f"⬇️ Download {agency_name} By Product x Platform (PNG)", 
                                f.read(), 
                                file_name=f"{agency_name.lower()}_by_product_x_platform.png", 
                                mime="image/png", 
                                use_container_width=True
                            )

            # By Source
            with st.expander(f"{agency_name}: By Source", expanded=False):
                src = single["by_source"].copy()
                
                # Add filters for all available columns - conditionally add device
                num_filters = 4 + (1 if "device" in src.columns else 0)
                filter_cols = st.columns(num_filters)
                src_filtered = src.copy()
                
                col_idx = 0
                if "device" in src_filtered.columns:
                    with filter_cols[col_idx]:
                        device_vals = sorted(src_filtered["device"].dropna().unique())
                        if device_vals:
                            sel_dev = st.multiselect(
                                "🔍 Device:",
                                options=device_vals,
                                default=device_vals,
                                key=f"{agency_name}_src_device_filter"
                            )
                            if sel_dev:
                                src_filtered = src_filtered[src_filtered["device"].isin(sel_dev)]
                    col_idx += 1
                
                with filter_cols[col_idx]:
                    if "source" in src_filtered.columns:
                        source_vals = sorted(src_filtered["source"].dropna().unique())
                        if source_vals:
                            sel_source = st.multiselect(
                                "🔍 Source:",
                                options=source_vals,
                                default=source_vals,
                                key=f"{agency_name}_source_filter"
                            )
                            if sel_source:
                                src_filtered = src_filtered[src_filtered["source"].isin(sel_source)]
                col_idx += 1
                
                with filter_cols[col_idx]:
                    if "domain" in src_filtered.columns:
                        domain_vals = sorted(src_filtered["domain"].dropna().unique())
                        if domain_vals:
                            sel_domain = st.multiselect(
                                "🔍 Domain:",
                                options=domain_vals,
                                default=domain_vals,
                                key=f"{agency_name}_src_domain_filter"
                            )
                            if sel_domain:
                                src_filtered = src_filtered[src_filtered["domain"].isin(sel_domain)]
                col_idx += 1
                
                with filter_cols[col_idx]:
                    if "platform" in src_filtered.columns:
                        platform_vals = sorted(src_filtered["platform"].dropna().unique())
                        if platform_vals:
                            sel_platform = st.multiselect(
                                "🔍 Platform:",
                                options=platform_vals,
                                default=platform_vals,
                                key=f"{agency_name}_src_platform_filter"
                            )
                            if sel_platform:
                                src_filtered = src_filtered[src_filtered["platform"].isin(sel_platform)]
                col_idx += 1
                
                with filter_cols[col_idx]:
                    if "agency" in src_filtered.columns:
                        agency_vals = sorted(src_filtered["agency"].dropna().unique())
                        if agency_vals:
                            sel_agency = st.multiselect(
                                "🔍 Agency:",
                                options=agency_vals,
                                default=agency_vals,
                                key=f"{agency_name}_src_agency_filter"
                            )
                            if sel_agency:
                                src_filtered = src_filtered[src_filtered["agency"].isin(sel_agency)]
                
                if not src_filtered.empty:
                    st.dataframe(pretty_headers(src_filtered), use_container_width=True, hide_index=True)
                else:
                    st.info("No data matches the selected filters.")
                
                if DFI_AVAILABLE:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        df_png = prepare_df_for_png(single["by_source"].copy())
                        style = hide_index_styler(df_png)
                        dfi.export(style, tmp.name)
                        with open(tmp.name, "rb") as f:
                            st.download_button(
                                f"⬇️ Download {agency_name} By Source (PNG)", 
                                f.read(), 
                                file_name=f"{agency_name.lower()}_by_source.png", 
                                mime="image/png", 
                                use_container_width=True
                            )

    # ---------- COMBINED SECTIONS (collapsed) ----------
    # 1) Platform totals only (Platform + TOTAL) — aggregated across agencies
    with st.expander("Combined — Platform (Totals)", expanded=False):
        plat = results["platform_overview"].copy()
        
        # Add visualizations if plotly is available
        if PLOTLY_AVAILABLE:
            plat_chart = plat[plat["platform"] != "TOTAL"].copy()
            
            if not plat_chart.empty:
                # Chart controls
                chart_col1, chart_col2, chart_col3 = st.columns([2, 2, 2])
                
                with chart_col1:
                    combined_chart_type = st.selectbox(
                        "Chart Type:",
                        options=["Bar", "Line", "Area", "Pie", "Scatter"],
                        key="combined_plat_chart_type"
                    )
                
                with chart_col2:
                    combined_metric = st.selectbox(
                        "Metric:",
                        options=["Leads (Total)", "Quote Starts", "Phone Clicks", "SMS Clicks", "Spend", "CPL"],
                        key="combined_plat_metric"
                    )
                
                with chart_col3:
                    combined_show_values = st.checkbox(
                        "Show Values",
                        value=True,
                        key="combined_plat_show_values"
                    )
                
                # Map metric selection
                combined_metric_map = {
                    "Leads (Total)": "leads",
                    "Quote Starts": "quote_starts",
                    "Phone Clicks": "phone_clicks",
                    "SMS Clicks": "sms_clicks",
                    "Spend": "spend",
                    "CPL": "cpl_platform"
                }
                
                combined_metric_col = combined_metric_map[combined_metric]
                
                # Convert to numeric and aggregate if needed
                plat_chart["spend"] = pd.to_numeric(plat_chart["spend"], errors="coerce").fillna(0)
                plat_chart["cpl_platform"] = pd.to_numeric(plat_chart["cpl_platform"], errors="coerce")
                plat_chart["leads"] = pd.to_numeric(plat_chart["leads"], errors="coerce").fillna(0)
                
                # If device column exists, aggregate for charts
                if "device" in plat_chart.columns:
                    plat_agg = plat_chart.groupby("platform", as_index=False).agg({
                        "leads": "sum",
                        "spend": "sum",
                        "quote_starts": "sum",
                        "phone_clicks": "sum",
                        "sms_clicks": "sum"
                    })
                    plat_agg["cpl_platform"] = plat_agg.apply(
                        lambda r: r["spend"] / r["leads"] if r["leads"] > 0 else np.nan,
                        axis=1
                    )
                else:
                    plat_agg = plat_chart.copy()
                
                # Filter out invalid data for CPL
                if combined_metric_col == "cpl_platform":
                    plat_agg = plat_agg[plat_agg["cpl_platform"] > 0]
                
                # Create chart based on type
                if combined_chart_type == "Bar":
                    fig = px.bar(
                        plat_agg,
                        x="platform",
                        y=combined_metric_col,
                        title=f"Combined: {combined_metric} by Platform",
                        labels={"platform": "Platform", combined_metric_col: combined_metric},
                        color=combined_metric_col,
                        color_continuous_scale=["#eef7ef", "#49b156"] if combined_metric_col != "cpl_platform" else ["#49b156", "#efd568", "#f28c82"],
                        text=combined_metric_col if combined_show_values else None
                    )
                elif combined_chart_type == "Line":
                    fig = px.line(
                        plat_agg,
                        x="platform",
                        y=combined_metric_col,
                        title=f"Combined: {combined_metric} by Platform",
                        labels={"platform": "Platform", combined_metric_col: combined_metric},
                        markers=True,
                        color_discrete_sequence=["#49b156"]
                    )
                elif combined_chart_type == "Area":
                    fig = px.area(
                        plat_agg,
                        x="platform",
                        y=combined_metric_col,
                        title=f"Combined: {combined_metric} by Platform",
                        labels={"platform": "Platform", combined_metric_col: combined_metric},
                        color_discrete_sequence=["#49b156"]
                    )
                elif combined_chart_type == "Pie":
                    fig = px.pie(
                        plat_agg,
                        values=combined_metric_col,
                        names="platform",
                        title=f"Combined: {combined_metric} Distribution",
                        color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6", "#cccccc"]
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                else:  # Scatter
                    fig = px.scatter(
                        plat_agg,
                        x="platform",
                        y=combined_metric_col,
                        size=combined_metric_col,
                        title=f"Combined: {combined_metric} by Platform",
                        labels={"platform": "Platform", combined_metric_col: combined_metric},
                        color_discrete_sequence=["#49b156"]
                    )
                
                if combined_show_values and combined_chart_type == "Bar":
                    if combined_metric_col in ["spend", "cpl_platform"]:
                        fig.update_traces(texttemplate='$%{text:,.2f}', textposition='outside')
                    else:
                        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                
                fig.update_layout(
                    showlegend=False if combined_chart_type != "Pie" else True,
                    height=450,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
        
        # Table
        for c in [x for x in ["spend", "cpl_platform"] if x in plat.columns]:
            plat[c] = fmt_currency_series(plat[c])
        display_table_with_total(
            plat, 
            "platform", 
            "TOTAL",
            filters={"platform": "combined_plat_platform"}
        )
        
        if DFI_AVAILABLE:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                df_png = prepare_df_for_png(results["platform_overview"].copy())
                style = hide_index_styler(df_png)
                dfi.export(style, tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button(
                        "⬇️ Download Combined Platform (PNG)", 
                        f.read(), 
                        file_name="combined_platform_totals.png", 
                        mime="image/png", 
                        use_container_width=True
                    )

    # 2) Agency overview
    with st.expander("Combined — Agency Overview (Volumes + TOTAL)", expanded=False):
        ag = results["agency_overview"].copy()
        
        # Add stacked bar chart visualization
        if PLOTLY_AVAILABLE:
            ag_chart = ag[ag["agency"] != "TOTAL"].copy()
            
            if not ag_chart.empty:
                # If device column exists, aggregate for chart
                if "device" in ag_chart.columns:
                    ag_agg = ag_chart.groupby("agency", as_index=False).agg({
                        "quote_starts": "sum",
                        "phone_clicks": "sum",
                        "sms_clicks": "sum",
                        "leads": "sum"
                    })
                else:
                    ag_agg = ag_chart.copy()
                
                # Reshape for stacked bar chart
                ag_melted = ag_agg.melt(
                    id_vars=["agency"],
                    value_vars=["quote_starts", "phone_clicks", "sms_clicks"],
                    var_name="Lead Type",
                    value_name="Count"
                )
                ag_melted["Lead Type"] = ag_melted["Lead Type"].map({
                    "quote_starts": "Quote Starts",
                    "phone_clicks": "Phone Clicks",
                    "sms_clicks": "SMS Clicks"
                })
                
                fig_agency = px.bar(
                    ag_melted,
                    x="agency",
                    y="Count",
                    color="Lead Type",
                    title="Lead Breakdown by Agency",
                    labels={"agency": "Agency", "Count": "Total"},
                    color_discrete_map={
                        "Quote Starts": "#49b156",
                        "Phone Clicks": "#0f5340",
                        "SMS Clicks": "#efd568"
                    },
                    text="Count"
                )
                fig_agency.update_traces(texttemplate='%{text:,.0f}', textposition='inside')
                fig_agency.update_layout(
                    barmode='stack',
                    height=400,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_agency, use_container_width=True)
                
                st.markdown("---")
        
        # Table
        display_table_with_total(
            ag, 
            "agency", 
            "TOTAL",
            filters={"agency": "combined_agency_filter"}
        )
        
        if DFI_AVAILABLE:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                df_png = prepare_df_for_png(results["agency_overview"].copy())
                style = hide_index_styler(df_png)
                dfi.export(style, tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button(
                        "⬇️ Download Combined Agency Overview (PNG)", 
                        f.read(), 
                        file_name="combined_agency_overview.png", 
                        mime="image/png", 
                        use_container_width=True
                    )

    # 2b) Combined UTM Overview (Platform × UTM + TOTAL)
    with st.expander("Combined — UTM Overview (Platform × UTM + TOTAL)", expanded=False):
        if results["utm_overview"] is not None and not results["utm_overview"].empty:
            utm_over = results["utm_overview"].copy()
            display_table_with_total(utm_over, "utm", "TOTAL")
            
            if DFI_AVAILABLE:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    df_png = prepare_df_for_png(utm_over.copy())
                    style = hide_index_styler(df_png)
                    dfi.export(style, tmp.name)
                    with open(tmp.name, "rb") as f:
                        st.download_button(
                            "⬇️ Download Combined UTM Overview (PNG)", 
                            f.read(), 
                            file_name="combined_utm_overview.png", 
                            mime="image/png", 
                            use_container_width=True
                        )
        else:
            st.info("No Campaign ID column found - UTM overview unavailable.")

    # 3) Product × Platform totals (no agency split)
    with st.expander("Combined — Product × Platform (Totals + % Share)", expanded=False):
        bpp = results["by_product_platform"].copy()
        bpp["lead_share_pct"] = pd.to_numeric(bpp["lead_share_within_platform"], errors="coerce") * 100.0
        bpp_display = bpp[["platform", "product", "quote_starts", "phone_clicks", "sms_clicks", "lead_opportunities", "lead_share_pct"]].copy()
        
        # Add filters
        filter_cols = st.columns(2)
        bpp_filtered = bpp_display.copy()
        
        with filter_cols[0]:
            if "platform" in bpp_filtered.columns:
                plat_vals = sorted(bpp_filtered["platform"].unique())
                sel_plat = st.multiselect(
                    "🔍 Platform:",
                    options=plat_vals,
                    default=plat_vals,
                    key="combined_bpp_platform"
                )
                if sel_plat:
                    bpp_filtered = bpp_filtered[bpp_filtered["platform"].isin(sel_plat)]
        
        with filter_cols[1]:
            if "product" in bpp_filtered.columns:
                prod_vals = sorted(bpp_filtered["product"].unique())
                sel_prod = st.multiselect(
                    "🔍 Product:",
                    options=prod_vals,
                    default=prod_vals,
                    key="combined_bpp_product"
                )
                if sel_prod:
                    bpp_filtered = bpp_filtered[bpp_filtered["product"].isin(sel_prod)]
        
        bpp_filtered["lead_share_pct"] = fmt_percent_series(bpp_filtered["lead_share_pct"], places=1)
        
        if not bpp_filtered.empty:
            st.dataframe(pretty_headers(bpp_filtered), use_container_width=True, hide_index=True)
        else:
            st.info("No data matches the selected filters.")
        
        if DFI_AVAILABLE:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                df_png = prepare_df_for_png(bpp_display.copy())
                style = hide_index_styler(df_png)
                dfi.export(style, tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button(
                        "⬇️ Download Combined Product x Platform (PNG)", 
                        f.read(), 
                        file_name="combined_product_x_platform.png", 
                        mime="image/png", 
                        use_container_width=True
                    )

    # 4) Product totals only (no agency / no platform)
    with st.expander("Combined — Product (Totals)", expanded=False):
        prod_tot = results["by_product_total"].copy()
        
        # Add pie chart visualization
        if PLOTLY_AVAILABLE:
            prod_chart = prod_tot[prod_tot["product"] != "TOTAL"].copy()
            
            if not prod_chart.empty:
                # Convert to numeric
                prod_chart["leads"] = pd.to_numeric(prod_chart["leads"], errors="coerce").fillna(0)
                
                # If device column exists, aggregate for chart
                if "device" in prod_chart.columns:
                    prod_agg = prod_chart.groupby("product", as_index=False)["leads"].sum()
                else:
                    prod_agg = prod_chart[["product", "leads"]].copy()
                
                # Filter out zero leads
                prod_agg = prod_agg[prod_agg["leads"] > 0]
                
                if not prod_agg.empty:
                    # Create pie chart
                    fig_pie = px.pie(
                        prod_agg,
                        values="leads",
                        names="product",
                        title="Lead Distribution by Product",
                        color_discrete_sequence=["#49b156", "#0f5340", "#efd568", "#f2f0e6"]
                    )
                    fig_pie.update_traces(
                        textposition='inside',
                        textinfo='percent+label',
                        hovertemplate='<b>%{label}</b><br>Leads: %{value:,.0f}<br>Share: %{percent}<extra></extra>'
                    )
                    fig_pie.update_layout(height=400)
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                    st.markdown("---")
        
        # Table
        display_table_with_total(
            prod_tot, 
            "product", 
            "TOTAL", 
            filters={"product": "combined_product_filter"}
        )
        
        if DFI_AVAILABLE:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                df_png = prepare_df_for_png(results["by_product_total"].copy())
                style = hide_index_styler(df_png)
                dfi.export(style, tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button(
                        "⬇️ Download Combined Product (PNG)", 
                        f.read(), 
                        file_name="combined_product_totals.png", 
                        mime="image/png", 
                        use_container_width=True
                    )

    # 5) By Source (keeps Agency column for traceability)
    with st.expander("Combined — By Source (includes Agency column)", expanded=False):
        src = results["by_source"].copy()
        
        # Add filters for all available columns
        filter_cols = st.columns(4)
        src_filtered = src.copy()
        
        with filter_cols[0]:
            if "source" in src_filtered.columns:
                source_vals = sorted(src_filtered["source"].dropna().unique())
                if source_vals:
                    sel_source = st.multiselect(
                        "🔍 Source:",
                        options=source_vals,
                        default=source_vals,
                        key="combined_source_filter"
                    )
                    if sel_source:
                        src_filtered = src_filtered[src_filtered["source"].isin(sel_source)]
        
        with filter_cols[1]:
            if "domain" in src_filtered.columns:
                domain_vals = sorted(src_filtered["domain"].dropna().unique())
                if domain_vals:
                    sel_domain = st.multiselect(
                        "🔍 Domain:",
                        options=domain_vals,
                        default=domain_vals,
                        key="combined_src_domain_filter"
                    )
                    if sel_domain:
                        src_filtered = src_filtered[src_filtered["domain"].isin(sel_domain)]
        
        with filter_cols[2]:
            if "platform" in src_filtered.columns:
                platform_vals = sorted(src_filtered["platform"].dropna().unique())
                if platform_vals:
                    sel_platform = st.multiselect(
                        "🔍 Platform:",
                        options=platform_vals,
                        default=platform_vals,
                        key="combined_src_platform_filter"
                    )
                    if sel_platform:
                        src_filtered = src_filtered[src_filtered["platform"].isin(sel_platform)]
        
        with filter_cols[3]:
            if "agency" in src_filtered.columns:
                agency_vals = sorted(src_filtered["agency"].dropna().unique())
                if agency_vals:
                    sel_agency = st.multiselect(
                        "🔍 Agency:",
                        options=agency_vals,
                        default=agency_vals,
                        key="combined_src_agency_filter"
                    )
                    if sel_agency:
                        src_filtered = src_filtered[src_filtered["agency"].isin(sel_agency)]
        
        if not src_filtered.empty:
            st.dataframe(pretty_headers(src_filtered), use_container_width=True, hide_index=True)
        else:
            st.info("No data matches the selected filters.")
        
        if DFI_AVAILABLE:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                df_png = prepare_df_for_png(results["by_source"].copy())
                style = hide_index_styler(df_png)
                dfi.export(style, tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button(
                        "⬇️ Download Combined By Source (PNG)", 
                        f.read(), 
                        file_name="combined_by_source.png", 
                        mime="image/png", 
                        use_container_width=True
                    )

    # ---------- Exports (short sheet names <=31 chars) ----------
    excel_bytes = build_excel({
        "Platform": results["platform_overview"],
        "Agency": results["agency_overview"],
        "Prod x Plat": results["by_product_platform"],
        "Product": results["by_product_total"],
        "By Source": results["by_source"],
    })

    # ---------- Budget Optimizer (Demo only) ----------
    with st.expander("💡 Budget Optimizer (Demo) — suggest platform allocation to maximize leads", expanded=False):
        # Use platform CPL from combined platform overview (exclude TOTAL, Unknown, and Listings)
        plat_eff = results["platform_overview"].copy()
        plat_eff = plat_eff[~plat_eff["platform"].isin(["TOTAL", "Unknown", "Listings"])].copy()
        
        # If device column exists, aggregate by platform only for the optimizer
        if "device" in plat_eff.columns:
            plat_eff = plat_eff.groupby("platform", as_index=False).agg({
                "spend": "sum",
                "leads": "sum",
                "quote_starts": "sum",
                "phone_clicks": "sum",
                "sms_clicks": "sum"
            })
            # Recalculate CPL after aggregation
            plat_eff["cpl_platform"] = plat_eff.apply(
                lambda r: r["spend"] / r["leads"] if r["leads"] > 0 else np.nan,
                axis=1
            )
        
        if plat_eff.empty:
            st.info("No platform data available to compute suggestions.")
        else:
            # Compute CPL per platform as spend/leads (already available), guard against zeros
            eff = plat_eff[["platform", "spend", "cpl_platform", "leads"]].copy()
            
            # Convert CPL to numeric once (moved outside conditional to avoid duplication)
            eff["cpl_platform"] = pd.to_numeric(eff["cpl_platform"], errors="coerce")
            
            # Default total budget = current summed spend if present, else 0
            default_budget = float(pd.to_numeric(eff["spend"], errors="coerce").fillna(0).sum())
            total_budget = st.number_input("Total budget to allocate ($)", value=default_budget, min_value=0.0, step=100.0, format="%.2f")
            st.caption("Allocation is proportional to efficiency (1 / Platform CPL). Platforms with no CPL (no leads) get 0 by default.")
            conservative_mode = st.checkbox(
                f"Conservative mode (dampen shifts when CPL ≤ ${CONSERVATIVE_CPL_THRESHOLD})", 
                value=True, 
                help="Adds inertia: dampens low-CPL moves and blends with current spend share."
            )
            
            # Minimum floors per platform
            cols = st.columns(len(eff))
            min_floors = {}
            for i, (_, row) in enumerate(eff.iterrows()):
                with cols[i]:
                    min_floors[row["platform"]] = st.number_input(
                        f"Min ${row['platform']}", 
                        value=0.0, 
                        min_value=0.0, 
                        step=50.0, 
                        format="%.2f", 
                        key=f"opt_floor_{row['platform']}"
                    )
            
            # Initialize csv_bytes to avoid undefined variable error
            csv_bytes = b""
            
            # Minimize overall CPL: allocate the remainder to platform(s) with the lowest positive CPL
            total_floor = float(sum(min_floors.values()))
            
            if total_floor > total_budget:
                st.error("Sum of minimums exceeds total budget. Lower the minimums or increase the total budget.")
            else:
                remaining = max(0.0, total_budget - total_floor)
                
                if conservative_mode:
                    # Conservative mode: blend efficiency with current spend
                    base_w = eff["cpl_platform"].apply(
                        lambda x: 0.0 if (pd.isna(x) or x <= 0) else 1.0 / float(x)
                    )
                    damp = eff["cpl_platform"].apply(
                        lambda x: CONSERVATIVE_DAMPING_FACTOR if (pd.notna(x) and x <= CONSERVATIVE_CPL_THRESHOLD) else 1.0
                    )
                    base_w = base_w * damp
                    
                    total_sp = pd.to_numeric(eff["spend"], errors="coerce").fillna(0).sum()
                    if total_sp > 0:
                        s_share = pd.to_numeric(eff["spend"], errors="coerce").fillna(0) / total_sp
                    else:
                        s_share = pd.Series([1.0 / len(eff)] * len(eff), index=eff.index)
                    
                    final_w = CONSERVATIVE_EFFICIENCY_WEIGHT * base_w + CONSERVATIVE_SPEND_WEIGHT * s_share
                    wsum = float(final_w.sum())
                    
                    if wsum > 0:
                        eff["alloc_var"] = (final_w / wsum) * remaining
                    else:
                        eff["alloc_var"] = remaining / max(1, len(eff))
                else:
                    # Aggressive mode: allocate all to lowest CPL platform(s)
                    valid = eff["cpl_platform"].where(eff["cpl_platform"] > 0)
                    if valid.notna().any():
                        min_cpl = valid.min()
                        winners = eff["cpl_platform"].eq(min_cpl)
                        n_win = int(winners.sum()) or 1
                        eff["alloc_var"] = 0.0
                        eff.loc[winners, "alloc_var"] = remaining / n_win
                    else:
                        eff["alloc_var"] = remaining / max(1, len(eff))
                
                eff["allocation"] = eff.apply(
                    lambda r: float(min_floors.get(r["platform"], 0.0)) + float(r["alloc_var"]), 
                    axis=1
                )
                
                # Round Suggested Spend to nearest increment
                eff["allocation"] = (ALLOCATION_ROUNDING_INCREMENT * np.round(
                    eff["allocation"] / ALLOCATION_ROUNDING_INCREMENT
                )).astype(int)
                
                # Predicted leads = allocation / CPL
                eff["predicted_leads"] = eff.apply(
                    lambda r: (r["allocation"] / r["cpl_platform"]) 
                    if (pd.notna(r["cpl_platform"]) and r["cpl_platform"] > 0) 
                    else 0.0, 
                    axis=1
                )
                
                # Formatting for display
                out = eff[["platform", "allocation", "predicted_leads", "cpl_platform"]].copy()
                out.rename(columns={
                    "platform": "Platform",
                    "allocation": "Suggested Spend",
                    "predicted_leads": "Predicted Leads",
                    "cpl_platform": "Platform CPL"
                }, inplace=True)
                
                out["Suggested Spend"] = out["Suggested Spend"].apply(lambda x: f"${x:,.2f}")
                out["Platform CPL"] = out["Platform CPL"].apply(
                    lambda x: f"${x:,.2f}" if pd.notna(x) and x > 0 else "—"
                )
                out["Predicted Leads"] = out["Predicted Leads"].apply(lambda x: f"{x:,.1f}")
                
                total_alloc = float(eff["allocation"].sum())
                total_pred = float(eff["predicted_leads"].sum())
                total_cpl_val = (total_alloc / total_pred) if total_pred > 0 else None
                total_cpl_str = (f"${total_cpl_val:,.2f}" if total_cpl_val is not None else "—")
                
                total_row = pd.DataFrame([{
                    "Platform": "TOTAL",
                    "Suggested Spend": f"${total_alloc:,.2f}",
                    "Predicted Leads": f"{total_pred:,.1f}",
                    "Platform CPL": total_cpl_str
                }])
                
                out = pd.concat([out, total_row], ignore_index=True)
                display_table_with_total(out, "Platform", "TOTAL")
                
                # Prepare CSV export
                out_raw = eff[["platform", "allocation", "predicted_leads", "cpl_platform"]].copy()
                out_raw.rename(columns={
                    "platform": "Platform",
                    "allocation": "Suggested_Spend",
                    "predicted_leads": "Predicted_Leads",
                    "cpl_platform": "Platform_CPL"
                }, inplace=True)
                csv_bytes = out_raw.to_csv(index=False).encode("utf-8")
        
        # Download button outside the else block
        st.download_button(
            "⬇️ Download Suggested Allocation (CSV)", 
            data=csv_bytes, 
            file_name="demo_budget_optimizer.csv", 
            mime="text/csv", 
            use_container_width=True
        )

    st.download_button(
        "⬇️ Download Combined Excel Report (Generated "+datetime.now().strftime('%I:%M %p')+")", 
        excel_bytes, 
        "combined_lead_report_demo.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        use_container_width=True
    )

    style_flag = "formatted" if st.session_state.get("sb_csv_style") == "With $ and % symbols" else "raw"
    csv_platform = df_to_csv_bytes(results["platform_overview"].copy(), style=style_flag)
    csv_ag = df_to_csv_bytes(results["agency_overview"].copy(), style=style_flag)
    csv_bpp = df_to_csv_bytes(results["by_product_platform"].copy(), style=style_flag)
    csv_prod = df_to_csv_bytes(results["by_product_total"].copy(), style=style_flag)
    csv_src = df_to_csv_bytes(results["by_source"].copy(), style=style_flag)

    st.markdown("### Download Combined CSVs")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Platform (CSV)", 
            data=csv_platform, 
            file_name="combined_platform.csv",
            mime="text/csv", 
            use_container_width=True
        )
        st.download_button(
            "⬇️ Agency (CSV)", 
            data=csv_ag, 
            file_name="combined_agency.csv",
            mime="text/csv", 
            use_container_width=True
        )
    with c2:
        st.download_button(
            "⬇️ Product × Platform (CSV)", 
            data=csv_bpp, 
            file_name="combined_product_x_platform.csv",
            mime="text/csv", 
            use_container_width=True
        )
        st.download_button(
            "⬇️ Product (CSV)", 
            data=csv_prod, 
            file_name="combined_product.csv",
            mime="text/csv", 
            use_container_width=True
        )
        st.download_button(
            "⬇️ By Source (CSV)", 
            data=csv_src, 
            file_name="combined_by_source.csv",
            mime="text/csv", 
            use_container_width=True
        )

# ---- Footer ----
st.markdown("<hr/>", unsafe_allow_html=True)
st.markdown(
    """
    <div style='color:#47B74F;text-align:center;font-size:14px;padding:20px;'>
        <strong>🍈 Melon Local</strong> Lead Analyzer<br/>
        <span style='color:#114e38;font-size:12px;'>Fresh insights for smarter marketing decisions</span>
    </div>
    """, unsafe_allow_html=True
)
