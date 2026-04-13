# ============================================================================
# Lead Analyzer — Streamlit App (Entry Point)
# ============================================================================
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

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import openpyxl
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

# DFI disabled on Streamlit Cloud
DFI_AVAILABLE = False

from constants import (
    PINE_GREEN, CACTUS_GREEN, LEMON_SUN, MELON_COLORS, ALPINE_CREAM,
    WHITE, TEXT_DARK, TEXT_LIGHT, ADS_THRESHOLDS,
    CONSERVATIVE_CPL_THRESHOLD, CONSERVATIVE_DAMPING_FACTOR,
    CONSERVATIVE_EFFICIENCY_WEIGHT, CONSERVATIVE_SPEND_WEIGHT,
    ALLOCATION_ROUNDING_INCREMENT, UTM_TOKENS_FIXED, PLATFORM_RULES,
    PRODUCT_KEYWORDS, _MELON_MAX_DEVICE_CODES
)
from utils import (
    _norm, get_col, detect_traffic_source_col, choose_source_column,
    pretty_headers, drop_effective_cost_basis, is_currency_col, is_percent_col,
    fmt_currency_series, fmt_percent_series, hide_index_styler,
    prepare_df_for_png, safe_sheet_name, load_uploaded,
    validate_upload, extract_date_range_from_filename
)
from classification import (
    classify_platform, classify_product, classify_device,
    extract_utm_from_campaign_id, load_campaign_mapping,
    _CAMPAIGN_NUM_PRODUCT_MAP
)
from analysis import analyze
from export import (
    df_to_csv_bytes, build_excel, build_html_report, dataframe_to_html
)
from components import display_table_with_total
from ads_health import (
    load_ads_export, analyze_ads_account, process_ads_platform,
    enrich_ads_with_campaign_stats, match_budget_to_accounts,
    format_ads_metric, validate_numeric
)

