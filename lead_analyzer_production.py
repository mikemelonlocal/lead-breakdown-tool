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
    # Disable on Streamlit Cloud - browser automation doesn't work
    DFI_AVAILABLE = False  # Set to True for local development only
except ImportError:
    DFI_AVAILABLE = False
except Exception:
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
PINE_GREEN = '#114e38'        # Primary dark (Pine - TERTIARY)
CACTUS_GREEN = '#47B74F'      # Primary bright (Cactus - PRIMARY)
LEMON_SUN = '#F1CB20'         # Accent yellow (Lemon Sun - PRIMARY)

# Complete Official Melon Local Color Palette from Brand Book (March 2023, Page 13)
# PRIMARY COLORS
ALPINE = '#FEF8E9'           # C0 M2 Y9 K0
CACTUS = '#47B74F'           # C72 M0 Y95 K0 (PRIMARY)
LEMON_SUN_OFFICIAL = '#F1CB20'  # C5 M20 Y100 K0 (PRIMARY)

# SECONDARY COLORS
SAND = '#EDDFDB'             # C7 M9 Y28 K0
CLOVER = '#40A74C'           # C85 M5 Y100 K0
MUSTARD_SEED = '#CC8F15'     # C15 M45 Y100 K0
WATERMELON_SUGAR = '#E9736E' # C0 M75 Y50 K0
WHITNEY_PINK = '#FF9B94'     # C0 M54 Y30 K0

# TERTIARY COLORS
MOJAVE = '#CFBA97'           # C20 M25 Y42 K0
PINE = '#114e38'             # C95 M40 Y85 K45 (TERTIARY)
COCONUT = '#644414'          # C42 M65 Y100 K40
CRANBERRY = '#6C2126'        # C32 M96 Y80 K40

# Extended Melon Local color palette for charts - OPTIMIZED FOR CONTRAST
MELON_COLORS = {
    # Main palette - maximum contrast between adjacent colors
    # Pattern: Green → Yellow → Red/Pink → Brown → Green (alternating color families)
    'primary': [
        '#47B74F',  # 1. Cactus (bright green)
        '#F1CB20',  # 2. Lemon Sun (yellow) - contrast with green
        '#E9736E',  # 3. Watermelon Sugar (coral) - contrast with yellow
        '#114e38',  # 4. Pine (dark green) - contrast with coral
        '#CC8F15',  # 5. Mustard Seed (gold) - contrast with dark green
        '#FF9B94',  # 6. Whitney Pink (pink) - contrast with gold
        '#40A74C',  # 7. Clover (mid green) - contrast with pink
        '#6C2126',  # 8. Cranberry (burgundy) - contrast with green
        '#CFBA97',  # 9. Mojave (tan) - contrast with burgundy
        '#644414'   # 10. Coconut (brown) - contrast with tan
    ],
    # Legacy palette - darker tones with high contrast
    'legacy': [
        '#114e38',  # 1. Pine (dark green)
        '#F1CB20',  # 2. Lemon Sun (yellow) - contrast
        '#6C2126',  # 3. Cranberry (burgundy) - contrast
        '#47B74F',  # 4. Cactus (bright green) - contrast
        '#CC8F15',  # 5. Mustard Seed (gold) - contrast
        '#E9736E',  # 6. Watermelon Sugar (coral) - contrast
        '#40A74C',  # 7. Clover (mid green) - contrast
        '#CFBA97',  # 8. Mojave (tan) - contrast
        '#644414'   # 9. Coconut (brown) - contrast
    ],
    # MOA palette - bright tones with high contrast
    'moa': [
        '#47B74F',  # 1. Cactus (bright green)
        '#F1CB20',  # 2. Lemon Sun (yellow) - contrast
        '#FF9B94',  # 3. Whitney Pink (pink) - contrast
        '#40A74C',  # 4. Clover (mid green) - contrast
        '#CC8F15',  # 5. Mustard Seed (gold) - contrast
        '#E9736E',  # 6. Watermelon Sugar (coral) - contrast
        '#114e38',  # 7. Pine (dark green) - contrast
        '#CFBA97',  # 8. Mojave (tan) - contrast
        '#6C2126'   # 9. Cranberry (burgundy) - contrast
    ],
    # Contrast palette - alternating warm/cool colors
    'contrast': [
        '#47B74F',  # 1. Cactus (cool green)
        '#CC8F15',  # 2. Mustard Seed (warm gold) - contrast
        '#114e38',  # 3. Pine (cool dark green) - contrast
        '#E9736E',  # 4. Watermelon Sugar (warm coral) - contrast
        '#40A74C',  # 5. Clover (cool mid green) - contrast
        '#F1CB20',  # 6. Lemon Sun (warm yellow) - contrast
        '#6C2126',  # 7. Cranberry (cool burgundy) - contrast
        '#FF9B94',  # 8. Whitney Pink (warm pink) - contrast
        '#CFBA97'   # 9. Mojave (neutral tan) - contrast
    ]
}

# ============================================================================
# ADS ACCOUNT HEALTH - CONSTANTS
# ============================================================================
# Add this section after the MELON_COLORS definition (around line 147)

# Ads Account Health Thresholds
ADS_THRESHOLDS = {
    'target_top_is_min': 0.60,           # 60% minimum for top positions
    'target_top_is_max': 0.80,           # 80% maximum for top positions
    'target_abs_top_is_min': 0.20,       # 20% minimum position 1
    'target_abs_top_is_max': 0.40,       # 40% maximum position 1
    'increase_lost_is_rank_min': 0.30,   # 30% lost to rank triggers increase
    'decrease_abs_top_is_min': 0.50,     # 50% abs top triggers decrease
    'poor_ctr_threshold': 0.015,         # 1.5% CTR is poor
    'good_ctr_threshold': 0.04,          # 4% CTR is good
    'low_impr_share_threshold': 0.30,    # 30% impr share is low
    'min_spend_threshold': 20.0,         # $20 minimum spend to flag
}


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


# ============================================================================
# ADS ACCOUNT HEALTH - HELPER FUNCTIONS
# ============================================================================
# Add this section after the existing helper functions (around line 187, before main app)

def clean_numeric_ads(series):
    """Clean numeric columns from Google Ads export (handles commas, dashes, <, >, %)"""
    return pd.to_numeric(
        series.astype(str)
        .str.replace(',', '')
        .str.replace('--', '')
        .str.replace('<', '')
        .str.replace('>', '')
        .str.replace('%', '')
        .str.strip(),
        errors='coerce'
    )

def parse_bid_value(bid_str):
    """Extract numeric bid value from strings like '40.00 (enhanced)' or '90.00 (portfolio)'"""
    if pd.isna(bid_str):
        return None
    bid_str = str(bid_str).strip()
    if bid_str == '' or bid_str == '--' or bid_str == 'nan':
        return None
    # Extract just the number before any parentheses or text
    import re
    match = re.search(r'(\d+\.?\d*)', bid_str)
    if match:
        return float(match.group(1))
    return None

def match_budget_to_accounts(ads_df, budget_df):
    """
    Match budget report Agent names to Ads Account names.
    Returns ads_df with added 'Budget Status' column.
    """
    if budget_df is None or 'Agent' not in budget_df.columns or 'Status' not in budget_df.columns:
        return ads_df
    
    # Create a mapping dictionary
    from difflib import SequenceMatcher
    
    def similarity(a, b):
        """Calculate similarity between two strings"""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    # Create Agent -> Status mapping
    agent_status = {}
    for _, row in budget_df.iterrows():
        agent = str(row['Agent']).strip()
        status = str(row['Status']).strip()
        agent_status[agent] = status
    
    # Match each Account to best Agent
    def find_budget_status(account_name):
        if pd.isna(account_name):
            return None
        
        account_name = str(account_name).strip()
        
        # Try exact match first
        if account_name in agent_status:
            return agent_status[account_name]
        
        # Try fuzzy match (>0.8 similarity)
        best_match = None
        best_score = 0.8  # Threshold
        
        for agent in agent_status.keys():
            score = similarity(account_name, agent)
            if score > best_score:
                best_score = score
                best_match = agent
        
        if best_match:
            return agent_status[best_match]
        
        return None
    
    # Add Budget Status column
    ads_df['Budget Status'] = ads_df['Account'].apply(find_budget_status)
    
    return ads_df

def enrich_ads_with_campaign_stats(ads_df, campaign_stats_df, url_report_df=None):
    """
    Match campaigns and add conversion metrics to ads dataframe.
    
    Matching strategy (in priority order):
    1. If url_report_df provided with Campaign ID column: Direct ID matching
    2. If ads_df has Campaign ID column: Direct match with Tab 1 Campaign IDs
    3. Otherwise: Match on campaign name (exact match, then fuzzy match)
    
    Office filtering: If campaign_stats has an Office column, campaigns are matched
    by office based on whether campaign name contains "Legacy" or "MOA"
    
    Args:
        ads_df: Ads account dataframe from Tab 2
        campaign_stats_df: Campaign stats from Tab 1
        url_report_df: Optional URL report with Campaign ID and Ad Group ID columns
    
    Returns:
        ads_df with added "Campaign Conversions" column
    """
    if campaign_stats_df is None or campaign_stats_df.empty:
        return ads_df
    
    # Helper function to detect office from campaign name
    def detect_office(campaign_name):
        """Detect office (Legacy or MOA) from campaign name.
        
        Logic:
        - Campaign contains "MOA" → MOA office
        - Campaign contains "Legacy" → Legacy office
        - Neither → Default to Legacy office
        """
        if pd.isna(campaign_name):
            return 'Legacy'  # Default to Legacy
        
        name_upper = str(campaign_name).upper()
        
        # Check for MOA first (more specific)
        if 'MOA' in name_upper:
            return 'MOA'
        
        # Everything else defaults to Legacy
        # (including campaigns with "Legacy" in name and campaigns with neither)
        return 'Legacy'
    
    # Find Campaign ID column in Tab 1 stats
    stats_id_col = None
    for col in campaign_stats_df.columns:
        if 'campaign' in col.lower() and 'id' in col.lower():
            stats_id_col = col
            break
    
    # Build campaign map from Tab 1 stats
    # Key is (Campaign ID or Name, Office) -> conversions
    campaign_map = {}
    
    # Check if Office column exists (multi-office scenario)
    has_office = 'Office' in campaign_stats_df.columns
    
    if stats_id_col:
        # Tab 1 has Campaign IDs column - use that as primary key
        for _, row in campaign_stats_df.iterrows():
            campaign_id = str(row[stats_id_col]).strip() if pd.notna(row[stats_id_col]) else None
            if campaign_id and campaign_id != 'nan':
                # Remove any decimal points from float strings (20643283194.0 -> 20643283194)
                if '.' in campaign_id:
                    campaign_id = campaign_id.split('.')[0]
                
                # Store with office if available
                if has_office:
                    office = row.get('Office', 'Unknown')
                    key = (campaign_id, office)
                else:
                    key = campaign_id
                    
                campaign_map[key] = {
                    'conversions': row.get('Total Conversions', 0)
                }
    
    # Also map by campaign name as fallback
    campaign_name_map = {}
    if 'Campaign' in campaign_stats_df.columns:
        for _, row in campaign_stats_df.iterrows():
            campaign_name = str(row['Campaign']).strip() if pd.notna(row['Campaign']) else None
            if campaign_name:
                # Store with office if available
                if has_office:
                    office = row.get('Office', 'Unknown')
                    key = (campaign_name, office)
                else:
                    key = campaign_name
                    
                campaign_name_map[key] = {
                    'conversions': row.get('Total Conversions', 0)
                }
    
    # Strategy 1: Extract tracking Campaign IDs from URL report Final URLs
    # URL report contains Final URLs with tracking IDs like: ?cmpid=MLBDSF001-001R
    # We extract tracking ID from Final URL, then match to Tab 1 stats
    if url_report_df is not None and not url_report_df.empty:
        # Look for Final URL column
        final_url_col = None
        for col in url_report_df.columns:
            col_lower = str(col).lower()
            if any(term in col_lower for term in ['final', 'url', 'landing', 'destination']):
                final_url_col = col
                break
        
        # If URL report has Final URL column, extract tracking Campaign IDs
        if final_url_col:
            import re
            
            # Create mapping: (Account + Ad Group) -> (Tracking Campaign ID, Campaign Name)
            url_map = {}
            
            for _, row in url_report_df.iterrows():
                final_url = str(row.get(final_url_col, '')).strip() if pd.notna(row.get(final_url_col)) else None
                
                if not final_url or final_url == 'nan':
                    continue
                
                # Extract tracking Campaign ID from URL parameters
                # Look for patterns like: cmpid=MLBDSF001-001R, campaignid=..., utm_campaign=...
                tracking_id = None
                for param in ['cmpid=', 'campaignid=', 'utm_campaign=', 'campaign=']:
                    if param in final_url.lower():
                        # Extract value after parameter
                        match = re.search(rf'{param}([^&\s]+)', final_url, re.IGNORECASE)
                        if match:
                            tracking_id = match.group(1).strip()
                            break
                
                if not tracking_id:
                    continue
                
                # Get Ad Group, Account, and Campaign Name for matching
                ad_group = None
                account = None
                campaign_name = None
                
                for col in ['Ad group', 'Ad group name', 'Adgroup']:
                    if col in row and pd.notna(row[col]):
                        ad_group = str(row[col]).strip()
                        break
                
                for col in ['Account', 'Account name']:
                    if col in row and pd.notna(row[col]):
                        account = str(row[col]).strip()
                        break
                
                for col in ['Campaign', 'Campaign name']:
                    if col in row and pd.notna(row[col]):
                        campaign_name = str(row[col]).strip()
                        break
                
                if ad_group and tracking_id:
                    # Use composite key for precise matching
                    key = f"{account}|{ad_group}" if account else ad_group
                    url_map[key] = {
                        'tracking_id': tracking_id,
                        'campaign_name': campaign_name
                    }
            
            # Match ads data using URL report mapping
            def get_conversions_via_url_report(row):
                ad_group = str(row.get('Ad group', '')).strip() if pd.notna(row.get('Ad group')) else None
                account = str(row.get('Account', '')).strip() if pd.notna(row.get('Account')) else None
                
                if not ad_group:
                    return None
                
                # Try composite key first (Account + Ad group)
                key = f"{account}|{ad_group}" if account else ad_group
                url_data = url_map.get(key)
                
                if not url_data:
                    # Try just ad group
                    url_data = url_map.get(ad_group)
                
                if not url_data:
                    return None
                
                tracking_id = url_data['tracking_id']
                campaign_name = url_data.get('campaign_name', '')
                
                # Detect office from campaign name (always returns Legacy or MOA)
                office = detect_office(campaign_name)
                
                # Use office-specific match if stats have office column
                if has_office:
                    lookup_key = (tracking_id, office)
                    if lookup_key in campaign_map:
                        return campaign_map[lookup_key]['conversions']
                else:
                    # No office in stats - direct match
                    if tracking_id in campaign_map:
                        return campaign_map[tracking_id]['conversions']
                
                return None
            
            ads_df['Campaign Conversions'] = ads_df.apply(get_conversions_via_url_report, axis=1)
            return ads_df
    
    # Strategy 2: Direct Campaign ID matching (if ads_df has Campaign ID column)
    ads_campaign_id_col = None
    for col in ads_df.columns:
        if 'campaign' in col.lower() and 'id' in col.lower():
            ads_campaign_id_col = col
            break
    
    if ads_campaign_id_col and campaign_map:
        def get_conversions_by_direct_id(row):
            campaign_id = row[ads_campaign_id_col]
            campaign_name = str(row.get('Campaign', '')).strip() if pd.notna(row.get('Campaign')) else None
            
            if pd.isna(campaign_id):
                return None
            campaign_id = str(campaign_id).strip()
            
            # Normalize Campaign ID (same as URL report normalization)
            if campaign_id and campaign_id != 'nan':
                # Remove decimal points (20643283194.0 -> 20643283194)
                if '.' in campaign_id:
                    campaign_id = campaign_id.split('.')[0]
                # Remove brackets ([604582413] -> 604582413)
                campaign_id = campaign_id.replace('[', '').replace(']', '').strip()
            
            # Determine office from campaign name (always returns Legacy or MOA)
            office = detect_office(campaign_name)
            
            # Use office-specific match if stats have office column
            if has_office:
                lookup_key = (campaign_id, office)
                if lookup_key in campaign_map:
                    return campaign_map[lookup_key]['conversions']
            else:
                # No office in stats - direct match
                return campaign_map.get(campaign_id, {}).get('conversions', None)
            
            return None
        
        ads_df['Campaign Conversions'] = ads_df.apply(get_conversions_by_direct_id, axis=1)
        return ads_df
    
    # Strategy 3: Name-based matching (fallback)
    def get_conversions_by_name(campaign_name):
        if pd.isna(campaign_name):
            return None
        
        campaign_name = str(campaign_name).strip()
        
        # Determine office from campaign name (always returns Legacy or MOA)
        office = detect_office(campaign_name)
        
        # Use office-specific match if stats have office column
        if has_office:
            # Try exact match with office
            lookup_key = (campaign_name, office)
            if lookup_key in campaign_name_map:
                return campaign_name_map[lookup_key]['conversions']
            
            # Try fuzzy match (strip device suffixes like "- Desktop", "- Mobile")
            base_name = campaign_name
            for suffix in [' - Desktop', ' - Mobile', ' - Tablet']:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            
            if base_name != campaign_name:
                lookup_key = (base_name, office)
                if lookup_key in campaign_name_map:
                    return campaign_name_map[lookup_key]['conversions']
        else:
            # No office in stats - try direct name matching
            if campaign_name in campaign_name_map:
                return campaign_name_map[campaign_name]['conversions']
            
            # Try fuzzy match
            base_name = campaign_name
            for suffix in [' - Desktop', ' - Mobile', ' - Tablet']:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            
            if base_name != campaign_name and base_name in campaign_name_map:
                return campaign_name_map[base_name]['conversions']
        
        return None
    
    if 'Campaign' in ads_df.columns:
        ads_df['Campaign Conversions'] = ads_df['Campaign'].apply(get_conversions_by_name)
    
    return ads_df