st.set_page_config(
    page_title="Lead Analyzer — Melon Local",
    page_icon="🍈",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        background-color: #47B74F;
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
        background: linear-gradient(180deg, #0f5340 0%, #47B74F 100%);
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
        background-color: #47B74F !important;
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
        background-color: #47B74F !important;
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
        background-color: #47B74F !important;
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
        border: 2px dashed #47B74F;
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
        background-color: #47B74F !important;
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
    - **HTML**: Web-based reports for easy sharing
    
    ### ⚠️ Important: Understanding "Other" and "Unknown" Classifications
    **"Other" or "Unknown" in Platform/Product classifications represent leads that MySFDomain's tracking software was unable to categorize.**
    
    **The majority of leads are tracked correctly**, but MySFDomain's platform has some limitations in lead categorization that affect a small percentage of data. These tracking gaps are due to MySFDomain's software limitations and do not reflect issues with campaign setup or data quality from Melon Local.
    
    When you see "Other" or "Unknown" categories, this represents MySFDomain's inability to fully categorize all leads, not errors in campaign management or structure.
    """)

st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)

# ---------- Helper Functions ----------

if 'campaign_mapping_loaded' not in st.session_state:
    mapping_df = load_campaign_mapping()
    if mapping_df is not None:
        st.session_state.campaign_mapping = mapping_df
        st.session_state.tab1_mapping = mapping_df  # For Tab 1
        st.session_state.campaign_mapping_loaded = True
    else:
        st.session_state.campaign_mapping = None
        st.session_state.tab1_mapping = None
        st.session_state.campaign_mapping_loaded = False


st.markdown("""
<div class="main-header" style="background: linear-gradient(135deg, #114e38 0%, #47B74F 100%); padding: 2rem 1.5rem; border-radius: 10px; color: white; margin-bottom: 2rem;">
    <h1 style="color: white !important; margin-bottom: 0.5rem;">🍈 Melon Local Lead Analyzer</h1>
    <p style="color: #FEF8E9; font-size: 1.1rem;">Comprehensive lead analytics & ads account optimization</p>
</div>
""", unsafe_allow_html=True)

# Create main tabs
main_tab1, main_tab2 = st.tabs(["📊 Lead Performance Analysis", "💰 Ads Account Health"])

# ========== TAB 1: LEAD PERFORMANCE ==========
with main_tab1:
    st.markdown("### Lead Performance Analysis")

    # ---------- Sidebar (filters only) ----------
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:1rem 0;margin-bottom:1rem;'>
            <div style='font-size:2em;'>🍈</div>
            <div style='font-size:1.3em;font-weight:700;color:#F1CB20;'>melon local</div>
            <div style='font-size:0.9em;opacity:0.8;'>Lead Analyzer</div>
        </div>
        """, unsafe_allow_html=True)

    # ---------- Data Sources ----------
    st.markdown("### Data Sources")

    # ---------- File Upload ----------
    c1, c2 = st.columns(2)
    with c1:
        up_legacy = st.file_uploader("Upload Legacy file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="upload_legacy")
    with c2:
        up_moa = st.file_uploader("Upload MOA file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="upload_moa")
    
    # Show file status
    if up_legacy or up_moa:
        st.markdown("**Files Uploaded:**")
        file_status = []
        if up_legacy:
            file_status.append(f"✅ Legacy: `{up_legacy.name}`")
        if up_moa:
            file_status.append(f"✅ MOA: `{up_moa.name}`")
        st.markdown(" • ".join(file_status))
        st.caption("💡 Analysis will update automatically when files change")
    
    # ---------- Configuration (collapsible) ----------
    with st.expander("⚙️ Configuration", expanded=False):
        _defs = st.session_state.get("_default_budgets", {})
        cfg_col1, cfg_col2 = st.columns(2)

        with cfg_col1:
            st.markdown("**Legacy Budget**")
            legacy_google = st.number_input("Google Spend", value=_defs.get("legacy_google", 0.0), min_value=0.0, step=100.0, format="%.2f", key="legacy_spend_google")
            legacy_ms = st.number_input("Microsoft Spend", value=_defs.get("legacy_ms", 0.0), min_value=0.0, step=100.0, format="%.2f", key="legacy_spend_ms")
            legacy_mm = st.number_input("Melon Max Spend", value=_defs.get("legacy_mm", 0.0), min_value=0.0, step=100.0, format="%.2f", key="legacy_spend_mm")

        with cfg_col2:
            st.markdown("**MOA Budget**")
            moa_google = st.number_input("Google Spend", value=_defs.get("moa_google", 0.0), min_value=0.0, step=100.0, format="%.2f", key="moa_spend_google")
            moa_ms = st.number_input("Microsoft Spend", value=_defs.get("moa_ms", 0.0), min_value=0.0, step=100.0, format="%.2f", key="moa_spend_ms")
            moa_mm = st.number_input("Melon Max Spend", value=_defs.get("moa_mm", 0.0), min_value=0.0, step=100.0, format="%.2f", key="moa_spend_mm")

        if st.button("Save Budget as Defaults", key="save_budget_defaults"):
            st.session_state["_default_budgets"] = {
                "legacy_google": legacy_google, "legacy_ms": legacy_ms, "legacy_mm": legacy_mm,
                "moa_google": moa_google, "moa_ms": moa_ms, "moa_mm": moa_mm,
            }
            st.success("Budget defaults saved for this session.")

        st.markdown("---")
        cfg_col3, cfg_col4, cfg_col5 = st.columns(3)

        with cfg_col3:
            st.markdown("**Lead Types**")
            include_quote_starts = st.checkbox("Include Quote Starts", value=True, key="include_qs")
            include_phone_clicks = st.checkbox("Include Phone Clicks", value=True, key="include_phone")
            include_sms_clicks = st.checkbox("Include SMS Clicks", value=True, key="include_sms")
            if not (include_quote_starts or include_phone_clicks or include_sms_clicks):
                st.warning("At least one lead type must be selected!")

        with cfg_col4:
            st.markdown("**Display Options**")
            hide_unknown = st.checkbox("Hide 'Unknown' platform", False, key="gf_hide_unknown")
            exclude_listings_from_totals = st.checkbox("Exclude 'Listings' from TOTAL rows", False, key="exclude_listings_totals")

        with cfg_col5:
            st.markdown("**Export Options**")
            spend_col = st.text_input("Spend column name", placeholder="e.g., Spend, Cost", key="sb_spend_col")
            csv_style = st.radio("CSV number style", options=["Raw numbers", "With $ and % symbols"], index=0, key="sb_csv_style")

    # Track file changes to force rerun on change
    current_files = {
        'legacy': up_legacy.name if up_legacy else None,
        'moa': up_moa.name if up_moa else None,
        'legacy_id': id(up_legacy) if up_legacy else None,
        'moa_id': id(up_moa) if up_moa else None
    }
    
    if "previous_files" not in st.session_state:
        st.session_state.previous_files = current_files
    elif st.session_state.previous_files != current_files:
        # Files changed - clear any cached data
        st.session_state.previous_files = current_files
        # Clear domain filter state to force reset
        if 'flt_domains_list' in st.session_state:
            del st.session_state['flt_domains_list']
    
    
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
            for level, msg in validate_upload(df_legacy, up_legacy.name):
                getattr(st, level)(msg)
            df_legacy = df_legacy.copy()
            df_legacy["agency"] = "Legacy"
            dfs.append(df_legacy)

    if up_moa:
        df_moa = load_uploaded(up_moa)
        if df_moa is not None:
            for level, msg in validate_upload(df_moa, up_moa.name):
                getattr(st, level)(msg)
            df_moa = df_moa.copy()
            df_moa["agency"] = "MOA"
            dfs.append(df_moa)
    
    if not dfs:
        st.info("Upload at least one file (Legacy or MOA) to begin.")
    else:
        df_in = pd.concat(dfs, ignore_index=True)
        
        # Enrich with Product/UTM from mapping if available
        if 'tab1_mapping' in st.session_state and st.session_state.tab1_mapping is not None:
            mapping_df = st.session_state.tab1_mapping
            
            # The mapping has Campaign, Ad group, Product, and UTM columns
            # UTM column contains tracking codes like MLGD172-1R that match Campaign IDs in stats
            campaign_col_raw = get_col(df_in, ["campaign_ids", "campaign ids", "campaign_id", "campaign id", "campaign"])
            
            if campaign_col_raw and 'UTM' in mapping_df.columns:
                # Clean MD5 hashes from Campaign IDs
                def clean_campaign_id(campaign_id):
                    if pd.isna(campaign_id):
                        return None
                    campaign_str = str(campaign_id).strip()
                    match = re.match(r'^[0-9A-Fa-f]{32}(.+)$', campaign_str)
                    if match:
                        return match.group(1)
                    return campaign_str
                
                df_in['_cleaned_campaign_id'] = df_in[campaign_col_raw].apply(clean_campaign_id)
                
                # Create mapping dict: UTM -> Product
                # Clean UTM values in mapping
                mapping_df['_clean_utm'] = mapping_df['UTM'].fillna('')
                
                # Create a function to match Campaign IDs to Products via platform + campaign number
                # Debug tracking
                match_attempts = []
                
                def match_product(campaign_id):
                    """
                    Match Campaign ID to Product via platform + campaign number extraction.
                    Examples:
                      MLGDF172-001HVT1 -> Google + 172 -> match GD172 or MLGD172 -> Renters
                      MLBDF172-001RE2 -> Microsoft + 172 -> match BD172 or MLBD172 -> Renters
                      MLQSAM -> Melon Max Auto -> match MLQS...AM
                    """
                    if pd.isna(campaign_id):
                        return None

                    campaign_str = str(campaign_id).strip().upper()

                    # Detect platform + device from known prefixes (most specific first)
                    # Campaign IDs look like: MLGDF172-001HVT1, MLBM001-1, MLQSAM, GD001, GM001
                    platform_device = ''
                    for prefix in ['MLSGD', 'MLSGM', 'MLSBD', 'MLSBM',
                                   'MLGD', 'MLGM', 'MLBD', 'MLBM',
                                   'GD', 'GM', 'BD', 'BM']:
                        if prefix in campaign_str:
                            # Map to the short UTM prefix form (GD, GM, BD, BM)
                            platform_device = prefix[-2:]  # Last 2 chars: GD, GM, BD, BM
                            break

                    # Handle Melon Max separately
                    if 'MLQS' in campaign_str or campaign_str.startswith('QS'):
                        if 'AM' in campaign_str or 'AD' in campaign_str or 'AT' in campaign_str:
                            return 'Auto'
                        if 'HM' in campaign_str or 'HD' in campaign_str or 'HT' in campaign_str:
                            return 'Home'
                        return None

                    # Extract the campaign number (3-digit code like 172, 001, 170)
                    # Look for the number right after the platform+device prefix
                    # e.g., MLGDF172 -> 172, MLBM001 -> 001, GD001 -> 001
                    num_match = re.search(r'(?:MLG|MLB|MLSG|MLSB|[GB])[DM]F?(\d{3})', campaign_str)
                    if not num_match:
                        # Fallback: look for a 3-digit number in the ID
                        num_match = re.search(r'(\d{3})', campaign_str)
                    if not num_match:
                        return None

                    campaign_num = num_match.group(1)

                    # Build search patterns in priority order (most specific first)
                    search_patterns = []
                    if platform_device:
                        # e.g., GD172, BD001 — exact platform+device match
                        search_patterns.append(f"{platform_device}{campaign_num}")
                        # Try the other device variant (D<->M)
                        alt_device = platform_device[0] + ('M' if platform_device[1] == 'D' else 'D')
                        search_patterns.append(f"{alt_device}{campaign_num}")
                    # Cross-platform fallback: Microsoft campaigns often share
                    # the same campaign numbers as Google (e.g., 172 = Renters
                    # regardless of platform). Try Google UTM patterns too.
                    if platform_device and platform_device[0] == 'B':
                        search_patterns.append(f"G{platform_device[1]}{campaign_num}")
                        alt_gd = 'M' if platform_device[1] == 'D' else 'D'
                        search_patterns.append(f"G{alt_gd}{campaign_num}")

                    # Try each pattern — use startswith match on UTM, not substring
                    for pattern in search_patterns:
                        matching_utms = mapping_df[
                            mapping_df['_clean_utm'].str.upper().str.startswith(pattern, na=False)
                        ]
                        if len(matching_utms) > 0:
                            product = matching_utms.iloc[0]['Product']
                            if len(match_attempts) < 20:
                                match_attempts.append({
                                    'Campaign ID': campaign_str,
                                    'Pattern': pattern,
                                    'Product': product,
                                    'Matched': 'YES'
                                })
                            return product

                    # Track failed match
                    if len(match_attempts) < 20:
                        match_attempts.append({
                            'Campaign ID': campaign_str,
                            'Pattern': ', '.join(search_patterns) if search_patterns else campaign_num,
                            'Product': None,
                            'Matched': 'NO'
                        })

                    return None
                
                # Apply matching function
                df_in['Product'] = df_in['_cleaned_campaign_id'].apply(match_product)
                
                enriched_count = df_in['Product'].notna().sum()
                total_with_campaign = df_in['_cleaned_campaign_id'].notna().sum()
                
                # Store Product enrichment results for debug table
                st.session_state.product_enrichment_count = enriched_count
                st.session_state.product_enrichment_total = total_with_campaign
                
                # Store matching attempts for consolidated debug report
                st.session_state.product_matching_debug = match_attempts
                
                # Clean up temporary column
                df_in = df_in.drop(columns=['_cleaned_campaign_id'])
        
        # Store file loading info for debug table
        st.session_state.files_loaded = len(dfs)
        st.session_state.total_rows = len(df_in)
        if "agency" in df_in.columns:
            agency_counts = df_in["agency"].value_counts()
            st.session_state.agency_distribution = agency_counts.to_dict()
    
    
        # Sidebar Filters
        with st.sidebar:
            st.markdown("---")
            st.subheader("Filters")
            
            # Domain filter
            domain_col = get_col(df_in, ["domain", "site", "hostname"])
            if domain_col:
                all_domains = sorted([str(x) for x in df_in[domain_col].dropna().unique()])
                
                # Initialize or update selected domains
                # If this is the first time or domains changed, select all
                if "flt_domains_list" not in st.session_state or set(st.session_state.get("flt_domains_list", [])) != set(all_domains):
                    st.session_state.flt_domains_list = all_domains
                
                sel_domains = st.multiselect(
                    "Filter by domain:", 
                    options=all_domains, 
                    default=st.session_state.flt_domains_list,
                    key="flt_domains"
                )
                
                # Update session state
                st.session_state.flt_domains_list = sel_domains
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
                exclude_listings_from_totals=exclude_listings_from_totals,
                include_qs=include_quote_starts,
                include_phone=include_phone_clicks,
                include_sms=include_sms_clicks
            )
            
            # Store campaign-level stats in session state for Tab 2
            # Aggregate by campaign to get conversions and CPL
            if not df_in.empty:
                campaign_col = get_col(df_in, ["campaign_ids", "campaign ids", "campaign_id", "campaign id", "campaign"])
                if campaign_col:
                    # Get column names that exist
                    qs_col = get_col(df_in, ["quote_starts", "quote starts", "quote start", "qs"])
                    phone_col = get_col(df_in, ["phone_clicks", "phone clicks", "phone click"])
                    sms_col = get_col(df_in, ["sms_clicks", "sms clicks", "sms click"])
                    
                    # Build aggregation dict only for columns that exist
                    agg_dict = {}
                    if qs_col:
                        agg_dict[qs_col] = 'sum'
                    if phone_col:
                        agg_dict[phone_col] = 'sum'
                    if sms_col:
                        agg_dict[sms_col] = 'sum'
                    
                    # Only aggregate if we have at least one conversion column
                    if agg_dict:
                        # Clean Campaign IDs: Remove MD5 hash prefix (32 hex chars at start)
                        # Example: "149084BF90E9D889F9C32F2478957BE5MLQSHM" -> "MLQSHM"
                        def clean_campaign_id(campaign_id):
                            """Remove MD5 hash prefix from campaign ID if present."""
                            if pd.isna(campaign_id):
                                return campaign_id
                            campaign_str = str(campaign_id).strip()
                            # Check if starts with 32 hex characters (MD5 hash)
                            match = re.match(r'^[0-9A-Fa-f]{32}(.+)$', campaign_str)
                            if match:
                                return match.group(1)  # Return everything after the hash
                            return campaign_str  # Return as-is if no hash found
                        
                        # Create a cleaned campaign ID column for grouping
                        df_in['_cleaned_campaign_id'] = df_in[campaign_col].apply(clean_campaign_id)
                        
                        # Check if Domain column exists (for URL matching)
                        domain_col = get_col(df_in, ["domain"])
                        
                        # Group by cleaned campaign ID, domain (if available), and agency to preserve office information
                        group_cols = ['_cleaned_campaign_id', 'agency']
                        if domain_col:
                            group_cols.insert(1, domain_col)  # Add domain between campaign and agency
                        
                        campaign_stats = df_in.groupby(group_cols).agg(agg_dict).fillna(0)
                        
                        # Calculate total conversions based on what user included
                        campaign_stats['Total Conversions'] = 0
                        if qs_col and include_quote_starts and qs_col in campaign_stats.columns:
                            campaign_stats['Total Conversions'] += campaign_stats[qs_col]
                        if phone_col and include_phone_clicks and phone_col in campaign_stats.columns:
                            campaign_stats['Total Conversions'] += campaign_stats[phone_col]
                        if sms_col and include_sms_clicks and sms_col in campaign_stats.columns:
                            campaign_stats['Total Conversions'] += campaign_stats[sms_col]
                        
                        # Store in session state with standardized column names
                        campaign_stats_reset = campaign_stats.reset_index()
                        
                        # Rename columns to standard names
                        rename_map = {
                            '_cleaned_campaign_id': 'Campaign',
                            'agency': 'Office'  # Rename agency to Office for clarity
                        }
                        if domain_col:
                            rename_map[domain_col] = 'Domain'
                        if qs_col:
                            rename_map[qs_col] = 'Quote Starts'
                        if phone_col:
                            rename_map[phone_col] = 'Phone Clicks'
                        if sms_col:
                            rename_map[sms_col] = 'SMS Clicks'
                        
                        campaign_stats_reset = campaign_stats_reset.rename(columns=rename_map)
                        
                        # Ensure all expected columns exist (fill with 0 if missing)
                        for col in ['Quote Starts', 'Phone Clicks', 'SMS Clicks']:
                            if col not in campaign_stats_reset.columns:
                                campaign_stats_reset[col] = 0
                        
                        # Add Platform detection using existing classify_platform function
                        # For stats data, we don't have traffic source, so pass empty string
                        campaign_stats_reset['Platform'] = campaign_stats_reset['Campaign'].apply(
                            lambda x: classify_platform(str(x), '')
                        )
                        
                        # Try to extract domain from stats data to identify the agent
                        # Look for URL columns in the stats report
                        agent_domain = None
                        url_cols = [col for col in df_in.columns if 'url' in col.lower() or 'link' in col.lower() or 'landing' in col.lower()]
                        
                        if url_cols:
                            # Try to extract domain from first URL column
                            for url_col in url_cols:
                                sample_urls = df_in[url_col].dropna().head(5)
                                for url in sample_urls:
                                    if pd.notna(url) and 'http' in str(url).lower():
                                        match = re.search(r'https?://(?:www\.)?([^/?]+)', str(url))
                                        if match:
                                            agent_domain = match.group(1)
                                            break
                                if agent_domain:
                                    break
                        
                        # Determine which file(s) were uploaded
                        uploaded_files = []
                        if up_legacy:
                            uploaded_files.append(up_legacy.name)
                        if up_moa:
                            uploaded_files.append(up_moa.name)
                        stats_file_name = " + ".join(uploaded_files) if uploaded_files else "stats report"
                        
                        # Store domain for matching in Tab 2
                        st.session_state.campaign_stats = campaign_stats_reset
                        st.session_state.stats_agent_domain = agent_domain  # Store the domain
                        st.session_state.stats_file_uploaded = stats_file_name  # Track which file this is from
                        
                        # Store Tab 1 processing info for debug report
                        if 'debug_info' not in st.session_state:
                            st.session_state.debug_info = {}
                        
                        st.session_state.debug_info['tab1_campaign_col_detected'] = campaign_col
                        st.session_state.debug_info['tab1_campaigns_processed'] = len(campaign_stats_reset)
                        st.session_state.debug_info['tab1_sample_campaigns'] = campaign_stats_reset['Campaign'].head(10).tolist() if 'Campaign' in campaign_stats_reset.columns else []
                        st.session_state.debug_info['tab1_domain_detected'] = agent_domain
                        
                        # Store for consolidated debug table
                        st.session_state.campaign_stats_count = len(campaign_stats_reset)

            
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

        def render_agency_detail(agency_name):
            """Render the full detail view for a single agency inside a sub-tab."""
            ag_mask = df_in["agency"] == agency_name
            if not ag_mask.any():
                st.info(f"No data uploaded for {agency_name}.")
                return

            sub_df = df_in[ag_mask].copy()
            sub_spends = {agency_name: spends[agency_name]}
            single = analyze(sub_df, sub_spends, spend_column=spend_col.strip() or None, hide_unknown=hide_unknown, add_device_column=add_device_column, exclude_listings_from_totals=exclude_listings_from_totals, include_qs=include_quote_starts, include_phone=include_phone_clicks, include_sms=include_sms_clicks)
                
            # Platform Overview
            with st.expander(f"{agency_name}: Platform Overview (Platform CPL + TOTAL)", expanded=True):
                # Tracking disclaimer
                st.info("ℹ️ **Note:** \"Unknown\" or \"Other\" classifications represent leads that MySFDomain's tracking software was unable to categorize. While the majority of leads are tracked correctly, MySFDomain's platform has some limitations in lead categorization that affect a small percentage of data.")
                
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
                                        "Mobile": "#47B74F",
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
                                        "Mobile": "#47B74F",
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
                                        "Mobile": "#47B74F",
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
                                    color_continuous_scale=["#eef7ef", "#47B74F"] if metric_col != "cpl_platform" else ["#47B74F", "#efd568", "#f28c82"],
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
                                    color_discrete_sequence=["#47B74F"]
                                )
                            else:  # Area
                                fig = px.area(
                                    plat_agg,
                                    x="platform",
                                    y=metric_col,
                                    title=f"{agency_name}: {metric_to_show} by Platform",
                                    labels={"platform": "Platform", metric_col: metric_to_show},
                                    color_discrete_sequence=["#47B74F"]
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
                
                # Currency formatting is now handled by display_table_with_total
                # (removed redundant formatting here to avoid double-formatting)
                
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
                    
            # Platform × Landing Page × UTM
            with st.expander(f"{agency_name}: Platform × Landing Page × UTM + TOTAL", expanded=False):
                lpu = single.get("platform_lp_utm")
                if lpu is not None and not lpu.empty:
                    lpu_filters = {}
                    if "device" in lpu.columns:
                        lpu_filters["device"] = f"{agency_name}_lpu_device"
                    if "platform" in lpu.columns:
                        lpu_filters["platform"] = f"{agency_name}_lpu_platform"
                    if "landing_page" in lpu.columns:
                        lpu_filters["landing_page"] = f"{agency_name}_lpu_lp"
                    if "utm" in lpu.columns:
                        lpu_filters["utm"] = f"{agency_name}_lpu_utm"
                    display_table_with_total(lpu, "utm", "TOTAL", filters=lpu_filters if lpu_filters else None)
                else:
                    st.info("No Campaign ID or Landing Page column found — table unavailable.")

            # Landing Page vs UTM Product Mismatch
            with st.expander(f"{agency_name}: Landing Page vs UTM Product Mismatch", expanded=False):
                mm = single.get("product_mismatch")
                if mm is not None and not mm.empty:
                    st.warning(f"⚠️ **{len(mm) - 1} row(s)** where the landing page product differs from the UTM/campaign number product. The landing page is used as the primary classification.")
                    # Drop agency column if present (redundant in per-agency view)
                    mm_display = mm.drop(columns=["agency"], errors="ignore")
                    display_table_with_total(mm_display, "utm_product", "TOTAL")
                else:
                    st.success("No mismatches found — landing page and UTM products agree on all leads.")

            # By Product
            with st.expander(f"{agency_name}: By Product (All Platforms)", expanded=False):
                # Tracking disclaimer
                st.info("ℹ️ **Note:** \"Other\" in Product classifications represents leads where MySFDomain's tracking software was unable to identify the insurance product type. While the majority of leads are tracked correctly, MySFDomain's platform has some limitations in product categorization that affect a small percentage of data.")

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
                                color_discrete_sequence=MELON_COLORS["primary"],
                                hole=0.4 if prod_chart_type == "Donut" else 0
                            )
                            fig_pie.update_traces(
                                textposition='inside',
                                textinfo='percent+label',
                                hovertemplate=f'<b>%{{label}}</b><br>{prod_metric}: %{{value:,.0f}}<br>Share: %{{percent}}<extra></extra>'
                            )
                            fig_pie.update_layout(
                                height=500,
                                margin=dict(l=20, r=20, t=60, b=20),
                                showlegend=True,
                                legend=dict(
                                    orientation="v",
                                    yanchor="middle",
                                    y=0.5,
                                    xanchor="left",
                                    x=1.05
                                )
                            )
                            st.plotly_chart(fig_pie, use_container_width=True)
                        else:  # Bar
                            fig_bar = px.bar(
                                prod_agg,
                                x="product",
                                y=prod_metric_col,
                                title=f"{agency_name}: {prod_metric} by Product",
                                labels={"product": "Product", prod_metric_col: prod_metric},
                                color=prod_metric_col,
                                color_continuous_scale=["#eef7ef", "#47B74F"],
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
                                color_discrete_sequence=MELON_COLORS["primary"],
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
                                color_discrete_sequence=MELON_COLORS["primary"],
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
                                color_discrete_sequence=MELON_COLORS["primary"],
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
                                color_discrete_sequence=MELON_COLORS["primary"]
                            )
                        elif bpp_chart_type == "Heatmap":
                            # Pivot for heatmap
                            heatmap_data = bpp_agg.pivot(index="product", columns="platform", values=bpp_metric_col)
                            fig_bpp = px.imshow(
                                heatmap_data,
                                title=f"{agency_name}: {bpp_metric} Heatmap",
                                labels=dict(x="Platform", y="Product", color=bpp_metric),
                                color_continuous_scale=["#eef7ef", "#efd568", "#47B74F", "#0f5340"],
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
                                color_discrete_sequence=MELON_COLORS["primary"]
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
                
        # ========== KPI DASHBOARD ==========
        # Date range from filenames
        date_parts = []
        for f in [up_legacy, up_moa]:
            if f:
                s, e = extract_date_range_from_filename(f.name)
                if s and e:
                    date_parts.append((s, e))
        if date_parts:
            from datetime import datetime as _dt
            s = min(d[0] for d in date_parts)
            e = max(d[1] for d in date_parts)
            try:
                s_fmt = _dt.strptime(s, "%Y-%m-%d").strftime("%b %d, %Y")
                e_fmt = _dt.strptime(e, "%Y-%m-%d").strftime("%b %d, %Y")
                st.markdown(f"### Performance Summary &nbsp; <span style='font-size:0.6em;color:#666;'>Data Period: {s_fmt} – {e_fmt}</span>", unsafe_allow_html=True)
            except ValueError:
                st.markdown("### Performance Summary")
        else:
            st.markdown("### Performance Summary")
        kpi_cols = st.columns(4)

        plat_overview_kpi = results["platform_overview"]
        total_row_kpi = plat_overview_kpi[plat_overview_kpi["platform"] == "TOTAL"]

        total_leads_kpi = int(pd.to_numeric(total_row_kpi["leads"], errors="coerce").iloc[0]) if not total_row_kpi.empty else 0
        total_spend_kpi = float(pd.to_numeric(total_row_kpi.get("spend", pd.Series([0])), errors="coerce").iloc[0]) if not total_row_kpi.empty and "spend" in total_row_kpi.columns else 0
        overall_cpl_kpi = total_spend_kpi / total_leads_kpi if total_leads_kpi > 0 else 0

        plat_for_top = plat_overview_kpi[~plat_overview_kpi["platform"].isin(["TOTAL", "Unknown", "Listings"])].copy()
        plat_for_top["leads"] = pd.to_numeric(plat_for_top["leads"], errors="coerce").fillna(0)
        top_platform_name = plat_for_top.loc[plat_for_top["leads"].idxmax(), "platform"] if not plat_for_top.empty and plat_for_top["leads"].sum() > 0 else "N/A"

        prod_for_top = results["by_product_total"]
        prod_for_top = prod_for_top[prod_for_top["product"] != "TOTAL"].copy()
        prod_for_top["leads"] = pd.to_numeric(prod_for_top["leads"], errors="coerce").fillna(0)
        top_product_name = prod_for_top.loc[prod_for_top["leads"].idxmax(), "product"] if not prod_for_top.empty and prod_for_top["leads"].sum() > 0 else "N/A"

        with kpi_cols[0]:
            st.metric("Total Leads", f"{total_leads_kpi:,}")
        with kpi_cols[1]:
            st.metric("Overall CPL", f"${overall_cpl_kpi:.2f}" if overall_cpl_kpi > 0 else "N/A")
        with kpi_cols[2]:
            st.metric("Top Platform", top_platform_name)
        with kpi_cols[3]:
            st.metric("Top Product", top_product_name)

        st.markdown("---")

        # ========== SUB-TABS ==========
        if has_legacy_file and has_moa_file:
            tab_comp, tab_legacy, tab_moa, tab_optimizer, tab_export = st.tabs([
                "🔄 Agency Comparison",
                "🏢 Legacy Detail",
                "🏢 MOA Detail",
                "💡 Budget Optimizer",
                "⬇️ Export"
            ])
        elif has_legacy_file:
            tab_legacy, tab_optimizer, tab_export = st.tabs([
                "🏢 Legacy Detail",
                "💡 Budget Optimizer",
                "⬇️ Export"
            ])
            tab_comp = None
            tab_moa = None
        else:
            tab_moa, tab_optimizer, tab_export = st.tabs([
                "🏢 MOA Detail",
                "💡 Budget Optimizer",
                "⬇️ Export"
            ])
            tab_comp = None
            tab_legacy = None

        # ---- Agency Detail Tabs ----
        if has_legacy_file:
            with tab_legacy:
                render_agency_detail("Legacy")

        if has_moa_file:
            with tab_moa:
                render_agency_detail("MOA")

        # ---- Agency Comparison Tab ----
        if has_legacy_file and has_moa_file and tab_comp is not None:
            with tab_comp:
                st.markdown("### Head-to-Head Performance Analysis")
            
                # Get agency-specific data
                agency_overview = results["agency_overview"].copy()
                platform_agency = results["platform_agency"].copy()
            
                # Remove TOTAL rows for comparison
                agency_data = agency_overview[agency_overview["agency"] != "TOTAL"].copy()
                platform_agency_data = platform_agency[platform_agency["agency"] != "TOTAL"].copy()
            
                if not agency_data.empty and len(agency_data) >= 2:
                    # Aggregate by agency (in case device column exists)
                    if "device" in agency_data.columns:
                        agg_dict = {
                            "quote_starts": "sum",
                            "phone_clicks": "sum", 
                            "sms_clicks": "sum",
                            "leads": "sum"
                        }
                        # Add spend if it exists
                        if "spend" in agency_data.columns:
                            agg_dict["spend"] = "sum"
                    
                        agency_summary = agency_data.groupby("agency", as_index=False).agg(agg_dict)
                    else:
                        agency_summary = agency_data.copy()
                
                    # Calculate totals for percentages
                    total_leads = agency_summary["leads"].sum()
                
                    # Create comparison metrics
                    col1, col2, col3 = st.columns(3)
                
                    legacy_row = agency_summary[agency_summary["agency"] == "Legacy"]
                    moa_row = agency_summary[agency_summary["agency"] == "MOA"]
                
                    if not legacy_row.empty and not moa_row.empty:
                        legacy_leads = int(legacy_row["leads"].iloc[0])
                        moa_leads = int(moa_row["leads"].iloc[0])
                    
                        legacy_pct = (legacy_leads / total_leads * 100) if total_leads > 0 else 0
                        moa_pct = (moa_leads / total_leads * 100) if total_leads > 0 else 0
                    
                        with col1:
                            st.metric(
                                "**Legacy Total Leads**",
                                f"{legacy_leads:,}",
                                f"{legacy_pct:.1f}% of total"
                            )
                    
                        with col2:
                            st.metric(
                                "**MOA Total Leads**",
                                f"{moa_leads:,}",
                                f"{moa_pct:.1f}% of total"
                            )
                    
                        with col3:
                            diff = moa_leads - legacy_leads
                            diff_pct = ((moa_leads - legacy_leads) / legacy_leads * 100) if legacy_leads > 0 else 0
                            st.metric(
                                "**Difference**",
                                f"{abs(diff):,} leads",
                                f"{diff_pct:+.1f}%",
                                delta_color="normal" if diff > 0 else "inverse"
                            )
                
                    st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)
                
                    # Platform-by-Platform Comparison
                    st.markdown("#### Platform Performance Comparison")
                
                    if not platform_agency_data.empty:
                        # Aggregate by platform and agency
                        if "device" in platform_agency_data.columns:
                            platform_comp = platform_agency_data.groupby(["platform", "agency"], as_index=False).agg({
                                "leads": "sum",
                                "spend": "sum"
                            })
                        else:
                            platform_comp = platform_agency_data[["platform", "agency", "leads", "spend"]].copy()
                    
                        # Calculate CPL
                        platform_comp["cpl"] = platform_comp.apply(
                            lambda r: r["spend"] / r["leads"] if r["leads"] > 0 else np.nan,
                            axis=1
                        )
                    
                        # Pivot for comparison
                        comparison_df = platform_comp.pivot(index="platform", columns="agency", values=["leads", "spend", "cpl"])
                        comparison_df.columns = [f"{col[1]}_{col[0]}" for col in comparison_df.columns]
                        comparison_df = comparison_df.reset_index()
                    
                        # Calculate differences
                        if "Legacy_leads" in comparison_df.columns and "MOA_leads" in comparison_df.columns:
                            comparison_df["Lead_Difference"] = comparison_df["MOA_leads"] - comparison_df["Legacy_leads"]
                            comparison_df["Lead_Diff_%"] = comparison_df.apply(
                                lambda r: ((r["MOA_leads"] - r["Legacy_leads"]) / r["Legacy_leads"] * 100) 
                                if r["Legacy_leads"] > 0 else np.nan,
                                axis=1
                            )
                    
                        if "Legacy_cpl" in comparison_df.columns and "MOA_cpl" in comparison_df.columns:
                            comparison_df["CPL_Difference"] = comparison_df["MOA_cpl"] - comparison_df["Legacy_cpl"]
                            comparison_df["CPL_Winner"] = comparison_df.apply(
                                lambda r: "MOA ✓" if pd.notna(r["MOA_cpl"]) and pd.notna(r["Legacy_cpl"]) and r["MOA_cpl"] < r["Legacy_cpl"] 
                                else "Legacy ✓" if pd.notna(r["MOA_cpl"]) and pd.notna(r["Legacy_cpl"]) 
                                else "—",
                                axis=1
                            )
                    
                        # Display table
                        display_cols = ["platform"]
                        if "Legacy_leads" in comparison_df.columns:
                            display_cols.extend(["Legacy_leads", "MOA_leads", "Lead_Difference", "Lead_Diff_%"])
                        if "Legacy_cpl" in comparison_df.columns:
                            display_cols.extend(["Legacy_cpl", "MOA_cpl", "CPL_Difference", "CPL_Winner"])
                    
                        display_df = comparison_df[display_cols].copy()
                    
                        # Format for display
                        display_df = display_df.rename(columns={
                            "platform": "Platform",
                            "Legacy_leads": "Legacy Leads",
                            "MOA_leads": "MOA Leads",
                            "Lead_Difference": "Lead Diff",
                            "Lead_Diff_%": "Lead Diff %",
                            "Legacy_cpl": "Legacy CPL",
                            "MOA_cpl": "MOA CPL",
                            "CPL_Difference": "CPL Diff",
                            "CPL_Winner": "Lower CPL"
                        })
                    
                        # Apply formatting
                        for col in ["Legacy Leads", "MOA Leads", "Lead Diff"]:
                            if col in display_df.columns:
                                display_df[col] = display_df[col].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
                    
                        for col in ["Legacy CPL", "MOA CPL", "CPL Diff"]:
                            if col in display_df.columns:
                                display_df[col] = display_df[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) and x > 0 else "—")
                    
                        if "Lead Diff %" in display_df.columns:
                            display_df["Lead Diff %"] = display_df["Lead Diff %"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "—")
                    
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                        # Comparison Chart
                        if PLOTLY_AVAILABLE:
                            st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                        
                            chart_type = st.radio(
                                "Chart Type:",
                                ["Leads Comparison", "CPL Comparison", "Spend Comparison"],
                                horizontal=True,
                                key="agency_comp_chart_type"
                            )
                        
                            # Prepare data for chart
                            chart_data = platform_comp.copy()
                        
                            if chart_type == "Leads Comparison":
                                fig = px.bar(
                                    chart_data,
                                    x="platform",
                                    y="leads",
                                    color="agency",
                                    barmode="group",
                                    title="Lead Volume by Platform: Legacy vs. MOA",
                                    labels={"platform": "Platform", "leads": "Leads", "agency": "Agency"},
                                    color_discrete_map={"Legacy": "#114e38", "MOA": "#47B74F"}
                                )
                                fig.update_traces(texttemplate='%{y:,}', textposition='outside')
                            
                            elif chart_type == "CPL Comparison":
                                chart_data_cpl = chart_data[chart_data["cpl"] > 0].copy()
                                fig = px.bar(
                                    chart_data_cpl,
                                    x="platform",
                                    y="cpl",
                                    color="agency",
                                    barmode="group",
                                    title="Cost Per Lead by Platform: Legacy vs. MOA",
                                    labels={"platform": "Platform", "cpl": "CPL", "agency": "Agency"},
                                    color_discrete_map={"Legacy": "#114e38", "MOA": "#47B74F"}
                                )
                                fig.update_traces(texttemplate='$%{y:.2f}', textposition='outside')
                                fig.update_yaxes(tickprefix="$")
                            
                            else:  # Spend Comparison
                                chart_data_spend = chart_data[chart_data["spend"] > 0].copy()
                                fig = px.bar(
                                    chart_data_spend,
                                    x="platform",
                                    y="spend",
                                    color="agency",
                                    barmode="group",
                                    title="Ad Spend by Platform: Legacy vs. MOA",
                                    labels={"platform": "Platform", "spend": "Spend", "agency": "Agency"},
                                    color_discrete_map={"Legacy": "#114e38", "MOA": "#47B74F"}
                                )
                                fig.update_traces(texttemplate='$%{y:,.0f}', textposition='outside')
                                fig.update_yaxes(tickprefix="$")
                        
                            fig.update_layout(
                                height=450,
                                margin=dict(l=20, r=20, t=40, b=20),
                                showlegend=True,
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                        
                            st.plotly_chart(fig, use_container_width=True)
                
                    # Key Insights
                    st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)
                    st.markdown("#### 💡 Key Insights")
                
                    insights = []
                
                    # Lead volume comparison
                    if not legacy_row.empty and not moa_row.empty:
                        if moa_leads > legacy_leads:
                            pct_more = ((moa_leads - legacy_leads) / legacy_leads * 100)
                            insights.append(f"📈 **MOA generated {pct_more:.1f}% more leads** than Legacy ({moa_leads:,} vs {legacy_leads:,})")
                        elif legacy_leads > moa_leads:
                            pct_more = ((legacy_leads - moa_leads) / moa_leads * 100)
                            insights.append(f"📈 **Legacy generated {pct_more:.1f}% more leads** than MOA ({legacy_leads:,} vs {moa_leads:,})")
                        else:
                            insights.append(f"⚖️ **Both agencies generated equal leads** ({legacy_leads:,} each)")
                
                    # Platform winners
                    if "CPL_Winner" in comparison_df.columns:
                        legacy_wins = (comparison_df["CPL_Winner"] == "Legacy ✓").sum()
                        moa_wins = (comparison_df["CPL_Winner"] == "MOA ✓").sum()
                    
                        if moa_wins > legacy_wins:
                            insights.append(f"🎯 **MOA has better CPL on {moa_wins} platform(s)**, Legacy on {legacy_wins}")
                        elif legacy_wins > moa_wins:
                            insights.append(f"🎯 **Legacy has better CPL on {legacy_wins} platform(s)**, MOA on {moa_wins}")
                
                    if insights:
                        for insight in insights:
                            st.markdown(f"- {insight}")
                    else:
                        st.info("Upload data for both agencies to see comparison insights.")
                
                    # ========== PERFORMANCE ANALYSIS & RECOMMENDATIONS ==========
                    st.markdown('<div class="space-lg"></div>', unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown("### 🔍 Performance Analysis & Recommendations")
                
                    # Calculate key metrics for analysis
                    if not legacy_row.empty and not moa_row.empty:
                        legacy_total = int(legacy_row["leads"].iloc[0])
                        moa_total = int(moa_row["leads"].iloc[0])
                    
                        # Get spend data from agency_summary (which has aggregated spend if device column existed)
                        if "spend" in agency_summary.columns and "leads" in agency_summary.columns:
                            legacy_spend = agency_summary[agency_summary["agency"] == "Legacy"]["spend"].sum() if "Legacy" in agency_summary["agency"].values else 0
                            moa_spend = agency_summary[agency_summary["agency"] == "MOA"]["spend"].sum() if "MOA" in agency_summary["agency"].values else 0
                        
                            legacy_cpl = legacy_spend / legacy_total if legacy_total > 0 else 0
                            moa_cpl = moa_spend / moa_total if moa_total > 0 else 0
                        
                            # Determine which is less efficient
                            less_efficient_agency = "Legacy" if legacy_cpl > moa_cpl else "MOA"
                            more_efficient_agency = "MOA" if legacy_cpl > moa_cpl else "Legacy"
                            less_efficient_cpl = legacy_cpl if less_efficient_agency == "Legacy" else moa_cpl
                            more_efficient_cpl = moa_cpl if more_efficient_agency == "MOA" else legacy_cpl
                            cpl_diff = abs(legacy_cpl - moa_cpl)
                            cpl_pct_diff = (cpl_diff / more_efficient_cpl * 100) if more_efficient_cpl > 0 else 0
                        
                            # Show summary
                            st.markdown(f"""
                            **Cost Efficiency Overview:**
                            - **{less_efficient_agency}** CPL: **${less_efficient_cpl:.2f}** ({cpl_pct_diff:.1f}% higher than {more_efficient_agency})
                            - **{more_efficient_agency}** CPL: **${more_efficient_cpl:.2f}**
                            - **Gap:** ${cpl_diff:.2f} per lead
                            - **Volume Context:** {less_efficient_agency} = {legacy_total if less_efficient_agency == 'Legacy' else moa_total:,} leads (${legacy_spend if less_efficient_agency == 'Legacy' else moa_spend:,.2f} spend) • {more_efficient_agency} = {moa_total if more_efficient_agency == 'MOA' else legacy_total:,} leads (${moa_spend if more_efficient_agency == 'MOA' else legacy_spend:,.2f} spend)
                            """)
                        
                            # Platform CPL analysis
                            st.markdown(f"#### 🎯 Where is {less_efficient_agency} less efficient?")
                        
                            recommendations = []
                        
                            if not platform_agency_data.empty and "spend" in platform_agency_data.columns:
                                plat_comparison = platform_agency_data.copy()
                                if "device" in plat_comparison.columns:
                                    plat_comparison = plat_comparison.groupby(["platform", "agency"], as_index=False).agg({
                                        "leads": "sum",
                                        "spend": "sum"
                                    })
                            
                                # Calculate CPL per platform
                                plat_comparison["cpl"] = plat_comparison.apply(
                                    lambda r: r["spend"] / r["leads"] if r["leads"] > 0 else np.nan,
                                    axis=1
                                )
                            
                                # Pivot to compare CPLs
                                plat_pivot = plat_comparison.pivot(index="platform", columns="agency", values=["leads", "spend", "cpl"]).fillna(0)
                            
                                # Flatten column names
                                plat_pivot.columns = [f"{col[1]}_{col[0]}" for col in plat_pivot.columns]
                                plat_pivot = plat_pivot.reset_index()
                            
                                # Calculate CPL differences
                                if f"{less_efficient_agency}_cpl" in plat_pivot.columns and f"{more_efficient_agency}_cpl" in plat_pivot.columns:
                                    plat_pivot["cpl_diff"] = plat_pivot[f"{less_efficient_agency}_cpl"] - plat_pivot[f"{more_efficient_agency}_cpl"]
                                    plat_pivot["cpl_pct_diff"] = plat_pivot.apply(
                                        lambda r: ((r[f"{less_efficient_agency}_cpl"] - r[f"{more_efficient_agency}_cpl"]) / r[f"{more_efficient_agency}_cpl"] * 100) 
                                        if r[f"{more_efficient_agency}_cpl"] > 0 else 0,
                                        axis=1
                                    )
                                
                                    # Sort by biggest CPL difference
                                    plat_pivot = plat_pivot.sort_values("cpl_diff", ascending=False)
                                    biggest_cpl_gaps = plat_pivot[plat_pivot["cpl_diff"] > 0].head(3)
                                
                                    if not biggest_cpl_gaps.empty:
                                        st.markdown(f"**Platform Efficiency Gaps:**")
                                        for idx, row in biggest_cpl_gaps.iterrows():
                                            platform = row["platform"]
                                            less_eff_cpl = row[f"{less_efficient_agency}_cpl"]
                                            more_eff_cpl = row[f"{more_efficient_agency}_cpl"]
                                            cpl_gap = row["cpl_diff"]
                                            cpl_pct = row["cpl_pct_diff"]
                                            less_eff_leads = int(row[f"{less_efficient_agency}_leads"])
                                            more_eff_leads = int(row[f"{more_efficient_agency}_leads"])
                                            less_eff_spend = row[f"{less_efficient_agency}_spend"]
                                            more_eff_spend = row[f"{more_efficient_agency}_spend"]
                                        
                                            recommendations.append({
                                                "platform": platform,
                                                "cpl_gap": cpl_gap,
                                                "cpl_pct": cpl_pct,
                                                "less_eff_cpl": less_eff_cpl,
                                                "more_eff_cpl": more_eff_cpl,
                                                "less_eff_leads": less_eff_leads,
                                                "less_eff_spend": less_eff_spend
                                            })
                                        
                                            st.markdown(f"- **{platform}**: ${cpl_gap:.2f} higher CPL ({cpl_pct:.0f}% less efficient)")
                                            st.markdown(f"  - {less_efficient_agency}: ${less_eff_cpl:.2f} CPL ({less_eff_leads:,} leads @ ${less_eff_spend:,.2f})")
                                            st.markdown(f"  - {more_efficient_agency}: ${more_eff_cpl:.2f} CPL ({more_eff_leads:,} leads @ ${more_eff_spend:,.2f})")
                        
                            # Product CPL analysis
                            prod_comparison = results["product_agency"].copy()  # Use product_agency which has agency column
                            if "agency" in prod_comparison.columns:
                                prod_comp = prod_comparison[prod_comparison["product"] != "TOTAL"].copy()
                            
                                # Note: product data doesn't have spend, so skip CPL analysis
                                st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                                st.markdown(f"**Product Volume Context:**")
                                st.markdown("*(Product-level spend data not available for CPL calculation)*")
                            
                                if "device" in prod_comp.columns:
                                    prod_comp = prod_comp.groupby(["product", "agency"], as_index=False)["leads"].sum()
                            
                                prod_pivot = prod_comp.pivot(index="product", columns="agency", values="leads").fillna(0)
                            
                                if less_efficient_agency in prod_pivot.columns and more_efficient_agency in prod_pivot.columns:
                                    prod_pivot["Difference"] = prod_pivot[more_efficient_agency] - prod_pivot[less_efficient_agency]
                                    prod_pivot = prod_pivot.sort_values("Difference", ascending=False)
                                
                                    for product, row in prod_pivot.head(3).iterrows():
                                        less_eff_leads = int(row[less_efficient_agency])
                                        more_eff_leads = int(row[more_efficient_agency])
                                        st.markdown(f"- **{product}**: {less_efficient_agency} {less_eff_leads:,} leads • {more_efficient_agency} {more_eff_leads:,} leads")
                        
                            # Generate actionable recommendations
                            st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)
                            st.markdown(f"#### 💡 Recommended Actions for {less_efficient_agency}")
                        
                            if recommendations:
                                top_inefficiency = recommendations[0]
                            
                                # Calculate potential savings
                                potential_savings = top_inefficiency["less_eff_leads"] * (top_inefficiency["less_eff_cpl"] - top_inefficiency["more_eff_cpl"])
                            
                                st.markdown(f"""
                                **Priority 1: Improve {top_inefficiency['platform']} Efficiency**
                                - Current CPL: ${top_inefficiency['less_eff_cpl']:.2f}
                                - Target CPL: ${top_inefficiency['more_eff_cpl']:.2f} (match {more_efficient_agency})
                                - Efficiency gap: ${top_inefficiency['cpl_gap']:.2f} per lead ({top_inefficiency['cpl_pct']:.0f}% higher)
                                - **Potential monthly savings**: ${potential_savings:,.2f} if efficiency matches {more_efficient_agency}
                            
                                **Suggested investigations:**
                                1. **Campaign settings audit**: Compare {less_efficient_agency} vs {more_efficient_agency} on {top_inefficiency['platform']}
                                   - Targeting: Same audiences? Geographic settings?
                                   - Bidding: Manual vs automated? Bid caps? Target CPA settings?
                                   - Ad scheduling: Same dayparting?
                                2. **Quality Score check**: Lower QS = higher costs (note: ad copy is identical across offices)
                                   - Expected CTR differences
                                   - Ad relevance scoring
                                   - Landing page experience
                                3. **Landing page comparison**: Same pages? Load times? Mobile experience?
                                4. **Conversion tracking**: Verify both agencies tracking correctly
                                5. **Account history**: Older accounts may have better Quality Scores due to historical performance
                                """)
                            
                                if len(recommendations) > 1:
                                    second_inefficiency = recommendations[1]
                                    second_savings = second_inefficiency["less_eff_leads"] * (second_inefficiency["less_eff_cpl"] - second_inefficiency["more_eff_cpl"])
                                    st.markdown(f"""
                                    **Priority 2: Optimize {second_inefficiency['platform']}**
                                    - CPL gap: ${second_inefficiency['cpl_gap']:.2f} ({second_inefficiency['cpl_pct']:.0f}% less efficient)
                                    - Potential monthly savings: ${second_savings:,.2f}
                                    - Apply same audit process as Priority 1
                                    """)
                        
                            # Device analysis (if available)
                            if add_device_column and "device" in results["agency_overview"].columns:
                                st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                                st.markdown("**Device Considerations:**")
                                st.markdown("Check device-level performance and consider bid adjustments for mobile/desktop/tablet if one device type shows significantly different efficiency.")
                        
                            # Summary recommendation
                            st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                            total_potential_savings = sum(r["less_eff_leads"] * (r["less_eff_cpl"] - r["more_eff_cpl"]) for r in recommendations)
                            st.info(f"""
                            **Bottom Line:** By matching {more_efficient_agency}'s efficiency across platforms, {less_efficient_agency} could save approximately **${total_potential_savings:,.2f} per month** 
                            while maintaining the same lead volume. Focus on the platform-specific audits above to identify the root causes of the CPL differences.
                            """)
                        else:
                            st.warning("Spend data not available for CPL analysis. Upload files with spend/budget columns for efficiency insights.")
                
                    # ========== INDIVIDUAL AGENCY BREAKDOWNS ==========
                    st.markdown('<div class="space-lg"></div>', unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown("### 📋 Individual Agency Analysis")
                
                    # Split data by agency
                    legacy_data = df_in[df_in["agency"] == "Legacy"].copy() if "Legacy" in df_in["agency"].values else pd.DataFrame()
                    moa_data = df_in[df_in["agency"] == "MOA"].copy() if "MOA" in df_in["agency"].values else pd.DataFrame()
                
                    # Create two columns for side-by-side comparison
                    col_left, col_right = st.columns(2)
                
                    # ========== LEGACY ANALYSIS ==========
                    with col_left:
                        st.markdown("**🏢 Legacy Agency**")
                        st.markdown('<div class="space-xs"></div>', unsafe_allow_html=True)
                    
                        if not legacy_data.empty:
                            # Platform breakdown
                            st.markdown("**Platform Overview**")
                            legacy_platform = results["platform_agency"][
                                results["platform_agency"]["agency"] == "Legacy"
                            ].copy()
                        
                            if "device" in legacy_platform.columns:
                                legacy_platform = legacy_platform.groupby("platform", as_index=False).agg({
                                    "leads": "sum",
                                    "spend": "sum",
                                    "quote_starts": "sum",
                                    "phone_clicks": "sum",
                                    "sms_clicks": "sum"
                                })
                                legacy_platform["cpl_platform"] = np.where(
                                    legacy_platform["leads"] > 0,
                                    legacy_platform["spend"] / legacy_platform["leads"],
                                    np.nan
                                )
                        
                            # Remove agency column for cleaner display
                            if "agency" in legacy_platform.columns:
                                legacy_platform = legacy_platform.drop(columns=["agency"])

                            # Add TOTAL row
                            totals_row = {"platform": "TOTAL"}
                            for c in ["leads", "spend", "quote_starts", "phone_clicks", "sms_clicks"]:
                                if c in legacy_platform.columns:
                                    totals_row[c] = legacy_platform[c].sum()
                            if "cpl_platform" in legacy_platform.columns:
                                totals_row["cpl_platform"] = (totals_row.get("spend", 0) / totals_row["leads"]) if totals_row.get("leads", 0) > 0 else np.nan
                            legacy_platform = pd.concat([legacy_platform, pd.DataFrame([totals_row])], ignore_index=True)

                            display_table_with_total(legacy_platform, "platform", "TOTAL")

                            # Product breakdown
                            st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                            st.markdown("**Product Breakdown**")
                            legacy_product = results["product_agency"][
                                results["product_agency"]["agency"] == "Legacy"
                            ].copy() if "agency" in results["product_agency"].columns else pd.DataFrame()
                        
                            if not legacy_product.empty:
                                if "device" in legacy_product.columns:
                                    legacy_product = legacy_product.groupby("product", as_index=False).agg({
                                        "leads": "sum",
                                        "quote_starts": "sum",
                                        "phone_clicks": "sum",
                                        "sms_clicks": "sum"
                                    })

                                # Remove agency column
                                if "agency" in legacy_product.columns:
                                    legacy_product = legacy_product.drop(columns=["agency"])

                                # Add TOTAL row
                                totals_row = {"product": "TOTAL"}
                                for c in ["leads", "quote_starts", "phone_clicks", "sms_clicks"]:
                                    if c in legacy_product.columns:
                                        totals_row[c] = legacy_product[c].sum()
                                legacy_product = pd.concat([legacy_product, pd.DataFrame([totals_row])], ignore_index=True)

                                display_table_with_total(legacy_product, "product", "TOTAL")
                        
                            # Source breakdown (Top 5)
                            st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                            st.markdown("**Top 5 Traffic Sources**")
                            legacy_source = results["by_source"].copy()
                        
                            if "lead_opportunities" in legacy_source.columns:
                                legacy_source = legacy_source.rename(columns={"lead_opportunities": "leads"})
                        
                            if "agency" in legacy_source.columns:
                                legacy_source = legacy_source[legacy_source["agency"] == "Legacy"].copy()
                                legacy_source = legacy_source.groupby("source", as_index=False)["leads"].sum()
                                legacy_source = legacy_source.nlargest(5, "leads")
                            
                                # Remove agency column if present
                                if "agency" in legacy_source.columns:
                                    legacy_source = legacy_source.drop(columns=["agency"])
                            
                                # Use pretty headers
                                legacy_source_pretty = pretty_headers(legacy_source)
                                st.dataframe(legacy_source_pretty, use_container_width=True, hide_index=True)
                        else:
                            st.info("No Legacy data uploaded")
                
                    # ========== MOA ANALYSIS ==========
                    with col_right:
                        st.markdown("**🏢 MOA Agency**")
                        st.markdown('<div class="space-xs"></div>', unsafe_allow_html=True)
                    
                        if not moa_data.empty:
                            # Platform breakdown
                            st.markdown("**Platform Overview**")
                            moa_platform = results["platform_agency"][
                                results["platform_agency"]["agency"] == "MOA"
                            ].copy()
                        
                            if "device" in moa_platform.columns:
                                moa_platform = moa_platform.groupby("platform", as_index=False).agg({
                                    "leads": "sum",
                                    "spend": "sum",
                                    "quote_starts": "sum",
                                    "phone_clicks": "sum",
                                    "sms_clicks": "sum"
                                })
                                moa_platform["cpl_platform"] = np.where(
                                    moa_platform["leads"] > 0,
                                    moa_platform["spend"] / moa_platform["leads"],
                                    np.nan
                                )
                        
                            # Remove agency column for cleaner display
                            if "agency" in moa_platform.columns:
                                moa_platform = moa_platform.drop(columns=["agency"])

                            # Add TOTAL row
                            totals_row = {"platform": "TOTAL"}
                            for c in ["leads", "spend", "quote_starts", "phone_clicks", "sms_clicks"]:
                                if c in moa_platform.columns:
                                    totals_row[c] = moa_platform[c].sum()
                            if "cpl_platform" in moa_platform.columns:
                                totals_row["cpl_platform"] = (totals_row.get("spend", 0) / totals_row["leads"]) if totals_row.get("leads", 0) > 0 else np.nan
                            moa_platform = pd.concat([moa_platform, pd.DataFrame([totals_row])], ignore_index=True)

                            display_table_with_total(moa_platform, "platform", "TOTAL")

                            # Product breakdown
                            st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                            st.markdown("**Product Breakdown**")
                            moa_product = results["product_agency"][
                                results["product_agency"]["agency"] == "MOA"
                            ].copy() if "agency" in results["product_agency"].columns else pd.DataFrame()
                        
                            if not moa_product.empty:
                                if "device" in moa_product.columns:
                                    moa_product = moa_product.groupby("product", as_index=False).agg({
                                        "leads": "sum",
                                        "quote_starts": "sum",
                                        "phone_clicks": "sum",
                                        "sms_clicks": "sum"
                                    })

                                # Remove agency column
                                if "agency" in moa_product.columns:
                                    moa_product = moa_product.drop(columns=["agency"])

                                # Add TOTAL row
                                totals_row = {"product": "TOTAL"}
                                for c in ["leads", "quote_starts", "phone_clicks", "sms_clicks"]:
                                    if c in moa_product.columns:
                                        totals_row[c] = moa_product[c].sum()
                                moa_product = pd.concat([moa_product, pd.DataFrame([totals_row])], ignore_index=True)

                                display_table_with_total(moa_product, "product", "TOTAL")
                        
                            # Source breakdown (Top 5)
                            st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                            st.markdown("**Top 5 Traffic Sources**")
                            moa_source = results["by_source"].copy()
                        
                            if "lead_opportunities" in moa_source.columns:
                                moa_source = moa_source.rename(columns={"lead_opportunities": "leads"})
                        
                            if "agency" in moa_source.columns:
                                moa_source = moa_source[moa_source["agency"] == "MOA"].copy()
                                moa_source = moa_source.groupby("source", as_index=False)["leads"].sum()
                                moa_source = moa_source.nlargest(5, "leads")
                            
                                # Remove agency column if present
                                if "agency" in moa_source.columns:
                                    moa_source = moa_source.drop(columns=["agency"])
                            
                                # Use pretty headers
                                moa_source_pretty = pretty_headers(moa_source)
                                st.dataframe(moa_source_pretty, use_container_width=True, hide_index=True)
                        else:
                            st.info("No MOA data uploaded")
                
                    # ========== INDIVIDUAL AGENCY CHARTS ==========
                    if PLOTLY_AVAILABLE:
                        st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)
                        st.markdown("### 📈 Individual Agency Charts")

                        # Build a consistent product-to-color map so both agencies use the same colors
                        all_products = sorted(
                            results["product_agency"]["product"].unique().tolist()
                        ) if "product" in results["product_agency"].columns else []
                        all_products = [p for p in all_products if p != "TOTAL"]
                        product_color_map = {
                            p: MELON_COLORS['primary'][i % len(MELON_COLORS['primary'])]
                            for i, p in enumerate(all_products)
                        }

                        chart_col1, chart_col2 = st.columns(2)

                        with chart_col1:
                            st.markdown("**Legacy - Platform Performance**")
                            if not legacy_data.empty:
                                legacy_plat_chart = results["platform_agency"][
                                    results["platform_agency"]["agency"] == "Legacy"
                                ].copy()

                                if "device" in legacy_plat_chart.columns:
                                    legacy_plat_chart = legacy_plat_chart.groupby("platform", as_index=False)["leads"].sum()

                                legacy_plat_chart = legacy_plat_chart[legacy_plat_chart["platform"] != "TOTAL"]

                                if not legacy_plat_chart.empty:
                                    fig_legacy = px.bar(
                                        legacy_plat_chart,
                                        x="platform",
                                        y="leads",
                                        title="Legacy Leads by Platform",
                                        color_discrete_sequence=["#114e38"]
                                    )
                                    fig_legacy.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                                    fig_legacy.update_layout(height=350, showlegend=False)
                                    st.plotly_chart(fig_legacy, use_container_width=True)

                            st.markdown("**Legacy - Product Distribution**")
                            if not legacy_data.empty:
                                legacy_prod_chart = results["product_agency"].copy()

                                if "agency" in legacy_prod_chart.columns:
                                    legacy_prod_chart = legacy_prod_chart[legacy_prod_chart["agency"] == "Legacy"].copy()

                                if "device" in legacy_prod_chart.columns:
                                    legacy_prod_chart = legacy_prod_chart.groupby("product", as_index=False)["leads"].sum()

                                legacy_prod_chart = legacy_prod_chart[legacy_prod_chart["product"] != "TOTAL"]
                                legacy_prod_chart = legacy_prod_chart[legacy_prod_chart["leads"] > 0]

                                if not legacy_prod_chart.empty:
                                    fig_legacy_prod = px.pie(
                                        legacy_prod_chart,
                                        values="leads",
                                        names="product",
                                        title="Legacy Product Distribution",
                                        color="product",
                                        color_discrete_map=product_color_map
                                    )
                                    fig_legacy_prod.update_traces(
                                        textposition='auto',
                                        textinfo='label+percent',
                                        insidetextorientation='radial'
                                    )
                                    fig_legacy_prod.update_layout(
                                        height=400,
                                        showlegend=True,
                                        legend=dict(
                                            orientation="h",
                                            yanchor="bottom",
                                            y=-0.2,
                                            xanchor="center",
                                            x=0.5
                                        )
                                    )
                                    st.plotly_chart(fig_legacy_prod, use_container_width=True)

                        with chart_col2:
                            st.markdown("**MOA - Platform Performance**")
                            if not moa_data.empty:
                                moa_plat_chart = results["platform_agency"][
                                    results["platform_agency"]["agency"] == "MOA"
                                ].copy()

                                if "device" in moa_plat_chart.columns:
                                    moa_plat_chart = moa_plat_chart.groupby("platform", as_index=False)["leads"].sum()

                                moa_plat_chart = moa_plat_chart[moa_plat_chart["platform"] != "TOTAL"]

                                if not moa_plat_chart.empty:
                                    fig_moa = px.bar(
                                        moa_plat_chart,
                                        x="platform",
                                        y="leads",
                                        title="MOA Leads by Platform",
                                        color_discrete_sequence=["#47B74F"]
                                    )
                                    fig_moa.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                                    fig_moa.update_layout(height=350, showlegend=False)
                                    st.plotly_chart(fig_moa, use_container_width=True)

                            st.markdown("**MOA - Product Distribution**")
                            if not moa_data.empty:
                                moa_prod_chart = results["product_agency"].copy()

                                if "agency" in moa_prod_chart.columns:
                                    moa_prod_chart = moa_prod_chart[moa_prod_chart["agency"] == "MOA"].copy()

                                if "device" in moa_prod_chart.columns:
                                    moa_prod_chart = moa_prod_chart.groupby("product", as_index=False)["leads"].sum()

                                moa_prod_chart = moa_prod_chart[moa_prod_chart["product"] != "TOTAL"]
                                moa_prod_chart = moa_prod_chart[moa_prod_chart["leads"] > 0]

                                if not moa_prod_chart.empty:
                                    fig_moa_prod = px.pie(
                                        moa_prod_chart,
                                        values="leads",
                                        names="product",
                                        title="MOA Product Distribution",
                                        color="product",
                                        color_discrete_map=product_color_map
                                    )
                                    fig_moa_prod.update_traces(
                                        textposition='auto',
                                        textinfo='label+percent',
                                        insidetextorientation='radial'
                                    )
                                    fig_moa_prod.update_layout(
                                        height=400,
                                        showlegend=True,
                                        legend=dict(
                                            orientation="h",
                                            yanchor="bottom",
                                            y=-0.2,
                                            xanchor="center",
                                            x=0.5
                                        )
                                    )
                                    st.plotly_chart(fig_moa_prod, use_container_width=True)
                
                    # ========== ADDITIONAL COMPARISON TABLES ==========
                    st.markdown('<div class="space-lg"></div>', unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown("### 📊 Detailed Comparison Tables")
                
                    # Get individual agency data
                    legacy_mask = df_in["agency"] == "Legacy"
                    moa_mask = df_in["agency"] == "MOA"
                
                    # Product Comparison
                    st.markdown("**Product Performance Comparison**")
                    prod_comparison = results["product_agency"].copy()  # Use product_agency which has agency column
                
                    if "agency" in prod_comparison.columns:
                        # Pivot to show Legacy vs MOA side by side
                        prod_comp_clean = prod_comparison[prod_comparison["product"] != "TOTAL"].copy()
                    
                        if not prod_comp_clean.empty:
                            # Group by product and agency
                            if "device" in prod_comp_clean.columns:
                                prod_pivot_data = prod_comp_clean.groupby(["product", "agency"], as_index=False).agg({
                                    "leads": "sum",
                                    "quote_starts": "sum",
                                    "phone_clicks": "sum",
                                    "sms_clicks": "sum"
                                })
                            else:
                                prod_pivot_data = prod_comp_clean[["product", "agency", "leads", "quote_starts", "phone_clicks", "sms_clicks"]].copy()
                        
                            # Create pivot table
                            prod_pivot = prod_pivot_data.pivot(index="product", columns="agency", values=["leads", "quote_starts", "phone_clicks", "sms_clicks"])
                            prod_pivot.columns = [f"{col[1]}_{col[0]}" for col in prod_pivot.columns]
                            prod_pivot = prod_pivot.reset_index()
                        
                            # Add difference columns
                            if "Legacy_leads" in prod_pivot.columns and "MOA_leads" in prod_pivot.columns:
                                prod_pivot["Lead_Diff"] = prod_pivot["MOA_leads"] - prod_pivot["Legacy_leads"]
                                prod_pivot["Lead_Winner"] = prod_pivot.apply(
                                    lambda r: "MOA ✓" if r["MOA_leads"] > r["Legacy_leads"] 
                                    else "Legacy ✓" if r["Legacy_leads"] > r["MOA_leads"]
                                    else "Tie",
                                    axis=1
                                )
                        
                            # Format for display
                            display_cols = ["product"]
                            if "Legacy_leads" in prod_pivot.columns:
                                display_cols.extend(["Legacy_leads", "MOA_leads", "Lead_Diff", "Lead_Winner"])
                        
                            if "Legacy_quote_starts" in prod_pivot.columns:
                                display_cols.extend(["Legacy_quote_starts", "MOA_quote_starts"])
                            if "Legacy_phone_clicks" in prod_pivot.columns:
                                display_cols.extend(["Legacy_phone_clicks", "MOA_phone_clicks"])
                            if "Legacy_sms_clicks" in prod_pivot.columns:
                                display_cols.extend(["Legacy_sms_clicks", "MOA_sms_clicks"])
                        
                            prod_display = prod_pivot[[col for col in display_cols if col in prod_pivot.columns]].copy()
                        
                            # Rename columns
                            prod_display = prod_display.rename(columns={
                                "product": "Product",
                                "Legacy_leads": "Legacy Leads",
                                "MOA_leads": "MOA Leads",
                                "Lead_Diff": "Difference",
                                "Lead_Winner": "Winner",
                                "Legacy_quote_starts": "Legacy QS",
                                "MOA_quote_starts": "MOA QS",
                                "Legacy_phone_clicks": "Legacy Phone",
                                "MOA_phone_clicks": "MOA Phone",
                                "Legacy_sms_clicks": "Legacy SMS",
                                "MOA_sms_clicks": "MOA SMS"
                            })
                        
                            st.dataframe(prod_display, use_container_width=True, hide_index=True)
                
                    # Device Comparison (if device breakdown enabled)
                    if add_device_column and "device" in results["agency_overview"].columns:
                        st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)
                        st.markdown("**Device Performance Comparison**")
                    
                        device_data = results["agency_overview"][results["agency_overview"]["agency"] != "TOTAL"].copy()
                    
                        if not device_data.empty:
                            # Pivot by device and agency
                            device_pivot_data = device_data.groupby(["device", "agency"], as_index=False).agg({
                                "leads": "sum",
                                "quote_starts": "sum",
                                "phone_clicks": "sum",
                                "sms_clicks": "sum"
                            })
                        
                            device_pivot = device_pivot_data.pivot(index="device", columns="agency", values=["leads", "quote_starts", "phone_clicks", "sms_clicks"])
                            device_pivot.columns = [f"{col[1]}_{col[0]}" for col in device_pivot.columns]
                            device_pivot = device_pivot.reset_index()
                        
                            # Add difference
                            if "Legacy_leads" in device_pivot.columns and "MOA_leads" in device_pivot.columns:
                                device_pivot["Lead_Diff"] = device_pivot["MOA_leads"] - device_pivot["Legacy_leads"]
                                device_pivot["Winner"] = device_pivot.apply(
                                    lambda r: "MOA ✓" if r["MOA_leads"] > r["Legacy_leads"]
                                    else "Legacy ✓" if r["Legacy_leads"] > r["MOA_leads"]
                                    else "Tie",
                                    axis=1
                                )
                        
                            # Rename and display
                            device_pivot = device_pivot.rename(columns={
                                "device": "Device",
                                "Legacy_leads": "Legacy Leads",
                                "MOA_leads": "MOA Leads",
                                "Lead_Diff": "Difference"
                            })
                        
                            st.dataframe(device_pivot, use_container_width=True, hide_index=True)
                
                    # Source Comparison
                    st.markdown('<div class="space-md"></div>', unsafe_allow_html=True)
                    st.markdown("**Traffic Source Comparison**")
                
                    source_data = results["by_source"].copy()
                
                    # Rename lead_opportunities to leads if it exists
                    if "lead_opportunities" in source_data.columns:
                        source_data = source_data.rename(columns={"lead_opportunities": "leads"})
                
                    if "agency" in source_data.columns and "leads" in source_data.columns:
                        source_comp = source_data[source_data["source"] != "TOTAL"].copy()
                    
                        if not source_comp.empty:
                            # ALWAYS aggregate by source and agency to avoid duplicates
                            source_summary = source_comp.groupby(["source", "agency"], as_index=False)["leads"].sum()
                        
                            if not source_summary.empty:
                                # Get top 10 sources overall
                                top_sources = source_summary.groupby("source")["leads"].sum().nlargest(10).index.tolist()
                                source_top = source_summary[source_summary["source"].isin(top_sources)]
                            
                                # Pivot
                                source_pivot = source_top.pivot(index="source", columns="agency", values="leads").fillna(0)
                                source_pivot = source_pivot.reset_index()
                            
                                if "Legacy" in source_pivot.columns and "MOA" in source_pivot.columns:
                                    source_pivot["Difference"] = source_pivot["MOA"] - source_pivot["Legacy"]
                                    source_pivot = source_pivot.sort_values("Difference", ascending=False)
                            
                                # Rename
                                source_pivot = source_pivot.rename(columns={
                                    "source": "Traffic Source",
                                    "Legacy": "Legacy Leads",
                                    "MOA": "MOA Leads"
                                })
                            
                                st.dataframe(source_pivot, use_container_width=True, hide_index=True)
                            else:
                                st.info("No source data available for comparison.")
                        else:
                            st.info("No source data available for comparison.")
                    else:
                        st.info("Source comparison requires both agencies to have data.")
    

        # ---- Budget Optimizer Tab ----
        with tab_optimizer:
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
        
            # Minimum lead threshold — platforms with too few leads have unreliable CPL
            MIN_LEADS_FOR_OPTIMIZER = 10
            plat_eff["leads"] = pd.to_numeric(plat_eff["leads"], errors="coerce").fillna(0)
            low_lead_platforms = plat_eff[plat_eff["leads"] < MIN_LEADS_FOR_OPTIMIZER]
            if not low_lead_platforms.empty:
                names = ", ".join(low_lead_platforms["platform"].tolist())
                st.warning(f"Platforms with fewer than {MIN_LEADS_FOR_OPTIMIZER} leads excluded from optimization (unreliable CPL): **{names}**")
                plat_eff = plat_eff[plat_eff["leads"] >= MIN_LEADS_FOR_OPTIMIZER].copy()

            if plat_eff.empty:
                st.info("No platform data available to compute suggestions (all platforms below minimum lead threshold).")
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
    

        # ---- Export Tab ----
        with tab_export:
            # ---------- Exports (short sheet names <=31 chars) ----------
            excel_bytes = build_excel({
                "Platform": results["platform_overview"],
                "Agency": results["agency_overview"],
                "Prod x Plat": results["by_product_platform"],
                "Product": results["by_product_total"],
                "By Source": results["by_source"],
            })
    
            # ========== EXPORT SELECTION ==========
            st.markdown('<div class="space-lg"></div>', unsafe_allow_html=True)
            st.markdown("---")
            st.markdown("### 📦 Export Options")
        
            with st.expander("⚙️ Customize Your Export", expanded=False):
                st.markdown("**Select which tables and charts to include in exports:**")
            
                col1, col2 = st.columns(2)
            
                with col1:
                    st.markdown("**📊 Tables:**")
                    export_platform = st.checkbox("Platform Overview", value=True, key="export_platform")
                    export_agency = st.checkbox("Agency Overview", value=True, key="export_agency")
                    export_product_total = st.checkbox("Product (Total)", value=True, key="export_product_total")
                    export_product_platform = st.checkbox("Product × Platform", value=True, key="export_product_platform")
                    export_source = st.checkbox("By Source", value=True, key="export_source")
            
                with col2:
                    st.markdown("**📈 Charts (HTML only):**")
                    export_chart_platform = st.checkbox("Platform Performance Chart", value=True, key="export_chart_platform")
                    export_chart_product = st.checkbox("Product Distribution Chart", value=True, key="export_chart_product")
                    export_chart_agency = st.checkbox("Agency Comparison Chart", value=True, key="export_chart_agency")
                
                    st.markdown('<div class="space-sm"></div>', unsafe_allow_html=True)
                    if st.button("✅ Select All", use_container_width=True):
                        st.session_state.export_platform = True
                        st.session_state.export_agency = True
                        st.session_state.export_product_total = True
                        st.session_state.export_product_platform = True
                        st.session_state.export_source = True
                        st.session_state.export_chart_platform = True
                        st.session_state.export_chart_product = True
                        st.session_state.export_chart_agency = True
                        st.rerun()
                
                    if st.button("❌ Deselect All", use_container_width=True):
                        st.session_state.export_platform = False
                        st.session_state.export_agency = False
                        st.session_state.export_product_total = False
                        st.session_state.export_product_platform = False
                        st.session_state.export_source = False
                        st.session_state.export_chart_platform = False
                        st.session_state.export_chart_product = False
                        st.session_state.export_chart_agency = False
                        st.rerun()
        
            # Build filtered exports based on selections
            selected_sheets = {}
            if export_platform:
                selected_sheets["Platform Overview"] = results["platform_overview"]
            if export_agency:
                selected_sheets["Agency Overview"] = results["agency_overview"]
            if export_product_total:
                selected_sheets["By Product (Total)"] = results["by_product_total"]
            if export_product_platform:
                selected_sheets["By Product × Platform"] = results["by_product_platform"]
            if export_source:
                selected_sheets["By Source"] = results["by_source"]
            lpu_export = results.get("platform_lp_utm")
            if lpu_export is not None and not lpu_export.empty:
                selected_sheets["Platform x LP x UTM"] = lpu_export

            # Build Excel with selected sheets
            if selected_sheets:
                excel_bytes_filtered = build_excel(selected_sheets)
            else:
                excel_bytes_filtered = excel_bytes  # Fallback to all
        
            st.download_button(
                "⬇️ Download Combined Excel Report (Generated "+datetime.now().strftime('%I:%M %p')+")", 
                excel_bytes_filtered, 
                "combined_lead_report_demo.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )
        
            # Build HTML report with tables AND charts
            html_charts = {}
        
            if PLOTLY_AVAILABLE:
                # 1. Platform Overview Chart
                if export_chart_platform:
                    plat_data = results["platform_overview"][results["platform_overview"]["platform"] != "TOTAL"].copy()
                    if not plat_data.empty and "leads" in plat_data.columns:
                        plat_data["leads"] = pd.to_numeric(plat_data["leads"], errors="coerce").fillna(0)
                        if plat_data["leads"].sum() > 0:
                            fig_platform = px.bar(
                                plat_data,
                                x="platform",
                                y="leads",
                                title="Leads by Platform",
                                labels={"platform": "Platform", "leads": "Total Leads"},
                                color="leads",
                                color_continuous_scale=["#eef7ef", "#47B74F"]
                            )
                            fig_platform.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                            fig_platform.update_layout(
                                showlegend=False,
                                height=400,
                                margin=dict(l=20, r=20, t=60, b=20)
                            )
                            html_charts["Platform Performance"] = fig_platform
            
                # 2. Product Distribution Pie Chart
                if export_chart_product:
                    prod_data = results["by_product_total"].copy()
                    if "device" in prod_data.columns:
                        prod_data = prod_data.groupby("product", as_index=False)["leads"].sum()
                
                    prod_data = prod_data[prod_data["product"] != "TOTAL"].copy()
                    if not prod_data.empty and "leads" in prod_data.columns:
                        prod_data["leads"] = pd.to_numeric(prod_data["leads"], errors="coerce").fillna(0)
                        prod_data = prod_data[prod_data["leads"] > 0]
                    
                        if not prod_data.empty:
                            fig_product = px.pie(
                                prod_data,
                                values="leads",
                                names="product",
                                title="Lead Distribution by Product",
                                color_discrete_sequence=MELON_COLORS['primary']
                            )
                            fig_product.update_traces(
                                textposition='inside',
                                textinfo='percent+label'
                            )
                            fig_product.update_layout(
                                height=500,
                                margin=dict(l=20, r=20, t=60, b=20)
                            )
                            html_charts["Product Distribution"] = fig_product
            
                # 3. Agency Comparison (if both exist)
                if export_chart_agency:
                    agency_data = results["agency_overview"][results["agency_overview"]["agency"] != "TOTAL"].copy()
                    if len(agency_data) >= 2 and "leads" in agency_data.columns:
                        if "device" in agency_data.columns:
                            agency_data = agency_data.groupby("agency", as_index=False)["leads"].sum()
                    
                        agency_data["leads"] = pd.to_numeric(agency_data["leads"], errors="coerce").fillna(0)
                    
                        if agency_data["leads"].sum() > 0:
                            fig_agency = px.bar(
                                agency_data,
                                x="agency",
                                y="leads",
                                title="Leads by Agency",
                                labels={"agency": "Agency", "leads": "Total Leads"},
                                color="agency",
                                color_discrete_map={"Legacy": "#114e38", "MOA": "#47B74F"}
                            )
                            fig_agency.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                            fig_agency.update_layout(
                                showlegend=False,
                                height=400,
                                margin=dict(l=20, r=20, t=60, b=20)
                            )
                            html_charts["Agency Comparison"] = fig_agency
        
            html_report = build_html_report(selected_sheets, charts=html_charts)
        
            st.download_button(
                "⬇️ Download Complete HTML Report (Generated "+datetime.now().strftime('%I:%M %p')+")", 
                html_report.encode('utf-8'),
                "combined_lead_report.html",
                "text/html", 
                use_container_width=True
            )
    
            style_flag = "formatted" if st.session_state.get("sb_csv_style") == "With $ and % symbols" else "raw"
            csv_platform = df_to_csv_bytes(results["platform_overview"], style=style_flag)
            csv_ag = df_to_csv_bytes(results["agency_overview"], style=style_flag)
            csv_bpp = df_to_csv_bytes(results["by_product_platform"], style=style_flag)
            csv_prod = df_to_csv_bytes(results["by_product_total"], style=style_flag)
            csv_src = df_to_csv_bytes(results["by_source"], style=style_flag)
        
            # Generate HTML versions
            html_platform = dataframe_to_html(results["platform_overview"], "Platform Overview")
            html_ag = dataframe_to_html(results["agency_overview"], "Agency Overview")
            html_bpp = dataframe_to_html(results["by_product_platform"], "Product × Platform")
            html_prod = dataframe_to_html(results["by_product_total"], "Product Overview")
            html_src = dataframe_to_html(results["by_source"], "By Source")
    
            st.markdown("### Download Individual Reports")
        
            # Create tabs for CSV and HTML
            tab1, tab2 = st.tabs(["📄 CSV Format", "🌐 HTML Format"])
        
            with tab1:
                st.markdown("**CSV Downloads**")
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
                        file_name="combined_source.csv",
                        mime="text/csv", 
                        use_container_width=True
                    )
        
            with tab2:
                st.markdown("**HTML Downloads** (Open in browser, print-ready)")
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button(
                        "⬇️ Platform (HTML)", 
                        data=html_platform, 
                        file_name="platform_overview.html",
                        mime="text/html", 
                        use_container_width=True
                    )
                    st.download_button(
                        "⬇️ Agency (HTML)", 
                        data=html_ag, 
                        file_name="agency_overview.html",
                        mime="text/html", 
                        use_container_width=True
                    )
                with c2:
                    st.download_button(
                        "⬇️ Product × Platform (HTML)", 
                        data=html_bpp, 
                        file_name="product_x_platform.html",
                        mime="text/html", 
                        use_container_width=True
                    )
                    st.download_button(
                        "⬇️ Product (HTML)", 
                        data=html_prod, 
                        file_name="product_overview.html",
                        mime="text/html", 
                        use_container_width=True
                    )
                    st.download_button(
                        "⬇️ By Source (HTML)", 
                        data=html_src, 
                        file_name="by_source.html",
                        mime="text/html", 
                        use_container_width=True
                    )
    