def load_ads_export(file):
    """
    Load and clean Google Ads or Microsoft Ads ad group export.
    Handles both CSV (UTF-16 tab-separated) and XLSX formats.
    Automatically detects and maps Microsoft column names to Google format.
    """
    try:
        # Check file extension
        filename = file.name.lower()
        
        # Detect if Microsoft based on filename
        # Microsoft files: "Ad_Group_Report.xlsx" (underscore + capital G)
        # Google files: "Ad group report.csv" (space + lowercase g)
        original_name = file.name
        is_microsoft_filename = (
            'microsoft' in filename or 
            'bing' in filename or 
            'Ad_Group_Report' in original_name  # Capital G with underscores = Microsoft
        )
        
        # Debug output
        st.caption(f"📋 Loading {file.name}: Microsoft detection = {is_microsoft_filename}")
        
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            # Excel format
            if is_microsoft_filename:
                # Microsoft Excel: Skip 6 rows to get to headers
                df = pd.read_excel(file, skiprows=6)
                st.caption("🔷 Detected Microsoft Ads format (Excel)")
            else:
                # Google Excel: Skip 2 rows
                df = pd.read_excel(file, skiprows=2)
                st.caption("📊 Detected Google Ads format (Excel)")
        else:
            # CSV format - handle UTF-16 encoding
            content = file.read()
            
            # Try to decode as UTF-16
            try:
                decoded = content.decode('utf-16-le')
                lines_decoded = decoded.split('\n')
                
                if is_microsoft_filename:
                    # Microsoft CSV: Skip 6 rows
                    csv_content = '\n'.join(lines_decoded[6:])
                    st.caption("🔷 Detected Microsoft Ads format (CSV)")
                else:
                    # Google CSV: Skip 2 rows
                    csv_content = '\n'.join(lines_decoded[2:])
                    st.caption("📊 Detected Google Ads format (CSV)")
                    
                df = pd.read_csv(io.StringIO(csv_content), sep='\t')
            except:
                # Fall back to UTF-8
                file.seek(0)
                if is_microsoft_filename:
                    df = pd.read_csv(file, sep='\t', skiprows=6)
                    st.caption("🔷 Detected Microsoft Ads format (CSV UTF-8)")
                else:
                    df = pd.read_csv(file, sep='\t', skiprows=2)
                    st.caption("📊 Detected Google Ads format (CSV UTF-8)")
        
        # Detect if Microsoft by checking for Microsoft-specific columns
        if 'Account name' in df.columns or 'Impression share' in df.columns or 'Current maximum CPC' in df.columns:
            is_microsoft = True
        else:
            is_microsoft = False
        
        # Microsoft column mapping to Google format
        if is_microsoft:
            microsoft_column_map = {
                'Account name': 'Account',
                'Campaign name': 'Campaign',
                'Ad group': 'Ad group',
                'Campaign ID': 'Campaign ID',
                'Ad group ID': 'Ad group ID',
                'Ad group status': 'Ad group status',
                'Impressions': 'Impr.',
                'Clicks': 'Clicks',
                'CTR': 'CTR',
                'Avg. CPC': 'Avg. CPC',
                'Spend': 'Cost',
                'Impression share': 'Search impr. share',
                'Top impression rate': 'Search top IS',
                'Absolute top impression rate': 'Search abs. top IS',
                'Impression share lost to rank': 'Search lost IS (rank)',
                'Top impression share': 'Search top IS',
                'Absolute top impression share': 'Search abs. top IS',
                'Current maximum CPC': 'Default max. CPC',
                'Conversions': 'Conversions',
                'Conversion rate': 'Conv. rate',
            }
            
            # Rename Microsoft columns to Google equivalents
            df = df.rename(columns=microsoft_column_map)
            st.caption(f"✅ Mapped Microsoft columns to Google format")
            
            # Remove duplicate columns if any exist
            if df.columns.duplicated().any():
                duplicate_cols = df.columns[df.columns.duplicated()].tolist()
                st.warning(f"⚠️ Removing duplicate columns: {', '.join(set(duplicate_cols))}")
                df = df.loc[:, ~df.columns.duplicated()]
            
            # Clean Campaign ID and Ad Group ID - remove brackets from Microsoft format
            if 'Campaign ID' in df.columns:
                df['Campaign ID'] = df['Campaign ID'].astype(str).str.replace('[', '').str.replace(']', '').str.strip()
            if 'Ad group ID' in df.columns:
                df['Ad group ID'] = df['Ad group ID'].astype(str).str.replace('[', '').str.replace(']', '').str.strip()
        else:
            # Google Ads - clean Campaign ID (remove .0 from floats)
            if 'Campaign ID' in df.columns:
                df['Campaign ID'] = df['Campaign ID'].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x) != 'nan' else x)
            if 'Ad group ID' in df.columns:
                df['Ad group ID'] = df['Ad group ID'].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x) != 'nan' else x)
        
        # Clean numeric columns
        numeric_cols = ['Impr.', 'Clicks', 'Cost', 'Avg. CPC', 'Conversions', 'Cost / conv.']
        for col in numeric_cols:
            if col in df.columns:
                try:
                    # Check if this is actually a Series (not a DataFrame from duplicate columns)
                    if isinstance(df[col], pd.DataFrame):
                        st.warning(f"⚠️ Duplicate column '{col}' detected - using first occurrence")
                        df[col] = df[col].iloc[:, 0]
                    df[col] = clean_numeric_ads(df[col])
                except Exception as e:
                    st.warning(f"⚠️ Could not clean column '{col}': {str(e)}")
        
        # Clean percentage columns (convert to decimal)
        pct_cols = ['CTR', 'Search impr. share', 'Search top IS', 'Search abs. top IS',
                    'Search lost IS (rank)', 'Search lost top IS (rank)', 'Conv. rate',
                    'Search exact match IS']
        for col in pct_cols:
            if col in df.columns:
                try:
                    # Check if this is actually a Series (not a DataFrame from duplicate columns)
                    if isinstance(df[col], pd.DataFrame):
                        st.warning(f"⚠️ Duplicate column '{col}' detected - using first occurrence")
                        df[col] = df[col].iloc[:, 0]
                    
                    # First clean the numeric values
                    df[col] = clean_numeric_ads(df[col])
                    
                    # Check if values are already decimals (< 1) or percentages (> 1)
                    non_null_values = df[col].dropna()
                    if len(non_null_values) > 0:
                        sample_val = non_null_values.iloc[0]
                        if sample_val > 1:
                            # It's a percentage, convert to decimal
                            df[col] = df[col] / 100
                except Exception as e:
                    st.warning(f"⚠️ Could not clean percentage column '{col}': {str(e)}")
        
        # Parse bid column
        if 'Default max. CPC' in df.columns:
            df['Current Bid'] = df['Default max. CPC'].apply(parse_bid_value)
        
        return df
        
    except Exception as e:
        st.error(f"Error loading ads export: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return None

def analyze_ads_account(df, thresholds):
    """
    Analyze ad group performance and generate bid recommendations.
    
    Args:
        df: Cleaned ad group dataframe
        thresholds: Dictionary of threshold values
    
    Returns:
        Dictionary of categorized ad groups with recommendations
    """
    # Check required columns exist
    required_cols = ['Impr.', 'Ad group status']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
        st.error(f"Available columns: {', '.join(df.columns.tolist())}")
        return {
            'major_opportunity': pd.DataFrame(),
            'losing_auctions': pd.DataFrame(),
            'perfect_position': pd.DataFrame(),
            'overpaying_position_1': pd.DataFrame(),
            'poor_quality': pd.DataFrame(),
            'no_conversions': pd.DataFrame(),
            'zero_impressions': pd.DataFrame()
        }
    
    # Filter to active ad groups with data
    # Microsoft uses 'Active', Google uses 'Enabled'
    active_df = df[
        (df['Impr.'] > 0) & 
        (df['Ad group status'].isin(['Enabled', 'Active']))
    ].copy()
    
    # Show filtering results in expander
    with st.expander("🔍 Analysis Details", expanded=False):
        st.caption(f"📊 analyze_ads_account received: {len(df):,} rows, {len(df.columns)} columns")
        if 'Platform' in df.columns:
            platform_counts = df['Platform'].value_counts()
            st.caption(f"  Platforms: {dict(platform_counts)}")
        st.caption(f"  Sample columns: {df.columns[:8].tolist()}")
        st.caption(f"🔍 Filtered from {len(df):,} total ad groups to {len(active_df):,} active (Enabled/Active + Impressions > 0)")
        
    if len(active_df) == 0:
        st.warning("⚠️ No active ad groups found!")
        st.info(f"Ad group status values in data: {df['Ad group status'].unique().tolist()}")
        st.info(f"Ad groups with impressions: {(df['Impr.'] > 0).sum()}")
    
    # Check if Budget Status column exists
    has_budget_data = 'Budget Status' in active_df.columns
    
    results = {}
    
    # 1. OVERPAYING FOR POSITION 1 (prioritize if Overspending)
    overpay_filter = (
        (active_df['Search abs. top IS'] > thresholds['decrease_abs_top_is_min']) &
        (active_df['Cost'] > thresholds['min_spend_threshold'])
    )
    
    if has_budget_data:
        # Mark as high priority if Overspending
        results['overpaying_position_1'] = active_df[overpay_filter].copy()
        results['overpaying_position_1']['priority'] = results['overpaying_position_1']['Budget Status'].apply(
            lambda x: 'High' if x == 'Overspending' else 'Medium'
        )
    else:
        results['overpaying_position_1'] = active_df[overpay_filter].copy()
        results['overpaying_position_1']['priority'] = 'Medium'
    
    results['overpaying_position_1']['recommendation'] = 'Decrease bid 15-20%'
    results['overpaying_position_1']['reason'] = 'Overpaying for position 1'
    
    # Calculate recommended new bid (17.5% decrease - midpoint of 15-20%)
    if 'Current Bid' in results['overpaying_position_1'].columns:
        results['overpaying_position_1']['Recommended New Bid'] = results['overpaying_position_1']['Current Bid'] * 0.825
        results['overpaying_position_1']['Bid Change %'] = ((results['overpaying_position_1']['Recommended New Bid'] - results['overpaying_position_1']['Current Bid']) / results['overpaying_position_1']['Current Bid'] * 100).round(0).astype('Int64')
    
    # 2. LOSING AUCTIONS TO RANK (ONLY if budget has room - Underspending status)
    if has_budget_data:
        # WITH budget data: Only show if Underspending
        results['losing_auctions'] = active_df[
            (active_df['Budget Status'] == 'Underspending') &  # KEY: Must be underspending
            (active_df['Search lost IS (rank)'] > thresholds['increase_lost_is_rank_min']) &
            (active_df['Search top IS'] < thresholds['target_top_is_min']) &
            (active_df['Search impr. share'] < 0.40) &  # Missing >60% of market
            (active_df['CTR'] > thresholds['poor_ctr_threshold']) &
            (active_df['Cost'] > 10)
        ].copy()
        results['losing_auctions']['recommendation'] = 'Increase bid 30-40%'
        results['losing_auctions']['reason'] = 'Underspending + low impression share + losing auctions'
        results['losing_auctions']['priority'] = 'High'
    else:
        # WITHOUT budget data: Use impression share as proxy
        results['losing_auctions'] = active_df[
            (active_df['Search lost IS (rank)'] > thresholds['increase_lost_is_rank_min']) &
            (active_df['Search top IS'] < thresholds['target_top_is_min']) &
            (active_df['Search impr. share'] < 0.40) &  # Missing >60% of market - room to grow
            (active_df['CTR'] > thresholds['poor_ctr_threshold']) &
            (active_df['Cost'] > 10)
        ].copy()
        results['losing_auctions']['recommendation'] = 'Increase bid 30-40% (verify budget has room)'
        results['losing_auctions']['reason'] = 'Low impression share + losing auctions to rank'
        results['losing_auctions']['priority'] = 'High'
    
    # Calculate recommended new bid based on lost IS (rank)
    # Use sliding scale: the more IS lost, the bigger the increase
    if 'Current Bid' in results['losing_auctions'].columns and 'Search lost IS (rank)' in results['losing_auctions'].columns:
        def calculate_bid_increase(row):
            lost_is = row['Search lost IS (rank)']
            current_bid = row['Current Bid']
            
            if pd.isna(lost_is) or pd.isna(current_bid):
                return current_bid
            
            # Sliding scale formula: 20% base + (lost_is * 50%)
            # Lost IS 20% → +30% bid increase
            # Lost IS 30% → +35% bid increase  
            # Lost IS 40% → +40% bid increase
            # Lost IS 50% → +45% bid increase
            # Lost IS 60% → +50% bid increase
            increase_pct = 0.20 + (lost_is * 0.50)
            
            # Cap at +60% max to avoid extreme increases
            increase_pct = min(increase_pct, 0.60)
            
            return current_bid * (1 + increase_pct)
        
        results['losing_auctions']['Recommended New Bid'] = results['losing_auctions'].apply(calculate_bid_increase, axis=1)
        results['losing_auctions']['Bid Change %'] = ((results['losing_auctions']['Recommended New Bid'] - results['losing_auctions']['Current Bid']) / results['losing_auctions']['Current Bid'] * 100).round(0).astype('Int64')
    else:
        # Fallback if columns missing
        if 'Current Bid' in results['losing_auctions'].columns:
            results['losing_auctions']['Recommended New Bid'] = results['losing_auctions']['Current Bid'] * 1.35
    
    # 3. PERFECT POSITION 2-3
    results['perfect_position'] = active_df[
        (active_df['Search top IS'] >= thresholds['target_top_is_min']) &
        (active_df['Search top IS'] <= thresholds['target_top_is_max']) &
        (active_df['Search abs. top IS'] >= thresholds['target_abs_top_is_min']) &
        (active_df['Search abs. top IS'] <= thresholds['target_abs_top_is_max']) &
        (active_df['Cost'] > thresholds['min_spend_threshold'])
    ].copy()
    results['perfect_position']['recommendation'] = 'Maintain current bid'
    results['perfect_position']['reason'] = 'In ideal position 2-3 sweet spot'
    results['perfect_position']['priority'] = 'Low'
    
    # 4. POOR QUALITY
    results['poor_quality'] = active_df[
        (active_df['CTR'] < thresholds['poor_ctr_threshold']) &
        (active_df['Cost'] > thresholds['min_spend_threshold'])
    ].copy()
    results['poor_quality']['recommendation'] = 'Review ad copy/keywords OR decrease bid 30%'
    results['poor_quality']['reason'] = 'Low CTR suggests poor relevance'
    results['poor_quality']['priority'] = 'Medium'
    # Calculate recommended new bid (30% decrease)
    if 'Current Bid' in results['poor_quality'].columns:
        results['poor_quality']['Recommended New Bid'] = results['poor_quality']['Current Bid'] * 0.70
        results['poor_quality']['Bid Change %'] = ((results['poor_quality']['Recommended New Bid'] - results['poor_quality']['Current Bid']) / results['poor_quality']['Current Bid'] * 100).round(0).astype('Int64')
    
    # 5. MAJOR OPPORTUNITY
    results['major_opportunity'] = active_df[
        (active_df['CTR'] > thresholds['good_ctr_threshold']) &
        (active_df['Search impr. share'] < thresholds['low_impr_share_threshold']) &
        (active_df['Cost'] > thresholds['min_spend_threshold'])
    ].copy()
    results['major_opportunity']['recommendation'] = 'Increase bid 40-50%'
    results['major_opportunity']['reason'] = 'High quality traffic, low market share'
    results['major_opportunity']['priority'] = 'Very High'
    # Calculate recommended bid increase based on impression share gap
    # Use sliding scale: lower IS = bigger opportunity = bigger increase
    if 'Current Bid' in results['major_opportunity'].columns and 'Search impr. share' in results['major_opportunity'].columns:
        def calculate_opportunity_bid(row):
            impr_share = row['Search impr. share']
            current_bid = row['Current Bid']
            
            if pd.isna(impr_share) or pd.isna(current_bid):
                return current_bid
            
            # Sliding scale formula: 70% base - (impr_share * 100%)
            # Impr Share 5% → +65% bid increase
            # Impr Share 10% → +60% bid increase
            # Impr Share 15% → +55% bid increase
            # Impr Share 20% → +50% bid increase
            # Impr Share 25% → +45% bid increase
            # Impr Share 30% → +40% bid increase
            increase_pct = 0.70 - (impr_share * 1.00)
            
            # Floor at +30% min and cap at +70% max
            increase_pct = max(0.30, min(increase_pct, 0.70))
            
            return current_bid * (1 + increase_pct)
        
        results['major_opportunity']['Recommended New Bid'] = results['major_opportunity'].apply(calculate_opportunity_bid, axis=1)
        results['major_opportunity']['Bid Change %'] = ((results['major_opportunity']['Recommended New Bid'] - results['major_opportunity']['Current Bid']) / results['major_opportunity']['Current Bid'] * 100).round(0).astype('Int64')
    else:
        # Fallback
        if 'Current Bid' in results['major_opportunity'].columns:
            results['major_opportunity']['Recommended New Bid'] = results['major_opportunity']['Current Bid'] * 1.45
    
    # 6. NO CONVERSIONS (only if campaign conversion data available)
    if 'Campaign Conversions' in active_df.columns:
        results['no_conversions'] = active_df[
            ((active_df['Campaign Conversions'] == 0) | (active_df['Campaign Conversions'].isna())) &
            (active_df['Cost'] > 100)  # Significant spend
        ].copy()
        results['no_conversions']['recommendation'] = 'Review targeting OR pause campaign'
        results['no_conversions']['reason'] = 'High spend, zero or missing conversions'
        results['no_conversions']['priority'] = 'High'
    else:
        # If no conversion data, return empty dataframe
        results['no_conversions'] = pd.DataFrame()
    
    # 7. ZERO IMPRESSIONS
    results['zero_impressions'] = df[
        (df['Impr.'] == 0) &
        (df['Ad group status'] == 'Enabled')
    ].copy()
    results['zero_impressions']['recommendation'] = 'Consider pausing'
    results['zero_impressions']['reason'] = 'No impressions - account bloat'
    results['zero_impressions']['priority'] = 'Low'
    
    return results

def format_ads_metric(value, metric_type='currency'):
    """Format metrics for display"""
    if pd.isna(value):
        return '--'
    if metric_type == 'currency':
        return f'${value:,.2f}'
    elif metric_type == 'percentage':
        return f'{value*100:.1f}%'
    elif metric_type == 'number':
        return f'{value:,.0f}'
    return str(value)


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
            df.to_excel(xw, sheet_name=sheet_name, index=False)
            
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
    
    return output.getvalue()


def build_html_report(sheets: dict, charts: dict = None):
    """
    Build a complete HTML report with tables and charts.
    
    Args:
        sheets: Dictionary of {section_name: DataFrame}
        charts: Dictionary of {section_name: plotly_figure} (optional)
    
    Returns:
        HTML string with styled tables and embedded charts
    """
    html_parts = []
    
    # HTML Header with Melon Local branding
    html_parts.append("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lead Analyzer Report - Melon Local</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .header {
            border-bottom: 3px solid #0f5340;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        h1 {
            color: #0f5340;
            margin: 0 0 10px 0;
            font-size: 2em;
        }
        .subtitle {
            color: #666;
            font-size: 0.9em;
        }
        .section {
            margin: 40px 0;
        }
        .section-title {
            color: #0f5340;
            font-size: 1.5em;
            margin: 30px 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #e5e5e5;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 0.9em;
        }
        th {
            background: #0f5340;
            color: white;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 10px 8px;
            border-bottom: 1px solid #e5e5e5;
        }
        tr:hover {
            background: #f9f9f9;
        }
        tr.total-row {
            font-weight: bold;
            background: #f0f0f0;
            border-top: 2px solid #0f5340;
        }
        .chart-container {
            margin: 30px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 4px;
        }
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e5e5e5;
            text-align: center;
            color: #999;
            font-size: 0.85em;
        }
        .currency {
            text-align: right;
        }
        .number {
            text-align: right;
        }
        .disclaimer {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .disclaimer-title {
            font-weight: bold;
            color: #856404;
            margin-bottom: 8px;
        }
        .disclaimer-text {
            color: #856404;
            font-size: 0.9em;
            line-height: 1.5;
        }
    </style>
    <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Lead Analyzer Report</h1>
            <div class="subtitle">Generated by Melon Local • """ + datetime.now().strftime("%B %d, %Y at %I:%M %p") + """</div>
        </div>
        
        <div class="disclaimer">
            <div class="disclaimer-title">⚠️ Important: Understanding "Other" and "Unknown" Classifications</div>
            <div class="disclaimer-text">
                <strong>"Other" or "Unknown" in Platform/Product classifications represent leads that MySFDomain's tracking software was unable to categorize.</strong>
                While the majority of leads are tracked correctly, MySFDomain's platform has some limitations in lead categorization that affect a small percentage of data. 
                These tracking gaps are due to MySFDomain's software limitations and do not reflect issues with campaign setup or data quality.
            </div>
        </div>
""")
    
    # Add each section
    for section_name, df in sheets.items():
        if df is None or getattr(df, "empty", False):
            continue
        
        # Clean up the dataframe
        df = drop_effective_cost_basis(df)
        df = pretty_headers(df)
        
        html_parts.append(f'<div class="section">')
        html_parts.append(f'<h2 class="section-title">{section_name}</h2>')
        
        # Convert DataFrame to HTML table
        table_html = df.to_html(index=False, classes='data-table', escape=False, na_rep='—')
        
        # Add TOTAL row styling - replace <tr> tags that have <td>TOTAL</td>
        # Pattern to find <tr> followed by any <td> that contains exactly "TOTAL"
        pattern = r'<tr>(\s*<td[^>]*>TOTAL</td>)'
        replacement = r'<tr class="total-row">\1'
        table_html = re.sub(pattern, replacement, table_html, flags=re.IGNORECASE)
        
        html_parts.append(table_html)
        html_parts.append('</div>')
    
    # Add charts if provided
    if charts and PLOTLY_AVAILABLE:
        html_parts.append('<div class="section">')
        html_parts.append('<h2 class="section-title">Visual Analytics</h2>')
        
        for chart_name, fig in charts.items():
            if fig is not None:
                html_parts.append(f'<div class="chart-container">')
                html_parts.append(f'<h3>{chart_name}</h3>')
                # Convert plotly figure to HTML div
                chart_html = fig.to_html(include_plotlyjs=False, div_id=f"chart_{chart_name.replace(' ', '_')}")
                html_parts.append(chart_html)
                html_parts.append('</div>')
        
        html_parts.append('</div>')
    
    # Footer
    html_parts.append("""
        <div class="footer">
            <p>© Melon Local • Lead Breakdown Tool</p>
        </div>
    </div>
</body>
</html>
""")
    
    return '\n'.join(html_parts)


def dataframe_to_html(df, title="Table"):
    """Convert a single DataFrame to standalone HTML."""
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #0f5340; margin-top: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th {{ background: #0f5340; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f5f5f5; }}
        .total-row {{ font-weight: bold; background: #f0f0f0; }}
        .disclaimer {{ 
            background: #fff3cd; 
            border-left: 4px solid #ffc107; 
            padding: 12px 15px; 
            margin: 15px 0; 
            border-radius: 4px; 
            font-size: 0.9em; 
            color: #856404; 
        }}
        .footer {{ 
            margin-top: 30px; 
            padding-top: 15px; 
            border-top: 1px solid #ddd; 
            text-align: center; 
            color: #999; 
            font-size: 0.85em; 
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="disclaimer">
            ⚠️ <strong>Note:</strong> "Other" or "Unknown" classifications represent leads that MySFDomain's tracking software was unable to categorize. 
            While the majority of leads are tracked correctly, MySFDomain's platform has some limitations that affect a small percentage of data.
        </div>
        {df.to_html(index=False, escape=False)}
        <div class="footer">
            © Melon Local • Lead Breakdown Tool
        </div>
    </div>
</body>
</html>
"""
    return html.encode('utf-8')


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
    
    # Format currency and percentage columns
    for col in df_pretty.columns:
        col_l = str(col).lower()
        if is_currency_col(col_l):
            df_pretty[col] = fmt_currency_series(df_pretty[col])
        elif is_percent_col(col_l):
            ser = pd.to_numeric(df_pretty[col], errors="coerce")
            if ser.fillna(0).gt(1).any():
                df_pretty[col] = ser.apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
            else:
                df_pretty[col] = ser.apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    
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
def analyze(df, spends_input, spend_column=None, hide_unknown=False, add_device_column=False, exclude_listings_from_totals=False, include_qs=True, include_phone=True, include_sms=True):
    """
    Analyze lead data and compute metrics by platform, product, agency, and source.
    
    Args:
        df: Input dataframe with lead data
        spends_input: Dict of {agency: {platform: spend_float}}
        spend_column: Optional column name for spend data in df
        hide_unknown: Whether to filter out "Unknown" platform
        add_device_column: Whether to add device as a grouping column in aggregations
        exclude_listings_from_totals: Whether to exclude Listings from TOTAL row calculations
        include_qs: Whether to include Quote Starts in lead calculations
        include_phone: Whether to include Phone Clicks in lead calculations
        include_sms: Whether to include SMS Clicks in lead calculations
        
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
    
    # Calculate lead_opportunities based on selected lead types
    df["lead_opportunities"] = 0.0
    if include_qs:
        df["lead_opportunities"] += df[col_qs]
    if include_phone:
        df["lead_opportunities"] += df[col_phone]
    if include_sms:
        df["lead_opportunities"] += df[col_sms]

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
    
    # Build aggregation dict
    agg_dict = {
        "quote_starts": (col_qs, "sum"),
        "phone_clicks": (col_phone, "sum"),
        "sms_clicks": (col_sms, "sum"),
        "leads": ("lead_opportunities", "sum")
    }
    
    # Add spend if available (will calculate from spends_input)
    # We'll add it after groupby using the same logic as platform_agency
    
    agency_overview = df.groupby(group_cols, as_index=False).agg(**agg_dict).sort_values("leads", ascending=False).reset_index(drop=True)
    
    # Add spend column by summing across all platforms for each agency
    def calc_agency_spend(row):
        agency_name = row["agency"]
        if agency_name in spends_input:
            return sum(spends_input[agency_name].values())
        return 0.0
    
    agency_overview["spend"] = agency_overview.apply(calc_agency_spend, axis=1)
    
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
        agency_for_totals = df_for_agency_totals.groupby(group_cols, as_index=False).agg(**agg_dict)
        # Add spend for totals
        agency_for_totals["spend"] = agency_for_totals.apply(calc_agency_spend, axis=1)
    else:
        agency_for_totals = agency_overview.copy()
    
    totals_ag = {
        "agency": "TOTAL",
        "quote_starts": agency_for_totals["quote_starts"].sum(),
        "phone_clicks": agency_for_totals["phone_clicks"].sum(),
        "sms_clicks": agency_for_totals["sms_clicks"].sum(),
        "leads": agency_for_totals["leads"].sum(),
        "spend": agency_for_totals["spend"].sum()
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



# ========== MAIN APP WITH TABS ==========

# Header
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
        
        st.markdown("---")
        st.subheader("📊 Lead Types to Include")
        st.markdown("**Select which lead types to include in analysis:**")
        include_quote_starts = st.checkbox("Include Quote Starts", value=True, key="include_qs", help="Include quote start leads in totals and calculations")
        include_phone_clicks = st.checkbox("Include Phone Clicks", value=True, key="include_phone", help="Include phone click leads in totals and calculations")
        include_sms_clicks = st.checkbox("Include SMS Clicks", value=True, key="include_sms", help="Include SMS click leads in totals and calculations")
        
        # Show warning if all are unchecked
        if not (include_quote_starts or include_phone_clicks or include_sms_clicks):
            st.warning("⚠️ At least one lead type must be selected!")
        
        st.markdown("---")
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
    
    # Show file status
    if up_legacy or up_moa:
        st.markdown("**Files Uploaded:**")
        file_status = []
        if up_legacy:
            file_status.append(f"✅ Legacy: `{up_legacy.name}`")
        if up_moa:
            file_status.append(f"✅ MOA: `{up_moa.name}`")
        st.markdown(" • ".join(file_status))
        
        # Add analyze button
        if st.button("🔄 Refresh Analysis", type="primary", use_container_width=True, help="Click after uploading or changing files to reload the analysis"):
            st.rerun()
    
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
        
        # DEBUG INFO - Remove after testing
        st.info(f"📊 Debug Info: Loaded {len(dfs)} file(s). Total rows: {len(df_in)}")
        if "agency" in df_in.columns:
            agency_counts = df_in["agency"].value_counts()
            st.info(f"Agency distribution: {agency_counts.to_dict()}")
        else:
            st.error("❌ 'agency' column is missing!")
    
    
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
                campaign_col = get_col(df_in, ["campaign_id", "campaign id", "campaign"])
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
                        # Group by BOTH campaign and agency to preserve office information
                        campaign_stats = df_in.groupby([campaign_col, 'agency']).agg(agg_dict).fillna(0)
                        
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
                            campaign_col: 'Campaign',
                            'agency': 'Office'  # Rename agency to Office for clarity
                        }
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
                        
                        # Try to extract domain from stats data to identify the agent
                        # Look for URL columns in the stats report
                        import re
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
            ag_mask = df_in["agency"] == agency_name
            ag_has_rows = ag_mask.any()
            # Determine default expansion: expand if this agency file was uploaded
            default_expanded = has_legacy_file if agency_name == "Legacy" else has_moa_file
    
            with st.expander(f"{agency_name} — Overview", expanded=bool(default_expanded)):
                if not ag_has_rows:
                    st.info(f"No data uploaded for {agency_name}.")
                    continue
    
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
                            color_continuous_scale=["#eef7ef", "#47B74F"] if combined_metric_col != "cpl_platform" else ["#47B74F", "#efd568", "#f28c82"],
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
                            color_discrete_sequence=["#47B74F"]
                        )
                    elif combined_chart_type == "Area":
                        fig = px.area(
                            plat_agg,
                            x="platform",
                            y=combined_metric_col,
                            title=f"Combined: {combined_metric} by Platform",
                            labels={"platform": "Platform", combined_metric_col: combined_metric},
                            color_discrete_sequence=["#47B74F"]
                        )
                    elif combined_chart_type == "Pie":
                        fig = px.pie(
                            plat_agg,
                            values=combined_metric_col,
                            names="platform",
                            title=f"Combined: {combined_metric} Distribution",
                            color_discrete_sequence=MELON_COLORS['primary']
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
                            color_discrete_sequence=["#47B74F"]
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
            
            # Table (currency formatting handled by display_table_with_total)
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
                            "Quote Starts": "#47B74F",
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
            st.info("ℹ️ **Note:** \"Other\" or \"Unknown\" classifications represent leads that MySFDomain's tracking software was unable to categorize. While the majority of leads are tracked correctly, MySFDomain's platform has some limitations in lead categorization that affect a small percentage of data.")
            
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
            st.info("ℹ️ **Note:** \"Other\" in Product classifications represents leads where MySFDomain's tracking software was unable to identify the insurance product type. While the majority of leads are tracked correctly, MySFDomain's platform has some limitations in product categorization that affect a small percentage of data.")
            
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
                            color_discrete_sequence=MELON_COLORS['primary']
                        )
                        fig_pie.update_traces(
                            textposition='inside',
                            textinfo='percent+label',
                            hovertemplate='<b>%{label}</b><br>Leads: %{value:,.0f}<br>Share: %{percent}<extra></extra>'
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
    
        # ========== AGENCY COMPARISON SECTION ==========
        if has_legacy_file and has_moa_file:
            st.markdown('<div class="space-lg"></div>', unsafe_allow_html=True)
            st.markdown("---")
            
            with st.expander("🔄 **Agency Comparison: Legacy vs. MOA**", expanded=True):
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
                                (results["platform_agency"]["agency"] == "Legacy") | 
                                (results["platform_agency"]["platform"] == "TOTAL")
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
                                (results["platform_agency"]["agency"] == "MOA") | 
                                (results["platform_agency"]["platform"] == "TOTAL")
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
                                        color_discrete_sequence=["#114e38"]  # Official Pine color
                                    )
                                    fig_legacy.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                                    fig_legacy.update_layout(height=350, showlegend=False)
                                    st.plotly_chart(fig_legacy, use_container_width=True)
                            
                            st.markdown("**Legacy - Product Distribution**")
                            if not legacy_data.empty:
                                # Use product_agency which has agency column, NOT by_product_total
                                legacy_prod_chart = results["product_agency"].copy()
                                
                                # Filter by Legacy agency FIRST
                                if "agency" in legacy_prod_chart.columns:
                                    legacy_prod_chart = legacy_prod_chart[legacy_prod_chart["agency"] == "Legacy"].copy()
                                
                                # Then aggregate by product (if device column exists)
                                if "device" in legacy_prod_chart.columns:
                                    legacy_prod_chart = legacy_prod_chart.groupby("product", as_index=False)["leads"].sum()
                                
                                # Remove TOTAL row if present
                                legacy_prod_chart = legacy_prod_chart[legacy_prod_chart["product"] != "TOTAL"]
                                
                                if not legacy_prod_chart.empty:
                                    fig_legacy_prod = px.pie(
                                        legacy_prod_chart,
                                        values="leads",
                                        names="product",
                                        title="Legacy Product Distribution",
                                        color_discrete_sequence=MELON_COLORS['primary']  # Use same colors as MOA
                                    )
                                    fig_legacy_prod.update_traces(
                                        textposition='auto',  # Auto: inside for large slices, outside for small
                                        textinfo='label+percent',
                                        insidetextorientation='radial'
                                    )
                                    fig_legacy_prod.update_layout(
                                        height=400,
                                        showlegend=True,  # Keep legend for small slices that may be outside
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
                                # Use product_agency which has agency column, NOT by_product_total
                                moa_prod_chart = results["product_agency"].copy()
                                
                                # Filter by MOA agency FIRST
                                if "agency" in moa_prod_chart.columns:
                                    moa_prod_chart = moa_prod_chart[moa_prod_chart["agency"] == "MOA"].copy()
                                
                                # Then aggregate by product (if device column exists)
                                if "device" in moa_prod_chart.columns:
                                    moa_prod_chart = moa_prod_chart.groupby("product", as_index=False)["leads"].sum()
                                
                                # Remove TOTAL row if present
                                moa_prod_chart = moa_prod_chart[moa_prod_chart["product"] != "TOTAL"]
                                
                                if not moa_prod_chart.empty:
                                    fig_moa_prod = px.pie(
                                        moa_prod_chart,
                                        values="leads",
                                        names="product",
                                        title="MOA Product Distribution",
                                        color_discrete_sequence=MELON_COLORS['primary']  # Use same colors as Legacy
                                    )
                                    fig_moa_prod.update_traces(
                                        textposition='auto',  # Auto: inside for large slices, outside for small
                                        textinfo='label+percent',
                                        insidetextorientation='radial'
                                    )
                                    fig_moa_prod.update_layout(
                                        height=400,
                                        showlegend=True,  # Keep legend for small slices that may be outside
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
        csv_platform = df_to_csv_bytes(results["platform_overview"].copy(), style=style_flag)
        csv_ag = df_to_csv_bytes(results["agency_overview"].copy(), style=style_flag)
        csv_bpp = df_to_csv_bytes(results["by_product_platform"].copy(), style=style_flag)
        csv_prod = df_to_csv_bytes(results["by_product_total"].copy(), style=style_flag)
        csv_src = df_to_csv_bytes(results["by_source"].copy(), style=style_flag)
        
        # Generate HTML versions
        html_platform = dataframe_to_html(results["platform_overview"].copy(), "Platform Overview")
        html_ag = dataframe_to_html(results["agency_overview"].copy(), "Agency Overview")
        html_bpp = dataframe_to_html(results["by_product_platform"].copy(), "Product × Platform")
        html_prod = dataframe_to_html(results["by_product_total"].copy(), "Product Overview")
        html_src = dataframe_to_html(results["by_source"].copy(), "By Source")
    
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
    

def process_ads_platform(platform_name, ads_df, custom_thresholds, selected_account='All Accounts', filter_to_stats_account=False, shared_budget_df=None):
    """
    Process and analyze a single ads platform (Google or Microsoft).
    Shows budget reports, URL reports, campaign matching, and bid recommendations.
    
    Args:
        platform_name: Name of the platform (e.g., "Google Ads", "Microsoft Ads")
        ads_df: DataFrame with ad group data for this platform
        custom_thresholds: Dictionary of bid recommendation thresholds
        selected_account: Pre-selected account from shared filter (default: 'All Accounts')
        filter_to_stats_account: Whether to filter to stats account only (default: False)
        shared_budget_df: Pre-loaded budget DataFrame (optional, if already loaded before combining platforms)
    """
    
    st.markdown(f"**Platform:** {platform_name} • **Ad Groups:** {len(ads_df):,}")
    
    # Budget Report - use shared budget if provided, otherwise allow upload
    budget_df = None
    
    if shared_budget_df is not None:
        # Budget was already loaded before combining platforms
        budget_df = shared_budget_df
        st.markdown("---")
        st.success(f"✅ Using budget data loaded above ({len(budget_df)} accounts)")
    else:
        # Budget Report Upload (Optional) - in an expander for visibility
        st.markdown("---")
        with st.expander("💰 **Budget Report (Optional)** - Click to upload", expanded=True):
            st.markdown("""
            Upload your budget report to automatically filter recommendations by spending status.
            
            **Benefits:**
            - ✅ Only shows "Increase Bids" for accounts that are **Underspending**
            - ⚠️ Prioritizes "Decrease Bids" for accounts that are **Overspending**
            - 📊 Adds Budget Status column to all recommendations
            
            **Required columns:** Agent (or Name), Status (Underspending/Overspending/etc)
            """)
            
            budget_file = st.file_uploader(
                "Upload Budget Report (CSV or Excel)",
                type=['csv', 'xlsx', 'xls'],
                key=f'budget_upload_{platform_name}',
                help="Budget report with Agent names and Budget Status"
            )
    
        if budget_file is not None:
            try:
                # Check file extension
                filename = budget_file.name.lower()
                
                if filename.endswith('.xlsx') or filename.endswith('.xls'):
                    # Excel format
                    budget_df_raw = pd.read_excel(budget_file)
                    has_headers = True
                else:
                    # CSV format - check for headers
                    # Read first line to check if it's a header or data
                    budget_file.seek(0)
                    first_line = budget_file.readline().decode('utf-8').strip()
                    first_values = first_line.split(',')
                    
                    # Check if first line looks like headers (contains text like "Agent", "Status")
                    # vs data (contains values like "Underspending", "Overspending", agent names)
                    first_line_lower = first_line.lower()
                    has_header_keywords = any(word in first_line_lower for word in ['agent', 'status', 'budget id', 'description', 'platform'])
                    has_data_keywords = any(word in first_line_lower for word in ['underspending', 'overspending', 'optimization', 'no conversions'])
                    
                    # Reset to beginning
                    budget_file.seek(0)
                    
                    if has_header_keywords and not has_data_keywords:
                        # Has headers - read normally
                        budget_df_raw = pd.read_csv(budget_file)
                        has_headers = True
                    else:
                        # No headers or first row is data - specify column names
                        budget_df_raw = pd.read_csv(
                            budget_file,
                            header=None,
                            names=['Budget Id', 'Agent', 'Status', 'Description', 'Platform', 
                                   'Monthly Cap', 'Daily Cap', 'Spend']
                        )
                        has_headers = False
                        st.warning("⚠️ No headers detected. Assuming columns: [Budget Id, Agent, Status, Description, Platform, Monthly Cap, Daily Cap, Spend]")
                
                    # Auto-detect Agent and Status columns (case-insensitive)
                agent_col = None
                status_col = None
                
                if has_headers:
                    # Try to find columns by name
                    for col in budget_df_raw.columns:
                        col_lower = str(col).lower().strip()
                        if agent_col is None and ('agent' in col_lower and 'status' not in col_lower or col_lower == 'name'):
                            agent_col = col
                        # Prioritize "Spend Status" over other status columns
                        if status_col is None and 'spend' in col_lower and 'status' in col_lower:
                            status_col = col
                        elif status_col is None and ('status' in col_lower or col_lower == 'state'):
                            status_col = col
                else:
                    # Use default column names
                    agent_col = 'Agent'
                    status_col = 'Status'
                
                if agent_col and status_col and agent_col in budget_df_raw.columns and status_col in budget_df_raw.columns:
                    # Clean the data
                    budget_df = budget_df_raw[[agent_col, status_col]].copy()
                    budget_df.columns = ['Agent', 'Status']
                    
                    # Remove any rows with NaN in Agent or Status
                    budget_df = budget_df.dropna(subset=['Agent', 'Status'])
                    
                    # Clean agent names and status values
                    budget_df['Agent'] = budget_df['Agent'].astype(str).str.strip()
                    budget_df['Status'] = budget_df['Status'].astype(str).str.strip()
                    
                    # Remove rows where Agent or Status are empty strings
                    budget_df = budget_df[
                        (budget_df['Agent'] != '') & 
                        (budget_df['Agent'] != 'nan') &
                        (budget_df['Status'] != '') & 
                        (budget_df['Status'] != 'nan')
                    ]
                    
                    if len(budget_df) > 0:
                        st.success(f"✅ Loaded budget data for {len(budget_df)} account(s)")
                        
                        if has_headers and (agent_col != 'Agent' or status_col != 'Status'):
                            st.info(f"📋 Detected columns: '{agent_col}' → Agent, '{status_col}' → Status")
                        
                        # Show budget status summary
                        status_counts = budget_df['Status'].value_counts()
                        cols = st.columns(min(len(status_counts), 5))
                        for idx, (status, count) in enumerate(status_counts.items()):
                            if idx < 5:
                                with cols[idx]:
                                    st.metric(status, count)
                    else:
                        st.error("❌ No valid budget data found after cleaning")
                        budget_df = None
                else:
                    st.error("❌ Could not find 'Agent' and 'Status' columns")
                    st.info("Available columns: " + ", ".join([str(c) for c in budget_df_raw.columns[:10]]))
                    budget_df = None
                        
            except Exception as e:
                st.error(f"Error loading budget report: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
                budget_df = None
    
    st.markdown("---")
    
    # Match budget status to accounts if budget data provided
    if budget_df is not None:
        # Debug: Show what we're working with
        with st.expander("🔧 Budget Matching Debug", expanded=False):
            st.caption(f"Budget DF shape: {budget_df.shape}")
            st.caption(f"Budget DF columns: {budget_df.columns.tolist()}")
            if len(budget_df) > 0:
                st.caption(f"Sample row: {budget_df.iloc[0].to_dict()}")
        
        ads_df = match_budget_to_accounts(ads_df, budget_df)
        
        # Show matching summary (only if Budget Status column was added)
        if 'Budget Status' in ads_df.columns:
            matched = ads_df['Budget Status'].notna().sum()
            total = len(ads_df['Account'].unique())
            st.info(f"✅ Matched budget status for {matched} of {total} accounts")
        else:
            st.warning("⚠️ Budget data loaded but 'Budget Status' column not found")
    
    # URL Report Upload (Optional) - for precise campaign ID matching
    st.markdown("---")
    with st.expander("🔗 **URL Reports (Optional)** - For more precise campaign matching", expanded=False):
        st.markdown("""
        Upload URL reports to match campaigns by ID instead of name. This is more accurate when campaign names vary.
        
        **Benefits:**
        - ✅ More precise campaign matching using Campaign IDs
        - ✅ Handles campaign name variations automatically
        - ✅ Supports both Google Ads and Microsoft Advertising
        - ✅ Matches by Account + Ad group for perfect accuracy
        
        **Tip:** If your agent runs ads on both Google and Microsoft, upload both reports for complete coverage.
        
        **Required columns:** 
        - Account name (or Account)
        - Ad group (or Ad group name)
        - Campaign ID (e.g., `MLGDA0055-003RE2`, `MLBDSF001-001R`)
        
        **Optional:** Ad Group ID for additional precision
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            google_url_file = st.file_uploader(
                "📊 Google Ads URL Report",
                type=['csv', 'xlsx', 'xls'],
                key=f'google_url_report_{platform_name}',
                help="Google Ads report with Campaign ID and Ad group columns"
            )
        
        with col2:
            microsoft_url_file = st.file_uploader(
                "🔷 Microsoft Ads URL Report",
                type=['csv', 'xlsx', 'xls'],
                key=f'microsoft_url_report_{platform_name}',
                help="Microsoft Advertising report with Campaign ID and Ad group columns"
            )
    
    # Combine URL reports
    url_report_dfs = []
    
    if google_url_file is not None:
        try:
            # Check file extension
            filename = google_url_file.name.lower()
            
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                # Excel format
                google_df = pd.read_excel(google_url_file, skiprows=2)
                url_report_dfs.append(google_df)
                st.success(f"✅ Loaded Google URL report: {len(google_df):,} rows")
            else:
                # CSV format - try UTF-16 first (common Google Ads export format)
                try:
                    google_df = pd.read_csv(google_url_file, encoding='utf-16', sep='\t', skiprows=2)
                    url_report_dfs.append(google_df)
                    st.success(f"✅ Loaded Google URL report: {len(google_df):,} rows")
                except:
                    google_url_file.seek(0)
                    try:
                        google_df = pd.read_csv(google_url_file, encoding='utf-8')
                        url_report_dfs.append(google_df)
                        st.success(f"✅ Loaded Google URL report: {len(google_df):,} rows")
                    except Exception as e:
                        st.error(f"❌ Error loading Google URL report: {str(e)}")
        except Exception as e:
            st.error(f"❌ Error loading Google URL report: {str(e)}")
    
    if microsoft_url_file is not None:
        try:
            # Microsoft exports as Excel with header rows
            if microsoft_url_file.name.endswith('.xlsx') or microsoft_url_file.name.endswith('.xls'):
                ms_df = pd.read_excel(microsoft_url_file, skiprows=5)
                # Set first row as header
                ms_df.columns = ms_df.iloc[0]
                ms_df = ms_df[1:].reset_index(drop=True)
            else:
                # CSV format
                ms_df = pd.read_csv(microsoft_url_file, encoding='utf-16', sep='\t', skiprows=5)
                ms_df.columns = ms_df.iloc[0]
                ms_df = ms_df[1:].reset_index(drop=True)
            
            # Microsoft column names: 'Campaign name', 'Ad group' (not 'Ad group name')
            # Standardize to match Google format
            rename_map = {}
            if 'Campaign name' in ms_df.columns:
                rename_map['Campaign name'] = 'Campaign'
            # Note: Microsoft uses 'Ad group', Google uses 'Ad group' - no rename needed
            
            if rename_map:
                ms_df = ms_df.rename(columns=rename_map)
            
            # Clean Campaign ID and Ad Group ID - remove brackets
            if 'Campaign ID' in ms_df.columns:
                ms_df['Campaign ID'] = ms_df['Campaign ID'].astype(str).str.replace('[', '').str.replace(']', '').str.strip()
            if 'Ad group ID' in ms_df.columns:
                ms_df['Ad group ID'] = ms_df['Ad group ID'].astype(str).str.replace('[', '').str.replace(']', '').str.strip()
            
            url_report_dfs.append(ms_df)
            st.success(f"✅ Loaded Microsoft URL report: {len(ms_df):,} rows")
        except Exception as e:
            st.error(f"❌ Error loading Microsoft URL report: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
    
    # Combine all URL reports into one dataframe
    url_report_df = None
    if url_report_dfs:
        url_report_df = pd.concat(url_report_dfs, ignore_index=True)
        st.info(f"📊 Combined URL reports: {len(url_report_df):,} total rows from {len(url_report_dfs)} file(s)")
    
    # Enrich with campaign conversion data from Tab 1 (if available)
    if 'campaign_stats' in st.session_state:
        # Debug: Show campaign_stats structure
        with st.expander("🔍 Campaign Stats Debug (Office Matching)"):
            st.write("**Campaign Stats Shape:**", st.session_state.campaign_stats.shape)
            st.write("**Campaign Stats Columns:**", st.session_state.campaign_stats.columns.tolist())
            
            if 'Office' in st.session_state.campaign_stats.columns:
                st.write("**Office Distribution:**", st.session_state.campaign_stats['Office'].value_counts().to_dict())
                st.write("**Sample Campaign Stats (first 10):**")
                st.dataframe(st.session_state.campaign_stats[['Campaign', 'Office', 'Total Conversions']].head(10))
            else:
                st.warning("⚠️ No 'Office' column found in campaign_stats - office matching will not work!")
                st.write("**Sample Campaign Stats (first 10):**")
                st.dataframe(st.session_state.campaign_stats.head(10))
        
        ads_df = enrich_ads_with_campaign_stats(ads_df, st.session_state.campaign_stats, url_report_df)
        
        # Show matching summary only if the column was added
        if 'Campaign Conversions' in ads_df.columns:
            matched_campaigns = ads_df['Campaign Conversions'].notna().sum()
            total_ad_groups = len(ads_df)
            
            # Debug: Show matching details by office
            with st.expander("🔍 Office Matching Results"):
                if 'Office' in st.session_state.campaign_stats.columns:
                    st.write("**Matching by Office:**")
                    
                    # Sample matched campaigns
                    matched_df = ads_df[ads_df['Campaign Conversions'].notna()][['Campaign', 'Campaign Conversions']].head(10)
                    if len(matched_df) > 0:
                        st.write(f"**Matched Campaigns (showing {len(matched_df)} of {matched_campaigns}):**")
                        st.dataframe(matched_df)
                    
                    # Sample unmatched campaigns
                    unmatched_df = ads_df[ads_df['Campaign Conversions'].isna()][['Campaign']].head(10)
                    if len(unmatched_df) > 0:
                        st.write(f"**Unmatched Campaigns (showing {len(unmatched_df)} of {total_ad_groups - matched_campaigns}):**")
                        for idx, row in unmatched_df.iterrows():
                            campaign = row['Campaign']
                            # Detect what office this campaign would be assigned
                            if 'MOA' in str(campaign).upper():
                                detected_office = 'MOA'
                            else:
                                detected_office = 'Legacy'
                            st.write(f"  - `{campaign}` → Detected office: **{detected_office}**")
                else:
                    st.write("No office-based matching (Office column missing)")
            
            if url_report_df is not None:
                # Check if URL report has Campaign ID column
                has_campaign_id = any('campaign' in str(col).lower() and 'id' in str(col).lower() for col in url_report_df.columns)
                if has_campaign_id:
                    st.success(f"✅ Matched conversion data for {matched_campaigns} of {total_ad_groups} ad groups using Campaign IDs")
                else:
                    st.success(f"✅ Matched conversion data for {matched_campaigns} of {total_ad_groups} ad groups from URL report")
            else:
                # Check if ads report has Campaign ID column
                has_campaign_id_in_ads = any('campaign' in str(col).lower() and 'id' in str(col).lower() for col in ads_df.columns)
                if has_campaign_id_in_ads:
                    st.success(f"✅ Matched conversion data for {matched_campaigns} of {total_ad_groups} ad groups using Campaign IDs (direct match)")
                else:
                    st.success(f"✅ Matched conversion data for {matched_campaigns} of {total_ad_groups} ad groups using campaign names")
                    st.info("💡 Upload URL reports above for more precise matching by Campaign ID")
    
    
    # Apply account filter (passed from parent)
    with st.expander("🔧 Filter Details", expanded=False):
        st.caption(f"🔍 Account filter: selected_account='{selected_account}', has Account column={'Account' in ads_df.columns}")
        
        if selected_account != 'All Accounts' and 'Account' in ads_df.columns:
            before_filter = len(ads_df)
            st.caption(f"  Filtered from {before_filter:,} → filtering...")
        else:
            st.caption(f"  Using all {len(ads_df):,} ad groups")
    
    if selected_account != 'All Accounts' and 'Account' in ads_df.columns:
        ads_df_filtered = ads_df[ads_df['Account'] == selected_account].copy()
        
        if len(ads_df_filtered) == 0:
            available_accounts = ads_df['Account'].unique()[:10]
            st.warning(f"⚠️ No rows match account '{selected_account}'. Available accounts: {list(available_accounts)}")
    else:
        ads_df_filtered = ads_df.copy()
    
    # Apply stats account filter if checkbox is enabled
    if filter_to_stats_account:
        with st.expander("📊 Stats Account Matching", expanded=False):
            has_campaign_data = 'campaign_stats' in st.session_state and st.session_state.campaign_stats is not None
            has_domain = 'stats_agent_domain' in st.session_state and st.session_state.stats_agent_domain is not None
            
            st.caption(f"🔍 Stats account filter active. Has campaign data: {has_campaign_data}, Has domain: {has_domain}")
            
            if has_campaign_data:
                matched_account = None
                
                # Try to match using domain from URL report (if url_report_df exists)
                if 'url_report_df' in locals() and url_report_df is not None and not url_report_df.empty and 'Ad final URL' in url_report_df.columns and has_domain:
                    import re
                    stats_domain = st.session_state.stats_agent_domain
                    st.caption(f"🔍 Looking for domain: {stats_domain} in URL report")
                    
                    # Find accounts whose URLs contain the stats domain
                    for _, row in url_report_df.iterrows():
                        url = row.get('Ad final URL')
                        account = row.get('Account name')
                        
                        if pd.notna(url) and pd.notna(account) and stats_domain in str(url):
                            matched_account = str(account).strip()
                            st.caption(f"✅ Found matching account: {matched_account}")
                            break
                    
                    if not matched_account:
                        st.warning(f"⚠️ No account found with domain '{stats_domain}' in URL report")
                else:
                    st.warning("⚠️ URL report not available or missing 'Ad final URL' column")
        
        # Actually apply the filter (outside expander)
        has_campaign_data = 'campaign_stats' in st.session_state and st.session_state.campaign_stats is not None
        has_domain = 'stats_agent_domain' in st.session_state and st.session_state.stats_agent_domain is not None
        
        if has_campaign_data:
            matched_account = None
            
            # Try to match using domain from URL report (if url_report_df exists)
            if 'url_report_df' in locals() and url_report_df is not None and not url_report_df.empty and 'Ad final URL' in url_report_df.columns and has_domain:
                import re
                stats_domain = st.session_state.stats_agent_domain
                
                # Find accounts whose URLs contain the stats domain
                for _, row in url_report_df.iterrows():
                    url = row.get('Ad final URL')
                    account = row.get('Account name')
                    
                    if pd.notna(url) and pd.notna(account) and stats_domain in str(url):
                        matched_account = str(account).strip()
                        break
            
            # If we found a matching account, filter to it
            if matched_account and matched_account in ads_df_filtered['Account'].values:
                ads_df_filtered = ads_df_filtered[ads_df_filtered['Account'] == matched_account].copy()
                file_name = st.session_state.get('stats_file_uploaded', 'stats report')
                st.info(f"📊 Showing data for: **{matched_account}** (from {file_name}) — {len(ads_df_filtered):,} ad groups")
            elif matched_account:
                st.warning(f"⚠️ Account '{matched_account}' not found in ad group data")

    # Run analysis on filtered data
    with st.spinner('Analyzing account health...'):
        analysis_results = analyze_ads_account(ads_df_filtered, custom_thresholds)

    # Account Overview
    st.markdown("---")
    st.markdown("### 📊 Account Overview")
    
    # Show which platforms are included using the Platform column
    if 'Platform' in ads_df_filtered.columns:
        platform_counts = ads_df_filtered['Platform'].value_counts()
        platform_info = " + ".join([f"{platform}: {count} ad groups" for platform, count in platform_counts.items()])
        st.info(f"**Platforms:** {platform_info}")

    active_count = len(ads_df_filtered[ads_df_filtered['Impr.'] > 0])
    total_spend = ads_df_filtered['Cost'].sum()
    total_clicks = ads_df_filtered['Clicks'].sum()
    avg_cpc = total_spend / total_clicks if total_clicks > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Ad Groups", f"{len(ads_df_filtered):,}", help="Total number of ad groups in the selected account(s)")
        st.caption(f"Active: {active_count:,}")
        st.caption("ℹ️ Active = has impressions", help="Ad groups with at least 1 impression in the date range")
    with col2:
        st.metric("Total Spend", f"${total_spend:,.2f}", help="Total cost across all ad groups in the selected account(s)")
    with col3:
        st.metric("Total Clicks", f"{total_clicks:,.0f}", help="Total clicks received across all ad groups")
    with col4:
        st.metric("Avg. CPC", f"${avg_cpc:.2f}", help="Average cost per click (Total Spend ÷ Total Clicks)")

    # Recommendations by category
    st.markdown("---")
    st.markdown("### 🎯 Bid Recommendations")
    
    # Add help expander with explanations
    with st.expander("ℹ️ Understanding the Recommendations", expanded=False):
        st.markdown("""
        **How to use these recommendations:**
        
        Each tab shows ad groups that need a specific action. Click through the tabs to see your priorities.
        
        **🚀 Major Opportunities**
        - Ad groups with high CTR (>{:.0f}%) but low impression share (<{:.0f}%)
        - These are WINNING ads that aren't showing enough
        - Action: Increase bids 40-50% to capture more quality traffic
        
        **🔺 Increase Bids**
        - Losing >{:.0f}% of auctions to rank (low bids)
        - Not reaching top 3 positions (Top IS <{:.0f}%)
        - **AND impression share <40%** (missing most of the market)
        - Action: Increase bids 30-40% to capture more traffic
        - Note: If you're already at 60%+ impression share, ignore the "lost auctions" - you're getting enough traffic
        
        **✅ Maintain**
        - Already in the sweet spot (position 2-3)
        - Top IS {:.0f}-{:.0f}%, Abs Top IS {:.0f}-{:.0f}%
        - Action: Keep current bids, don't change anything
        
        **🔻 Decrease Bids**
        - Appearing in position 1 too often (>{:.0f}% of the time)
        - Overpaying for clicks you'd get at position 2-3
        - Action: Decrease bids 15-20% to drop to position 2-3
        
        **⚠️ Review**
        - Very low CTR (<{:.1f}%) suggests poor ad/keyword relevance
        - Need to fix ad copy or keywords before adjusting bids
        - Action: Review and improve ads, OR decrease bids 30%
        
        **🛑 Cleanup**
        - Enabled but zero impressions (dead weight)
        - Cluttering your account management
        - Action: Consider pausing to simplify your account
        """.format(
            custom_thresholds['good_ctr_threshold']*100,
            custom_thresholds['low_impr_share_threshold']*100,
            custom_thresholds['increase_lost_is_rank_min']*100,
            custom_thresholds['target_top_is_min']*100,
            custom_thresholds['target_top_is_min']*100,
            custom_thresholds['target_top_is_max']*100,
            custom_thresholds['target_abs_top_is_min']*100,
            custom_thresholds['target_abs_top_is_max']*100,
            custom_thresholds['decrease_abs_top_is_min']*100,
            custom_thresholds['poor_ctr_threshold']*100
        ))

    # Create tabs for each category
    rec_tabs = st.tabs([
        f"🚀 Major Opportunities ({len(analysis_results['major_opportunity'])})",
        f"🔺 Increase Bids ({len(analysis_results['losing_auctions'])})",
        f"✅ Maintain ({len(analysis_results['perfect_position'])})",
        f"🔻 Decrease Bids ({len(analysis_results['overpaying_position_1'])})",
        f"⚠️ Review ({len(analysis_results['poor_quality'])})",
        f"❌ No Conversions ({len(analysis_results['no_conversions'])})",
        f"🛑 Cleanup ({len(analysis_results['zero_impressions'])})"
    ])

    # Major Opportunities
    with rec_tabs[0]:
        df_opp = analysis_results['major_opportunity']
        if len(df_opp) > 0:
            st.markdown(f"""
            **Logic:** CTR >{custom_thresholds['good_ctr_threshold']*100:.0f}% 
            AND Impression Share <{custom_thresholds['low_impr_share_threshold']*100:.0f}%

            These ad groups have great engagement but low market share. 
            Major growth potential!
            """)

            # Display table
            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign', 'Campaign Conversions', 
                          'Current Bid', 'Recommended New Bid',
                          'CTR', 'Search impr. share', 'Search lost IS (rank)', 
                          'Cost', 'Clicks']
            
            # Only include bid columns if they exist
            available_cols = [col for col in display_cols if col in df_opp.columns]

            display_df = df_opp[available_cols].copy()
            
            # Format metrics
            if 'Campaign Conversions' in display_df.columns:
                display_df['Campaign Conversions'] = display_df['Campaign Conversions'].apply(lambda x: format_ads_metric(x, 'number'))
            if 'Current Bid' in display_df.columns:
                display_df['Current Bid'] = display_df['Current Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Recommended New Bid' in display_df.columns:
                display_df['Recommended New Bid'] = display_df['Recommended New Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'CTR' in display_df.columns:
                display_df['CTR'] = display_df['CTR'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search impr. share' in display_df.columns:
                display_df['Search impr. share'] = display_df['Search impr. share'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search lost IS (rank)' in display_df.columns:
                display_df['Search lost IS (rank)'] = display_df['Search lost IS (rank)'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Cost' in display_df.columns:
                display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Clicks' in display_df.columns:
                display_df['Clicks'] = display_df['Clicks'].apply(lambda x: format_ads_metric(x, 'number'))
            
            # Rename columns with helpful descriptions
            rename_map = {
                'Current Bid': 'Current Bid',
                'Recommended New Bid': 'New Bid',
                'Campaign Conversions': 'Campaign Leads',
                'CTR': 'CTR',
                'Search impr. share': 'Impr. Share',
                'Search lost IS (rank)': 'Lost to Bids'
            }
            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
            
            # Metric legend above table
            st.markdown("""
            <div style='background: #f0f2f6; padding: 12px; border-radius: 8px; margin-bottom: 12px;'>
                <strong>📊 Column Definitions:</strong><br/>
                <span style='color: #666; font-size: 14px;'>
                <b>CTR (Click Rate)</b> = Clicks ÷ Impressions • Measures ad relevance and quality<br/>
                <b>Impr. Share (% of market)</b> = Your impressions ÷ Total available impressions • Shows how much traffic you're capturing<br/>
                <b>Lost to Low Bids (%)</b> = Auctions lost because your bid was too low • Higher = more room to grow
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Add metric explanations below table
            st.caption("💡 **CTR** = Click-through rate (engagement quality) | **Impr. Share** = % of available impressions you're getting | **Lost to Low Bids** = % of auctions you're losing because your bid is too low")

            # Download button
            csv = df_opp.to_csv(index=False)
            st.download_button(
                "⬇️ Download Major Opportunities",
                csv,
                "major_opportunities.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.info("No major opportunities found. All high-CTR ad groups are capturing good impression share.")

    # Increase Bids
    with rec_tabs[1]:
        df_inc = analysis_results['losing_auctions']
        if len(df_inc) > 0:
            # Show different message if budget data is present
            has_budget = 'Budget Status' in df_inc.columns and df_inc['Budget Status'].notna().any()
            
            if has_budget:
                st.markdown(f"""
                **Logic (WITH Budget Data):** Budget Status = Underspending
                AND Lost IS (rank) >{custom_thresholds['increase_lost_is_rank_min']*100:.0f}% 
                AND Top IS <{custom_thresholds['target_top_is_min']*100:.0f}%
                AND Impression Share <40%

                ✅ **These accounts have confirmed budget room to scale!**
                
                Only showing ad groups where the account is actively underspending. 
                You can safely increase these bids to capture more traffic.
                """)
            else:
                st.markdown(f"""
                **Logic (WITHOUT Budget Data):** Lost IS (rank) >{custom_thresholds['increase_lost_is_rank_min']*100:.0f}% 
                AND Top IS <{custom_thresholds['target_top_is_min']*100:.0f}%
                AND Impression Share <40%

                ⚠️ **Verify budget has room before increasing!**
                
                Upload budget report to automatically filter by underspending accounts.
                """)


            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign', 'Campaign Conversions', 'Budget Status', 
                          'Current Bid', 'Recommended New Bid', 'Bid Change %', 'Search impr. share', 
                          'Search lost IS (rank)', 'Search top IS', 'CTR', 'Cost']
            
            # Only include columns that exist
            available_cols = [col for col in display_cols if col in df_inc.columns]
            display_df = df_inc[available_cols].copy()
            
            # Format metrics
            if 'Campaign Conversions' in display_df.columns:
                display_df['Campaign Conversions'] = display_df['Campaign Conversions'].apply(lambda x: format_ads_metric(x, 'number'))
            if 'Current Bid' in display_df.columns:
                display_df['Current Bid'] = display_df['Current Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Recommended New Bid' in display_df.columns:
                display_df['Recommended New Bid'] = display_df['Recommended New Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Bid Change %' in display_df.columns:
                display_df['Bid Change %'] = display_df['Bid Change %'].apply(lambda x: f"+{int(x)}%" if pd.notna(x) else '--')
            if 'Search impr. share' in display_df.columns:
                display_df['Search impr. share'] = display_df['Search impr. share'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search lost IS (rank)' in display_df.columns:
                display_df['Search lost IS (rank)'] = display_df['Search lost IS (rank)'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search top IS' in display_df.columns:
                display_df['Search top IS'] = display_df['Search top IS'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'CTR' in display_df.columns:
                display_df['CTR'] = display_df['CTR'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Cost' in display_df.columns:
                display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
            
            # Rename columns
            rename_map = {
                'Current Bid': 'Current Bid',
                'Recommended New Bid': 'New Bid',
                'Search impr. share': 'Impr. Share',
                'Search lost IS (rank)': 'Lost to Bids',
                'Search top IS': 'Top 3 %'
            }
            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
            
            # Metric legend
            st.markdown("""
            <div style='background: #f0f2f6; padding: 12px; border-radius: 8px; margin-bottom: 12px;'>
                <strong>📊 Column Definitions:</strong><br/>
                <span style='color: #666; font-size: 14px;'>
                <b>Impr. Share</b> = % of available traffic you're capturing • <40% = room to grow<br/>
                <b>Lost to Bids</b> = % of auctions you lost because bid was too low<br/>
                <b>Top 3 %</b> = % of time you appear in positions 1-3 • Target: 60-80%<br/>
                <b>Key insight:</b> Only increase if impression share is LOW. If you're already at 60%+ impression share, you're getting enough traffic.
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.caption("💡 **Lost to Low Bids** = % of auctions you're losing | **Top 3 Position** = % of time you appear in positions 1-3 | **Target: 60-80%**")

            csv = df_inc.to_csv(index=False)
            st.download_button(
                "⬇️ Download Increase Bid List",
                csv,
                "increase_bids.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.success("✅ No ad groups losing significant auctions to rank.")

    # Maintain
    with rec_tabs[2]:
        df_maintain = analysis_results['perfect_position']
        if len(df_maintain) > 0:
            st.markdown(f"""
            **Logic:** Top IS {custom_thresholds['target_top_is_min']*100:.0f}-{custom_thresholds['target_top_is_max']*100:.0f}% 
            AND Abs. Top IS {custom_thresholds['target_abs_top_is_min']*100:.0f}-{custom_thresholds['target_abs_top_is_max']*100:.0f}%

            Perfect position 2-3 sweet spot! Keep these bids as-is.
            """)

            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign', 'Campaign Conversions', 
                          'Search top IS', 'Search abs. top IS', 'CTR', 'Avg. CPC', 'Cost']

            # Only include columns that exist
            available_cols = [col for col in display_cols if col in df_maintain.columns]
            display_df = df_maintain[available_cols].copy()
            
            # Format metrics
            if 'Campaign Conversions' in display_df.columns:
                display_df['Campaign Conversions'] = display_df['Campaign Conversions'].apply(lambda x: format_ads_metric(x, 'number'))
            display_df['Search top IS'] = display_df['Search top IS'].apply(lambda x: format_ads_metric(x, 'percentage'))
            display_df['Search abs. top IS'] = display_df['Search abs. top IS'].apply(lambda x: format_ads_metric(x, 'percentage'))
            display_df['CTR'] = display_df['CTR'].apply(lambda x: format_ads_metric(x, 'percentage'))
            display_df['Avg. CPC'] = display_df['Avg. CPC'].apply(lambda x: format_ads_metric(x, 'currency'))
            display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
            
            # Rename columns
            display_df = display_df.rename(columns={
                'Search top IS': 'Top 3 Position (%)',
                'Search abs. top IS': 'Position 1 (%)',
                'CTR': 'CTR (Click Rate)',
                'Avg. CPC': 'Avg. CPC'
            })
            
            # Metric legend
            st.markdown("""
            <div style='background: #d1ecf1; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #47B74F;'>
                <strong>✅ Column Definitions (Perfect Balance):</strong><br/>
                <span style='color: #666; font-size: 14px;'>
                <b>Top 3 Position (%)</b> = How often you show in positions 1-3 • Sweet spot: 60-80%<br/>
                <b>Position 1 (%)</b> = How often you're in the #1 spot • Sweet spot: 20-40% (not too much!)<br/>
                <b>Why this is perfect:</b> You're visible in top positions most of the time, but not overpaying for #1
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.caption("💡 **Perfect Balance:** Top 3 Position 60-80% + Position 1 only 20-40% = You're in the cost-efficient sweet spot!")
        else:
            st.warning("No ad groups currently in the perfect position 2-3 sweet spot.")

    # Decrease Bids
    with rec_tabs[3]:
        df_dec = analysis_results['overpaying_position_1']
        if len(df_dec) > 0:
            st.markdown(f"""
            **Logic:** Abs. Top IS >{custom_thresholds['decrease_abs_top_is_min']*100:.0f}%

            These ad groups are appearing in position 1 too often. Decrease bids to drop to position 2-3.
            """)

            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign', 'Campaign Conversions', 
                          'Budget Status', 'Current Bid', 'Recommended New Bid', 'Bid Change %',
                          'Search abs. top IS', 'Search top IS', 'Cost']
            
            # Only include columns that exist
            available_cols = [col for col in display_cols if col in df_dec.columns]
            display_df = df_dec[available_cols].copy()
            
            # Format metrics
            if 'Campaign Conversions' in display_df.columns:
                display_df['Campaign Conversions'] = display_df['Campaign Conversions'].apply(lambda x: format_ads_metric(x, 'number'))
            if 'Current Bid' in display_df.columns:
                display_df['Current Bid'] = display_df['Current Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Recommended New Bid' in display_df.columns:
                display_df['Recommended New Bid'] = display_df['Recommended New Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Bid Change %' in display_df.columns:
                display_df['Bid Change %'] = display_df['Bid Change %'].apply(lambda x: f"{int(x)}%" if pd.notna(x) else '--')
            if 'Search abs. top IS' in display_df.columns:
                display_df['Search abs. top IS'] = display_df['Search abs. top IS'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search top IS' in display_df.columns:
                display_df['Search top IS'] = display_df['Search top IS'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Cost' in display_df.columns:
                display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
            
            # Rename columns
            rename_map = {
                'Current Bid': 'Current Bid',
                'Recommended New Bid': 'New Bid',
                'Search abs. top IS': 'Position 1 %',
                'Search top IS': 'Top 3 %'
            }
            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
            
            # Metric legend
            st.markdown("""
            <div style='background: #fff3cd; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #CC8F15;'>
                <strong>⚠️ Column Definitions (Overpaying):</strong><br/>
                <span style='color: #666; font-size: 14px;'>
                <b>Position 1 (%)</b> = How often you're in the #1 spot • >50% = You're overpaying!<br/>
                <b>Top 3 Position (%)</b> = Total time in positions 1-3 • You'll stay visible after decreasing bids<br/>
                <b>The problem:</b> Position 1 is expensive. You'd get most of these clicks at position 2-3 for less money
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.caption("💡 **Overpaying:** Position 1 is expensive! Target: Show position 1 only 20-40% of the time, not 50%+")

            csv = df_dec.to_csv(index=False)
            st.download_button(
                "⬇️ Download Decrease Bid List",
                csv,
                "decrease_bids.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.success("✅ Position 1 strategy is working well - not overpaying!")

    # Review
    with rec_tabs[4]:
        df_review = analysis_results['poor_quality']
        if len(df_review) > 0:
            st.markdown(f"""
            **Logic:** CTR <{custom_thresholds['poor_ctr_threshold']*100:.1f}% AND spend >${custom_thresholds['min_spend_threshold']:.0f}

            Low engagement suggests poor ad/keyword relevance. Fix ads before adjusting bids.
            """)

            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign', 'Campaign Conversions', 
                          'Current Bid', 'Recommended New Bid', 'Bid Change %', 'CTR', 'Search impr. share', 
                          'Cost', 'Clicks']
            
            # Only include columns that exist
            available_cols = [col for col in display_cols if col in df_review.columns]
            display_df = df_review[available_cols].copy()
            
            # Format metrics
            if 'Campaign Conversions' in display_df.columns:
                display_df['Campaign Conversions'] = display_df['Campaign Conversions'].apply(lambda x: format_ads_metric(x, 'number'))
            if 'Current Bid' in display_df.columns:
                display_df['Current Bid'] = display_df['Current Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Recommended New Bid' in display_df.columns:
                display_df['Recommended New Bid'] = display_df['Recommended New Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Bid Change %' in display_df.columns:
                display_df['Bid Change %'] = display_df['Bid Change %'].apply(lambda x: f"{int(x)}%" if pd.notna(x) else '--')
            if 'CTR' in display_df.columns:
                display_df['CTR'] = display_df['CTR'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search impr. share' in display_df.columns:
                display_df['Search impr. share'] = display_df['Search impr. share'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Cost' in display_df.columns:
                display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Clicks' in display_df.columns:
                display_df['Clicks'] = display_df['Clicks'].apply(lambda x: format_ads_metric(x, 'number'))
            
            # Rename columns
            rename_map = {
                'Current Bid': 'Current Bid',
                'Recommended New Bid': 'New Bid',
                'Search impr. share': 'Impr. Share'
            }
            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
            
            # Metric legend
            st.markdown("""
            <div style='background: #f8d7da; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #E9736E;'>
                <strong>🚨 Column Definitions (Quality Issues):</strong><br/>
                <span style='color: #666; font-size: 14px;'>
                <b>CTR (Click Rate)</b> = Clicks ÷ Impressions • <1.5% is very low = poor relevance<br/>
                <b>Impr. Share (%)</b> = How much traffic you're getting • Low share + low CTR = double problem<br/>
                <b>The issue:</b> People see your ad but don't click. Your ad or keywords don't match their search intent
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.caption("💡 **Low CTR Warning:** CTR <1.5% usually means your ad or keywords don't match what people are searching for. Fix the ad first!")

            csv = df_review.to_csv(index=False)
            st.download_button(
                "⬇️ Download Review List",
                csv,
                "review_quality.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.success("✅ No major quality issues detected.")

    # No Conversions (only shows if campaign data available)
    with rec_tabs[5]:
        df_no_conv = analysis_results['no_conversions']
        if len(df_no_conv) > 0:
            st.markdown(f"""
            **Logic:** Campaign has 0 conversions AND Cost >$100

            These ad groups are in campaigns spending money but generating ZERO leads. 
            This is the highest priority issue - you're wasting budget.
            
            **Possible causes:**
            - Wrong audience targeting
            - Landing page issues  
            - Tracking problems
            - Poor keyword intent match
            """)

            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign', 'Campaign Conversions', 
                          'Current Bid', 'Cost', 'Clicks', 'CTR', 'Search impr. share']
            
            # Only include columns that exist
            available_cols = [col for col in display_cols if col in df_no_conv.columns]
            display_df = df_no_conv[available_cols].copy()
            
            # Format metrics
            if 'Campaign Conversions' in display_df.columns:
                display_df['Campaign Conversions'] = display_df['Campaign Conversions'].apply(lambda x: format_ads_metric(x, 'number'))
            if 'Current Bid' in display_df.columns:
                display_df['Current Bid'] = display_df['Current Bid'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Cost' in display_df.columns:
                display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
            if 'Clicks' in display_df.columns:
                display_df['Clicks'] = display_df['Clicks'].apply(lambda x: format_ads_metric(x, 'number'))
            if 'CTR' in display_df.columns:
                display_df['CTR'] = display_df['CTR'].apply(lambda x: format_ads_metric(x, 'percentage'))
            if 'Search impr. share' in display_df.columns:
                display_df['Search impr. share'] = display_df['Search impr. share'].apply(lambda x: format_ads_metric(x, 'percentage'))
            
            # Rename columns
            rename_map = {
                'Campaign Conversions': 'Campaign Leads',
                'Search impr. share': 'Impr. Share'
            }
            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
            
            # Metric legend
            st.markdown("""
            <div style='background: #f8d7da; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #E9736E;'>
                <strong>🚨 CRITICAL: Zero Conversions!</strong><br/>
                <span style='color: #666; font-size: 14px;'>
                <b>Campaign Leads</b> = Total conversions for the entire campaign (all ad groups combined)<br/>
                <b>Action</b> = PAUSE these campaigns immediately OR investigate why tracking shows zero conversions<br/>
                <b>Warning:</b> You're spending money and getting clicks but NO leads
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Show total wasted spend
            total_waste = df_no_conv['Cost'].sum()
            st.error(f"💸 **Total Wasted Spend:** ${total_waste:,.2f} across {len(df_no_conv)} ad groups with zero conversions")

            csv = df_no_conv.to_csv(index=False)
            st.download_button(
                "⬇️ Download No Conversions List",
                csv,
                "no_conversions.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            if 'Campaign Conversions' in ads_df_filtered.columns:
                st.success("✅ All campaigns with significant spend are generating conversions!")
            else:
                st.info("ℹ️ No campaign conversion data available. Upload stats in Tab 1 to see this analysis.")

    # Cleanup
    with rec_tabs[6]:
        df_cleanup = analysis_results['zero_impressions']
        if len(df_cleanup) > 0:
            st.markdown(f"""
            **Logic:** Zero impressions + Enabled status

            These {len(df_cleanup):,} ad groups are enabled but receiving no traffic. 
            Consider pausing to simplify account management.
            """)

            display_cols = ['Platform', 'Account', 'Ad group', 'Campaign']
            if 'Default max. CPC' in df_cleanup.columns:
                display_cols.append('Default max. CPC')
            
            # Only include columns that exist
            available_cols = [col for col in display_cols if col in df_cleanup.columns]

            st.dataframe(df_cleanup[available_cols], use_container_width=True, hide_index=True)

            csv = df_cleanup.to_csv(index=False)
            st.download_button(
                "⬇️ Download Zero Impression List (for bulk pausing)",
                csv,
                "zero_impressions_cleanup.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.success("✅ No zero-impression ad groups to clean up.")


# ========== TAB 2: ADS ACCOUNT HEALTH ==========
with main_tab2:
        st.markdown("### Ads Account Health Checker")
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
                
                with filter_col1:
                    account_options = ['All Accounts'] + all_accounts
                    selected_account = st.selectbox(
                        "Filter by Account",
                        options=account_options,
                        key='shared_account_filter',
                        help="View data for a specific agent across all platforms, or all accounts combined"
                    )
                
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
                    shared_budget_df  # Pass the budget data
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