# ========== TAB 2: ADS ACCOUNT HEALTH ==========
with main_tab2:
        st.markdown("### Ads Account Health Checker")
        
        # Store Tab 2 status for debug table
        if 'campaign_stats' in st.session_state:
            st.session_state.tab2_campaign_stats_available = len(st.session_state.campaign_stats)
        else:
            st.session_state.tab2_campaign_stats_available = 0
        
        # Store mapping info for debug table
        if 'campaign_mapping' in st.session_state and st.session_state.campaign_mapping is not None:
            st.session_state.tab2_mapping_loaded = len(st.session_state.campaign_mapping)
        else:
            st.session_state.tab2_mapping_loaded = 0
        
        st.markdown("""
        Upload your Google Ads **Ad Group Report** to get bid optimization recommendations 
        based on your position 2-3 strategy.

        **Required columns:** Ad group, Campaign, Impr., Clicks, Cost, Avg. CPC, CTR, 
        Search impr. share, Search top IS, Search abs. top IS, Search lost IS (rank)
        """)

        # Sidebar settings for ads health
        with st.sidebar:
            st.markdown("---")
            st.markdown("### ⚙️ Ads Health Settings")
            show_debug_tab2 = st.checkbox("Developer Tools", value=False, key="dev_tools_tab2")

            with st.expander("Customize Thresholds", expanded=False):
                st.markdown("**Position Targets**")
                target_top_min = st.slider(
                    "Min Top IS % (positions 1-3)",
                    min_value=50, max_value=70, value=60, step=5
                ) / 100
                target_top_max = st.slider(
                    "Max Top IS %",
                    min_value=70, max_value=90, value=80, step=5
                ) / 100
                target_abs_top_min = st.slider(
                    "Min Abs. Top IS % (position 1)",
                    min_value=10, max_value=30, value=20, step=5
                ) / 100
                target_abs_top_max = st.slider(
                    "Max Abs. Top IS %",
                    min_value=30, max_value=50, value=40, step=5
                ) / 100

                st.markdown("**Quality Thresholds**")
                poor_ctr = st.slider(
                    "Poor CTR threshold",
                    min_value=1.0, max_value=3.0, value=1.5, step=0.5
                ) / 100
                good_ctr = st.slider(
                    "Good CTR threshold",
                    min_value=3.0, max_value=6.0, value=4.0, step=0.5
                ) / 100

                st.markdown("**Action Triggers**")
                lost_is_trigger = st.slider(
                    "Lost IS (rank) threshold",
                    min_value=20, max_value=40, value=30, step=5
                ) / 100
                abs_top_trigger = st.slider(
                    "Abs. Top IS trigger (decrease)",
                    min_value=40, max_value=60, value=50, step=5
                ) / 100
            
            # Use slider values (which default to the values shown)
            custom_thresholds = {
                'target_top_is_min': target_top_min,
                'target_top_is_max': target_top_max,
                'target_abs_top_is_min': target_abs_top_min,
                'target_abs_top_is_max': target_abs_top_max,
                'increase_lost_is_rank_min': lost_is_trigger,
                'decrease_abs_top_is_min': abs_top_trigger,
                'poor_ctr_threshold': poor_ctr,
                'good_ctr_threshold': good_ctr,
                'low_impr_share_threshold': 0.30,
                'min_spend_threshold': 20.0,
            }
    
    # File upload - accept multiple files
        ads_files = st.file_uploader(
            "Upload Ad Group Report(s) (CSV or Excel)",
            type=['csv', 'xlsx', 'xls'],
            key='ads_upload',
            accept_multiple_files=True,
            help="Upload separate Google and Microsoft reports - they will be analyzed independently"
        )

        if ads_files:
            with st.expander("📋 Loading Details", expanded=False):
                with st.spinner('Loading ads data...'):
                    # Load all uploaded files and keep track of platform
                    ads_data_by_platform = []  # List of (platform_name, dataframe) tuples
                    
                    for ads_file in ads_files:
                        df = load_ads_export(ads_file)
                        if df is not None:
                            # Detect platform from filename or data characteristics
                            filename_lower = ads_file.name.lower()
                            
                            # Check filename for platform indicators
                            # Microsoft: "Ad_Group_Report" (capital G with underscores)
                            # Google: "Ad group report" (lowercase g with spaces)
                            if 'microsoft' in filename_lower or 'bing' in filename_lower or 'Ad_Group_Report' in ads_file.name:
                                platform = "Microsoft Ads"
                            elif 'google' in filename_lower:
                                platform = "Google Ads"
                            else:
                                # Check if file has Microsoft-specific columns after mapping
                                # "Device type" is unique to Microsoft (Google doesn't have this)
                                has_device_type = 'Device type' in df.columns
                                
                                if has_device_type:
                                    platform = "Microsoft Ads"
                                else:
                                    # Must be Google
                                    platform = "Google Ads"
                            
                            ads_data_by_platform.append((platform, df))
                            st.info(f"📄 Loaded {ads_file.name}: {len(df):,} ad groups → **{platform}**")
                    
                    if not ads_data_by_platform:
                        st.error("❌ No valid ad group data could be loaded")

            if ads_data_by_platform:
                st.success(f"✅ Loaded {len(ads_data_by_platform)} platform(s) for independent analysis")
                
                # Budget Report Upload (BEFORE combining, so we can filter by CSM)
                st.markdown("---")
                with st.expander("💰 **Budget Report (Optional)** - Upload to filter by CSM", expanded=False):
                    st.markdown("""
                    Upload your budget report to:
                    - ✅ Filter accounts by CSM (Client Success Manager)
                    - ✅ See Budget Status for each account
                    - ✅ Prioritize recommendations based on spending status
                    
                    **Required columns:** Agent, CSM (optional), Status/Spend Status
                    """)
                    
                    shared_budget_file = st.file_uploader(
                        "Upload Budget Report (CSV or Excel)",
                        type=['csv', 'xlsx', 'xls'],
                        key='shared_budget_upload',
                        help="Budget report with Agent names, CSM assignments, and Budget Status"
                    )
                
                # Load and process budget data if provided
                shared_budget_df = None
                available_csms = []
                
                if shared_budget_file is not None:
                    try:
                        filename = shared_budget_file.name.lower()
                        if filename.endswith('.xlsx') or filename.endswith('.xls'):
                            budget_df_raw = pd.read_excel(shared_budget_file)
                        else:
                            budget_df_raw = pd.read_csv(shared_budget_file)
                        
                        st.success(f"✅ Loaded budget data for {len(budget_df_raw)} account(s)")
                        
                        # Extract Agent and Status columns
                        # Look for 'Agent' column
                        agent_col = None
                        for col in budget_df_raw.columns:
                            if 'agent' in str(col).lower() and 'status' not in str(col).lower():
                                agent_col = col
                                break
                        
                        # Look for Status column - prioritize 'Spend Status'
                        status_col = None
                        for col in budget_df_raw.columns:
                            col_lower = str(col).lower()
                            if 'spend' in col_lower and 'status' in col_lower:
                                status_col = col
                                break
                        
                        if status_col is None:
                            for col in budget_df_raw.columns:
                                if 'status' in str(col).lower():
                                    status_col = col
                                    break
                        
                        # Create processed budget dataframe with Agent and Status
                        if agent_col and status_col:
                            shared_budget_df = budget_df_raw[[agent_col, status_col]].copy()
                            shared_budget_df.columns = ['Agent', 'Status']
                            
                            # Clean data
                            shared_budget_df = shared_budget_df.dropna(subset=['Agent', 'Status'])
                            shared_budget_df['Agent'] = shared_budget_df['Agent'].astype(str).str.strip()
                            shared_budget_df['Status'] = shared_budget_df['Status'].astype(str).str.strip()
                            
                            st.caption(f"📋 Using columns: '{agent_col}' → Agent, '{status_col}' → Status")
                        else:
                            st.error(f"❌ Could not find Agent and Status columns in budget file")
                            st.caption(f"Available columns: {', '.join(budget_df_raw.columns.tolist()[:10])}")
                            shared_budget_df = None
                        
                        # Extract CSM list if column exists (from raw data)
                        if shared_budget_df is not None and 'CSM' in budget_df_raw.columns:
                            available_csms = sorted(budget_df_raw['CSM'].dropna().unique().tolist())
                            st.caption(f"📊 Found {len(available_csms)} CSM(s): {', '.join(available_csms)}")
                            
                            # Add CSM to processed budget df for filtering
                            if agent_col in budget_df_raw.columns and 'CSM' in budget_df_raw.columns:
                                csm_map = budget_df_raw.set_index(agent_col)['CSM'].to_dict()
                                shared_budget_df['CSM'] = shared_budget_df['Agent'].map(csm_map)
                        
                    except Exception as e:
                        st.error(f"❌ Error loading budget report: {str(e)}")
                        shared_budget_df = None
                
                # Combine all accounts from all platforms for the shared filter
                all_accounts = set()
                for platform_name, ads_df in ads_data_by_platform:
                    if 'Account' in ads_df.columns:
                        accounts = ads_df['Account'].dropna().unique().tolist()
                        accounts = [str(acc).strip() for acc in accounts if str(acc).strip() != '']
                        all_accounts.update(accounts)
                
                all_accounts = sorted(all_accounts)
                
                # Shared Account Filter (applies to all platforms)
                st.markdown("---")
                st.markdown("### 🎯 Filters")
                
                filter_col1, filter_col2, filter_col3 = st.columns([3, 2, 2])
                
                # CSM filter first (determines available accounts)
                with filter_col2:
                    # CSM filter (only if budget data with CSM column is available)
                    if available_csms:
                        csm_options = ['All CSMs'] + available_csms
                        selected_csm = st.selectbox(
                            "Filter by CSM",
                            options=csm_options,
                            key='shared_csm_filter',
                            help="View data only for accounts managed by a specific CSM"
                        )
                    else:
                        selected_csm = 'All CSMs'
                
                # Account filter (filtered by CSM if selected)
                with filter_col1:
                    # Filter account options by selected CSM
                    if selected_csm != 'All CSMs' and shared_budget_df is not None and 'CSM' in shared_budget_df.columns:
                        # Get accounts for this CSM
                        csm_accounts = shared_budget_df[shared_budget_df['CSM'] == selected_csm]['Agent'].unique().tolist()
                        # Only show accounts that exist in both budget and ads data
                        available_accounts = [acc for acc in all_accounts if acc in csm_accounts]
                        account_options = ['All Accounts'] + available_accounts
                    else:
                        account_options = ['All Accounts'] + all_accounts
                    
                    selected_account = st.selectbox(
                        "Filter by Account",
                        options=account_options,
                        key='shared_account_filter',
                        help="View data for a specific agent across all platforms, or all accounts combined"
                    )
                
                with filter_col3:
                    # Check if we have campaign stats from Tab 1
                    has_campaign_data = 'campaign_stats' in st.session_state and st.session_state.campaign_stats is not None
                    if has_campaign_data:
                        filter_to_stats_account = st.checkbox(
                            "📊 Only account from stats",
                            value=False,
                            key='filter_stats_account_shared',
                            help="Filter to only show the account from the Tab 1 stats report"
                        )
                    else:
                        filter_to_stats_account = False
                
                # Show info about selection
                if selected_account != 'All Accounts':
                    # Count how many ad groups this account has across platforms
                    total_ag_for_account = 0
                    platforms_with_account = []
                    for platform_name, ads_df in ads_data_by_platform:
                        if 'Account' in ads_df.columns:
                            ag_count = len(ads_df[ads_df['Account'] == selected_account])
                            if ag_count > 0:
                                total_ag_for_account += ag_count
                                platforms_with_account.append(f"{platform_name}: {ag_count}")
                    
                    st.info(f"📊 **{selected_account}**: {total_ag_for_account} total ad groups ({', '.join(platforms_with_account)})")
                else:
                    total_ag_all = sum(len(df) for _, df in ads_data_by_platform)
                    st.info(f"📊 Showing all {len(all_accounts)} accounts ({total_ag_all:,} total ad groups)")
                
                # Combine ALL platforms into a single dataframe with Platform column (NO TABS)
                # First, create the combined dataframe
                combined_dfs = []
                for platform_name, ads_df in ads_data_by_platform:
                    df_copy = ads_df.copy()
                    df_copy['Platform'] = platform_name
                    combined_dfs.append(df_copy)
                
                all_ads_df = pd.concat(combined_dfs, ignore_index=True)
                
                # Show debug details in expander
                if show_debug_tab2:
                  with st.expander("🔧 Platform Combination Details", expanded=False):
                    for platform_name, ads_df in ads_data_by_platform:
                        st.caption(f"  → Added {len(ads_df)} ad groups from **{platform_name}**")
                        st.caption(f"     Columns: {', '.join(ads_df.columns[:10].tolist())}...")
                    
                    st.caption(f"\n✅ Combined dataframe: {len(all_ads_df):,} total ad groups")
                    
                    # Show platform breakdown
                    if 'Platform' in all_ads_df.columns:
                        platform_counts = all_ads_df['Platform'].value_counts()
                        for platform, count in platform_counts.items():
                            st.caption(f"  • {platform}: {count:,} ad groups")
                    
                    # Show column sample from each platform
                    st.caption(f"\n🔍 Column check:")
                    for platform_name, ads_df in ads_data_by_platform:
                        has_account = 'Account' in ads_df.columns
                        has_impr = 'Impr.' in ads_df.columns
                        first_col = ads_df.columns[0] if len(ads_df.columns) > 0 else 'N/A'
                        st.caption(f"  {platform_name}: Has 'Account'={has_account}, Has 'Impr.'={has_impr}, First col='{first_col}'")
                
                # Apply CSM filter if selected
                if selected_csm != 'All CSMs' and shared_budget_df is not None and 'CSM' in shared_budget_df.columns:
                    # Get list of accounts for this CSM
                    csm_accounts = shared_budget_df[shared_budget_df['CSM'] == selected_csm]['Agent'].dropna().unique().tolist()
                    
                    # Filter dataframe to only those accounts
                    before_csm_filter = len(all_ads_df)
                    all_ads_df = all_ads_df[all_ads_df['Account'].isin(csm_accounts)].copy()
                    after_csm_filter = len(all_ads_df)
                    
                    st.info(f"🎯 **CSM Filter**: {selected_csm} → {len(csm_accounts)} accounts, {after_csm_filter:,} ad groups")

                
                # Ensure all required columns exist (add with NaN if missing)
                required_columns = [
                    'Account', 'Ad group', 'Campaign', 'Platform',
                    'Impr.', 'Clicks', 'Cost', 'Avg. CPC', 'CTR',
                    'Search impr. share', 'Search top IS', 'Search abs. top IS', 'Search lost IS (rank)',
                    'Ad group status', 'Default max. CPC', 'Current Bid'
                ]
                
                for col in required_columns:
                    if col not in all_ads_df.columns:
                        all_ads_df[col] = pd.NA
                        st.warning(f"⚠️ Column '{col}' missing - added with blank values")
                
                # Debug: Show platform breakdown
                if 'Platform' in all_ads_df.columns:
                    platform_breakdown = all_ads_df['Platform'].value_counts()
                    st.success(f"✅ Combined dataframe: {len(all_ads_df):,} total ad groups")
                    for platform, count in platform_breakdown.items():
                        st.caption(f"  • {platform}: {count:,} ad groups")
                
                # Process as single combined analysis (NO TABS - all data in one view)
                process_ads_platform(
                    "All Platforms Combined",
                    all_ads_df,
                    custom_thresholds,
                    selected_account,
                    filter_to_stats_account,
                    shared_budget_df,
                    show_debug=show_debug_tab2
                )
                



# ---- Consolidated Debug Section ----
if 'debug_info' in st.session_state and st.session_state.debug_info:
        # ========== TAB 2 DEBUG & STATUS TABLE ==========
        st.markdown("---")
        st.markdown("### 🔍 Debug & Status Report")
        
        # Build comprehensive Tab 2 debug data
        tab2_debug_data = []
        
        # Campaign stats from Tab 1
        if 'tab2_campaign_stats_available' in st.session_state:
            count = st.session_state.tab2_campaign_stats_available
            status = "✅" if count > 0 else "⚠️"
            tab2_debug_data.append(["Campaign Stats from Tab 1", f"{count} campaigns", status])
        
        # Mapping loaded
        if 'tab2_mapping_loaded' in st.session_state:
            count = st.session_state.tab2_mapping_loaded
            status = "✅" if count > 0 else "⚠️"
            tab2_debug_data.append(["Product/UTM Mapping", f"{count:,} mappings", status])
        
        if tab2_debug_data:
            tab2_df = pd.DataFrame(tab2_debug_data, columns=["Metric", "Value", "Status"])
            st.dataframe(tab2_df, hide_index=True, use_container_width=True)
        
        # Build text export
        tab2_debug_text = "=== TAB 2 DEBUG & STATUS REPORT ===\n\n"
        if tab2_debug_data:
            for row in tab2_debug_data:
                tab2_debug_text += f"{row[0]}: {row[1]} {row[2]}\n"
        
        # Download and copy buttons
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                label="📥 Download Tab 2 Debug Report",
                data=tab2_debug_text,
                file_name="tab2_debug_report.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        with col2:
            if st.button("📋 Copy to Clipboard", key="copy_tab2_debug", use_container_width=True):
                st.code(tab2_debug_text, language=None)

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
