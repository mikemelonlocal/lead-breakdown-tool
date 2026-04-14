"""
Ads Account Health analysis for Lead Analyzer.
Google Ads and Microsoft Ads bid optimization.
"""
import io
import re
import tempfile
import pathlib
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np
import streamlit as st

from constants import ADS_THRESHOLDS, MELON_COLORS
from utils import get_col, pretty_headers, fmt_currency_series
from classification import classify_platform, extract_utm_from_campaign_id

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
    
    # Build campaign map from Tab 1 stats using Domain + Campaign prefix
    # This allows matching URLs like "insurancequotesouth.com/.../cmpid=MLGDF172-001R" 
    # to stats like "insurancequotesouth.com + MLGDF172-001HVT1"
    campaign_map = {}
    
    # Check if Domain and Office columns exist
    has_domain = 'Domain' in campaign_stats_df.columns
    has_office = 'Office' in campaign_stats_df.columns
    
    if 'Campaign' in campaign_stats_df.columns:
        for _, row in campaign_stats_df.iterrows():
            campaign_id = str(row['Campaign']).strip() if pd.notna(row['Campaign']) else None
            if not campaign_id or campaign_id == 'nan':
                continue
            
            # Extract campaign prefix (MLGDF172-001HVT1 -> MLGDF172)
            campaign_prefix = campaign_id.split('-')[0] if '-' in campaign_id else campaign_id
            
            # Build key: (Domain, Campaign_Prefix, Office) or variations
            if has_domain and has_office:
                domain = str(row.get('Domain', '')).strip().lower() if pd.notna(row.get('Domain')) else None
                office = row.get('Office', 'Unknown')
                if domain:
                    # Normalize domain (remove www., http://, https://)
                    domain = domain.replace('http://', '').replace('https://', '').replace('www.', '')
                    key = (domain, campaign_prefix, office)
                    campaign_map[key] = {
                        'conversions': row.get('Total Conversions', 0),
                        'full_campaign_id': campaign_id
                    }
            elif has_domain:
                domain = str(row.get('Domain', '')).strip().lower() if pd.notna(row.get('Domain')) else None
                if domain:
                    domain = domain.replace('http://', '').replace('https://', '').replace('www.', '')
                    key = (domain, campaign_prefix)
                    campaign_map[key] = {
                        'conversions': row.get('Total Conversions', 0),
                        'full_campaign_id': campaign_id
                    }
            elif has_office:
                office = row.get('Office', 'Unknown')
                key = (campaign_prefix, office)
                campaign_map[key] = {
                    'conversions': row.get('Total Conversions', 0),
                    'full_campaign_id': campaign_id
                }
            else:
                key = campaign_prefix
                campaign_map[key] = {
                    'conversions': row.get('Total Conversions', 0),
                    'full_campaign_id': campaign_id
                }
    
    # ── STRATEGY 0: Exact cmpid matching via URL report (most precise) ──
    # URL report contains (Campaign, Ad group) → Ad final URL with cmpid=MLGDF172-001R
    # Tab 1 stats has Campaign IDs like MLGDF172-001R with per-campaign-ID conversions
    # Match each Tab 2 (Campaign, Ad group) → its cmpid → Tab 1 stats value
    cmpid_conv_map = {}  # {cmpid_upper: total_conversions across all domains}
    if 'Campaign' in campaign_stats_df.columns:
        for _, row in campaign_stats_df.iterrows():
            cid = str(row.get('Campaign', '')).strip().upper()
            if not cid or cid == 'NAN':
                continue
            convs = float(row.get('Total Conversions', 0) or 0)
            cmpid_conv_map[cid] = cmpid_conv_map.get(cid, 0) + convs

    # Build (Campaign, Ad group) → cmpid lookup from URL report
    adgroup_cmpid_map = {}
    if url_report_df is not None and not url_report_df.empty:
        url_col = None
        for col in url_report_df.columns:
            if 'final url' in str(col).lower() and 'suffix' not in str(col).lower():
                url_col = col
                break
        if url_col and 'Campaign' in url_report_df.columns and 'Ad group' in url_report_df.columns:
            for _, row in url_report_df.iterrows():
                url = str(row.get(url_col, '')) if pd.notna(row.get(url_col)) else ''
                if not url or url == 'nan':
                    continue
                m = re.search(r'cmpid=([A-Z0-9\-]+)', url, re.IGNORECASE)
                if not m:
                    continue
                cmpid = m.group(1).upper()
                camp = str(row.get('Campaign', '')).strip()
                adg = str(row.get('Ad group', '')).strip()
                key = (camp, adg)
                # Keep the first cmpid for each (Campaign, Ad group) pair
                if key not in adgroup_cmpid_map:
                    adgroup_cmpid_map[key] = cmpid

    def _match_by_cmpid(row):
        """Match Tab 2 ad group to Tab 1 stats by exact cmpid from URL report."""
        camp = str(row.get('Campaign', '')).strip() if pd.notna(row.get('Campaign')) else ''
        adg = str(row.get('Ad group', '')).strip() if pd.notna(row.get('Ad group')) else ''
        if not camp or not adg:
            return None
        cmpid = adgroup_cmpid_map.get((camp, adg))
        if not cmpid:
            return None
        # Direct lookup
        if cmpid in cmpid_conv_map:
            return cmpid_conv_map[cmpid]
        # Fuzzy: Tab 1 cmpid may have extra suffix (e.g., URL cmpid=MLGDF172-001R, Tab 1 has MLGDF172-001RE2)
        for stats_cid, convs in cmpid_conv_map.items():
            if stats_cid.startswith(cmpid) or cmpid.startswith(stats_cid):
                return convs
        return None

    # Run cmpid matching first (most precise — per-ad-group)
    ads_df['Campaign Conversions'] = ads_df.apply(_match_by_cmpid, axis=1).astype('float64')

    # Debug summary
    _matched = ads_df['Campaign Conversions'].notna().sum()
    _total_conv = ads_df['Campaign Conversions'].sum()
    st.caption(f"🎯 cmpid matching: {_matched}/{len(ads_df)} matched, total={_total_conv:,.0f} (URL report: {len(adgroup_cmpid_map)} mappings, Tab 1 stats: {len(cmpid_conv_map)} campaign IDs)")

    # Strategy 1: Match using Campaign Name from ad group report
    # Campaign names like "Legacy - Fire 172 - SF Renters Insurance - Desktop"
    # Match to stats Campaign IDs like "MLGDF172-001HVT1" by extracting "F172" code
    
    def get_conversions_by_campaign_name(row):
        """Match ad group to stats using Campaign + Ad Group codes."""
        campaign_name = str(row.get('Campaign', '')).strip() if pd.notna(row.get('Campaign')) else None
        ad_group_name = str(row.get('Ad group', '')).strip() if pd.notna(row.get('Ad group')) else None
        
        if not campaign_name or not ad_group_name:
            return None

        # Extract campaign number from campaign name
        # Remove office prefix first (Legacy/MOA)
        clean_campaign = re.sub(r'^(Legacy|MOA)\s*-\s*', '', campaign_name, flags=re.IGNORECASE).strip()
        
        # Extract leading number (e.g., "001 - SF Brand" -> "001", "172 - Fire 172" -> "172")
        campaign_num_match = re.match(r'^(\d+)', clean_campaign)
        if not campaign_num_match:
            return None
        
        campaign_num = campaign_num_match.group(1)
        
        # Extract ad group number from ad group name
        # Patterns: "F172-001 SF Renters" -> "001", "001-1 SF" -> "001"
        ad_group_num = None
        
        # Try pattern: F###-### or just ###-###
        ag_match = re.search(r'[A-Z]?\d+-(\d+)', ad_group_name)
        if ag_match:
            ad_group_num = ag_match.group(1)
        else:
            # Try just leading number
            ag_num_match = re.match(r'^(\d+)', ad_group_name)
            if ag_num_match:
                ad_group_num = ag_num_match.group(1)
        
        # Detect office from campaign name
        office = detect_office(campaign_name)
        
        # Extract domain if available in ad group report
        domain = None
        if 'Final URL' in row:
            final_url = str(row.get('Final URL', '')).strip() if pd.notna(row.get('Final URL')) else None
            if final_url and final_url != 'nan':
                match = re.search(r'https?://(?:www\.)?([^/?]+)', final_url)
                if match:
                    domain = match.group(1).lower()
        
        # Debug: Store matching attempt info
        matching_attempts = []
        
        # Match using campaign + ad group numbers in stats Campaign IDs
        # Stats IDs like: MLBDF172-001RE2
        # We need: campaign=172, ad_group=001 → matches "F172" and "001"
        matched_conversion = None
        matched_campaign_id = None
        
        for key, data in campaign_map.items():
            # Unpack key based on structure
            if isinstance(key, tuple):
                if len(key) == 3:  # (domain, campaign_prefix, office)
                    stats_domain, stats_prefix, stats_office = key
                    
                    # Check if both campaign number AND ad group number are in the stats Campaign ID
                    has_campaign = campaign_num in stats_prefix
                    has_ad_group = ad_group_num and ad_group_num in stats_prefix
                    
                    if has_campaign and has_ad_group:
                        matching_attempts.append(f"Checked (domain={stats_domain}, prefix={stats_prefix}, office={stats_office})")
                    
                    if domain and stats_domain == domain and has_campaign and has_ad_group and stats_office == office:
                        matched_conversion = data['conversions']
                        matched_campaign_id = data.get('full_campaign_id', stats_prefix)
                        matching_attempts.append(f"✅ MATCHED: {stats_prefix} with {data['conversions']} conversions")
                        break
                elif len(key) == 2:  # (domain, campaign_prefix) or (campaign_prefix, office)
                    if has_domain:
                        stats_domain, stats_prefix = key
                        
                        has_campaign = campaign_num in stats_prefix
                        has_ad_group = ad_group_num and ad_group_num in stats_prefix
                        
                        if has_campaign and has_ad_group:
                            matching_attempts.append(f"Checked (domain={stats_domain}, prefix={stats_prefix})")
                        
                        if domain and stats_domain == domain and has_campaign and has_ad_group:
                            matched_conversion = data['conversions']
                            matched_campaign_id = data.get('full_campaign_id', stats_prefix)
                            matching_attempts.append(f"✅ MATCHED: {stats_prefix} with {data['conversions']} conversions")
                            break
                    else:
                        stats_prefix, stats_office = key
                        
                        has_campaign = campaign_num in stats_prefix
                        has_ad_group = ad_group_num and ad_group_num in stats_prefix
                        
                        if has_campaign and has_ad_group:
                            matching_attempts.append(f"Checked (prefix={stats_prefix}, office={stats_office})")
                        
                        if has_campaign and has_ad_group and stats_office == office:
                            matched_conversion = data['conversions']
                            matched_campaign_id = data.get('full_campaign_id', stats_prefix)
                            matching_attempts.append(f"✅ MATCHED: {stats_prefix} with {data['conversions']} conversions")
                            break
            else:  # Single campaign_prefix
                has_campaign = campaign_num in key
                has_ad_group = ad_group_num and ad_group_num in key
                
                if has_campaign and has_ad_group:
                    matching_attempts.append(f"Checked prefix={key}")
                    matched_conversion = data['conversions']
                    matched_campaign_id = data.get('full_campaign_id', key)
                    matching_attempts.append(f"✅ MATCHED: {key} with {data['conversions']} conversions")
                    break
        
        # Store debug info for first few rows
        if 'matching_debug' not in st.session_state:
            st.session_state.matching_debug = []
        
        if len(st.session_state.matching_debug) < 10:
            st.session_state.matching_debug.append({
                'campaign_name': campaign_name,
                'ad_group_name': ad_group_name,
                'campaign_num': campaign_num,
                'ad_group_num': ad_group_num,
                'office': office,
                'domain': domain,
                'matched': matched_conversion is not None,
                'conversions': matched_conversion,
                'matched_campaign_id': matched_campaign_id,
                'attempts': matching_attempts
            })
        
        return matched_conversion
    
    _via_campaign_name = ads_df.apply(get_conversions_by_campaign_name, axis=1).astype('float64')
    mask = ads_df['Campaign Conversions'].isna()
    ads_df.loc[mask, 'Campaign Conversions'] = _via_campaign_name[mask]

    # Continue with additional strategies for rows that didn't match
    # First: Process URL report if available (for debug info)
    if url_report_df is not None and not url_report_df.empty:
        # Store debug info in session state
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = {}
        
        st.session_state.debug_info['url_report_columns'] = url_report_df.columns.tolist()
        st.session_state.debug_info['url_report_shape'] = url_report_df.shape
        
        # FIRST: Try to match using Campaign ID column from URL report (most reliable)
        url_campaign_id_col = None
        for col in url_report_df.columns:
            if 'campaign' in col.lower() and 'id' in col.lower():
                url_campaign_id_col = col
                break
        
        if url_campaign_id_col and campaign_map:
            # Create mapping: (Account + Ad Group) -> Campaign ID
            ad_group_to_campaign_id = {}
            
            for _, row in url_report_df.iterrows():
                campaign_id = str(row.get(url_campaign_id_col, '')).strip() if pd.notna(row.get(url_campaign_id_col)) else None
                ad_group = None
                account = None
                campaign_name = None
                
                # Get Ad Group
                for col in ['Ad group', 'Ad group name', 'Adgroup']:
                    if col in row and pd.notna(row[col]):
                        ad_group = str(row[col]).strip()
                        break
                
                # Get Account
                for col in ['Account', 'Account name']:
                    if col in row and pd.notna(row[col]):
                        account = str(row[col]).strip()
                        break
                
                # Get Campaign Name
                for col in ['Campaign', 'Campaign name']:
                    if col in row and pd.notna(row[col]):
                        campaign_name = str(row[col]).strip()
                        break
                
                if ad_group and campaign_id and campaign_id != 'nan':
                    # Normalize Campaign ID
                    if '.' in campaign_id:
                        campaign_id = campaign_id.split('.')[0]
                    
                    # Use composite key for precise matching
                    key = f"{account}|{ad_group}" if account else ad_group
                    ad_group_to_campaign_id[key] = {
                        'campaign_id': campaign_id,
                        'campaign_name': campaign_name
                    }
            
            # Match ads data using Campaign ID from URL report
            def get_conversions_via_campaign_id(row):
                ad_group = str(row.get('Ad group', '')).strip() if pd.notna(row.get('Ad group')) else None
                account = str(row.get('Account', '')).strip() if pd.notna(row.get('Account')) else None
                
                if not ad_group:
                    return None
                
                # Try composite key first (Account + Ad group)
                key = f"{account}|{ad_group}" if account else ad_group
                mapping_data = ad_group_to_campaign_id.get(key)
                
                if not mapping_data:
                    # Try just ad group
                    mapping_data = ad_group_to_campaign_id.get(ad_group)
                
                if not mapping_data:
                    return None
                
                campaign_id = mapping_data['campaign_id']
                campaign_name = mapping_data.get('campaign_name', '')
                
                # Detect office from campaign name (always returns Legacy or MOA)
                office = detect_office(campaign_name)
                
                # Use office-specific match if stats have office column
                if has_office:
                    lookup_key = (campaign_id, office)
                    if lookup_key in campaign_map:
                        return campaign_map[lookup_key]['conversions']
                else:
                    # No office in stats - direct match
                    if campaign_id in campaign_map:
                        return campaign_map[campaign_id]['conversions']
                
                return None
            
            _via_id = ads_df.apply(get_conversions_via_campaign_id, axis=1).astype('float64')
            mask = ads_df['Campaign Conversions'].isna()
            ads_df.loc[mask, 'Campaign Conversions'] = _via_id[mask]

            # Store debug info
            st.session_state.debug_info['url_campaign_id_matching'] = {
                'url_campaign_id_col': url_campaign_id_col,
                'mappings_created': len(ad_group_to_campaign_id),
                'sample_mappings': list(ad_group_to_campaign_id.items())[:5]
            }
        
        # FALLBACK: Look for Final URL column and extract tracking IDs (less reliable)
        final_url_col = None
        for col in url_report_df.columns:
            col_lower = str(col).lower()
            if any(term in col_lower for term in ['final', 'url', 'landing', 'destination']):
                final_url_col = col
                break
        
        st.session_state.debug_info['final_url_col'] = final_url_col
        
        # If URL report has Final URL column, extract tracking Campaign IDs
        if final_url_col:
            # Sample URLs for debug
            sample_urls = url_report_df[final_url_col].dropna().head(5).tolist()
            st.session_state.debug_info['sample_urls'] = sample_urls
            
            # Create mapping: (Account + Ad Group) -> (Tracking Campaign ID, Campaign Name)
            url_map = {}
            extracted_count = 0
            
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
                            extracted_count += 1
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
            
            # Store extraction results
            st.session_state.debug_info['extracted_count'] = extracted_count
            st.session_state.debug_info['url_map_count'] = len(url_map)
            st.session_state.debug_info['url_map_sample'] = list(url_map.items())[:5]
            
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
                
                # Extract campaign prefix (MLGDF172-001R -> MLGDF172)
                campaign_prefix = tracking_id.split('-')[0] if '-' in tracking_id else tracking_id
                
                # Extract domain from Final URL for this ad group
                # We need to go back to url_report_df to get the Final URL
                domain = None
                for _, url_row in url_report_df.iterrows():
                    url_ad_group = None
                    for col in ['Ad group', 'Ad group name', 'Adgroup']:
                        if col in url_row and pd.notna(url_row[col]):
                            url_ad_group = str(url_row[col]).strip()
                            break
                    
                    if url_ad_group == ad_group:
                        # Found matching ad group - extract domain from Final URL
                        final_url = str(url_row.get(final_url_col, '')).strip() if pd.notna(url_row.get(final_url_col)) else None
                        if final_url and final_url != 'nan':
                            match = re.search(r'https?://(?:www\.)?([^/?]+)', final_url)
                            if match:
                                domain = match.group(1).lower()
                                break
                
                # Detect office from campaign name (always returns Legacy or MOA)
                office = detect_office(campaign_name)
                
                # Match using Domain + Campaign Prefix + Office
                matched_conversion = None
                
                if has_domain and has_office and domain:
                    lookup_key = (domain, campaign_prefix, office)
                    if lookup_key in campaign_map:
                        matched_conversion = campaign_map[lookup_key]['conversions']
                elif has_domain and domain:
                    lookup_key = (domain, campaign_prefix)
                    if lookup_key in campaign_map:
                        matched_conversion = campaign_map[lookup_key]['conversions']
                elif has_office:
                    lookup_key = (campaign_prefix, office)
                    if lookup_key in campaign_map:
                        matched_conversion = campaign_map[lookup_key]['conversions']
                else:
                    if campaign_prefix in campaign_map:
                        matched_conversion = campaign_map[campaign_prefix]['conversions']
                
                return matched_conversion
            
            _via_url = ads_df.apply(get_conversions_via_url_report, axis=1).astype('float64')
            mask = ads_df['Campaign Conversions'].isna()
            ads_df.loc[mask, 'Campaign Conversions'] = _via_url[mask]
    
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
        
        _via_direct = ads_df.apply(get_conversions_by_direct_id, axis=1).astype('float64')
        mask = ads_df['Campaign Conversions'].isna()
        ads_df.loc[mask, 'Campaign Conversions'] = _via_direct[mask]
    
    # Strategy 3: Name-based matching (fallback)
    # Build campaign_name_map from stats: campaign name → conversions
    campaign_name_map = {}
    if 'Campaign' in campaign_stats_df.columns:
        for _, row in campaign_stats_df.iterrows():
            cname = str(row['Campaign']).strip() if pd.notna(row.get('Campaign')) else None
            if not cname or cname == 'nan':
                continue
            convs = row.get('Total Conversions', 0)
            if has_office:
                office_val = row.get('Office', 'Legacy')
                key = (cname, office_val)
                if key not in campaign_name_map:
                    campaign_name_map[key] = {'conversions': convs}
                else:
                    campaign_name_map[key]['conversions'] += convs
            else:
                if cname not in campaign_name_map:
                    campaign_name_map[cname] = {'conversions': convs}
                else:
                    campaign_name_map[cname]['conversions'] += convs

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
        _via_name = ads_df['Campaign'].apply(get_conversions_by_name).astype('float64')
        mask = ads_df['Campaign Conversions'].isna()
        ads_df.loc[mask, 'Campaign Conversions'] = _via_name[mask]
    
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
            except Exception:
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
                'Impression share lost to budget': 'Search lost IS (budget)',
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
                    'Search lost IS (rank)', 'Search lost IS (budget)', 'Search lost top IS (rank)', 'Conv. rate',
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
            'budget_constrained': pd.DataFrame(),
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
        # WITHOUT budget data: Use Search lost IS (budget) as a proxy
        # Only suggest bid increases when lost IS to BUDGET is low (< 10%),
        # meaning the account is NOT budget-constrained.
        has_budget_is = 'Search lost IS (budget)' in active_df.columns
        budget_filter = (active_df['Search lost IS (budget)'] < 0.10) if has_budget_is else True

        results['losing_auctions'] = active_df[
            budget_filter &
            (active_df['Search lost IS (rank)'] > thresholds['increase_lost_is_rank_min']) &
            (active_df['Search top IS'] < thresholds['target_top_is_min']) &
            (active_df['Search impr. share'] < 0.40) &
            (active_df['CTR'] > thresholds['poor_ctr_threshold']) &
            (active_df['Cost'] > 10)
        ].copy()

        if has_budget_is:
            results['losing_auctions']['recommendation'] = 'Increase bid 30-40%'
            results['losing_auctions']['reason'] = 'Not budget-constrained + low impression share + losing auctions to rank'
        else:
            results['losing_auctions']['recommendation'] = 'Increase bid 30-40% (verify budget has room)'
            results['losing_auctions']['reason'] = 'Low impression share + losing auctions to rank (no budget data to verify)'
        results['losing_auctions']['priority'] = 'High'

        # Flag budget-constrained ad groups that were excluded
        if has_budget_is:
            budget_blocked = active_df[
                (active_df['Search lost IS (budget)'] >= 0.10) &
                (active_df['Search lost IS (rank)'] > thresholds['increase_lost_is_rank_min']) &
                (active_df['Search top IS'] < thresholds['target_top_is_min'])
            ]
            if not budget_blocked.empty:
                results['budget_constrained'] = budget_blocked.copy()
                results['budget_constrained']['recommendation'] = 'Increase BUDGET first (not bids)'
                results['budget_constrained']['reason'] = f'Losing {budget_blocked["Search lost IS (budget)"].mean()*100:.0f}%+ impressions to budget — raising bids will waste spend'
                results['budget_constrained']['priority'] = 'High'
    
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



def process_ads_platform(platform_name, ads_df, custom_thresholds, selected_account='All Accounts', filter_to_stats_account=False, shared_budget_df=None, show_debug=False):
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
        if show_debug:
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
                except Exception:
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
        if show_debug:
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
    
        # Enrich with Product and UTM from mapping file if available
        if 'campaign_mapping' in st.session_state and st.session_state.campaign_mapping is not None:
            mapping_df = st.session_state.campaign_mapping
        
            # Merge on Campaign + Ad group
            ads_df = ads_df.merge(
                mapping_df[['Campaign', 'Ad group', 'Product', 'UTM']],
                on=['Campaign', 'Ad group'],
                how='left',
                suffixes=('', '_map')
            )
        
            # Show enrichment summary
            enriched_count = ads_df['Product'].notna().sum() if 'Product' in ads_df.columns else 0
            st.info(f"📊 Enriched {enriched_count}/{len(ads_df)} ad groups with Product/UTM data from mapping")
    
        # Show matching summary only if the column was added
        if 'Campaign Conversions' in ads_df.columns:
            matched_campaigns = ads_df['Campaign Conversions'].notna().sum()
            total_ad_groups = len(ads_df)

            # Always show a brief matching summary
            matched_total = ads_df['Campaign Conversions'].sum()
            st.caption(f"📊 Campaign Leads: matched {matched_campaigns}/{total_ad_groups} ad groups, total leads = {matched_total:,.0f}")
            # Show sample values for debugging
            sample = ads_df[ads_df['Campaign Conversions'].notna()][['Campaign', 'Campaign Conversions']].drop_duplicates('Campaign').head(5)
            if not sample.empty:
                st.caption("Sample: " + ", ".join(
                    f"{row['Campaign']} → {row['Campaign Conversions']:,.0f}"
                    for _, row in sample.iterrows()
                ))
        
            # Debug: Show matching details by office
            if show_debug:
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
    if show_debug:
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
    if filter_to_stats_account and show_debug:
        with st.expander("📊 Stats Account Matching", expanded=False):
            has_campaign_data = 'campaign_stats' in st.session_state and st.session_state.campaign_stats is not None
            has_domain = 'stats_agent_domain' in st.session_state and st.session_state.stats_agent_domain is not None
        
            st.caption(f"🔍 Stats account filter active. Has campaign data: {has_campaign_data}, Has domain: {has_domain}")
        
            if has_campaign_data:
                matched_account = None
            
                # Try to match using domain from URL report (if url_report_df exists)
                if 'url_report_df' in locals() and url_report_df is not None and not url_report_df.empty and 'Ad final URL' in url_report_df.columns and has_domain:
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
    budget_constrained = analysis_results.get('budget_constrained', pd.DataFrame())
    tab_names = [
        f"🚀 Major Opportunities ({len(analysis_results['major_opportunity'])})",
        f"🔺 Increase Bids ({len(analysis_results['losing_auctions'])})",
    ]
    if not budget_constrained.empty:
        tab_names.append(f"💰 Budget Constrained ({len(budget_constrained)})")
    tab_names.extend([
        f"✅ Maintain ({len(analysis_results['perfect_position'])})",
        f"🔻 Decrease Bids ({len(analysis_results['overpaying_position_1'])})",
        f"⚠️ Review ({len(analysis_results['poor_quality'])})",
        f"❌ No Conversions ({len(analysis_results['no_conversions'])})",
        f"🛑 Cleanup ({len(analysis_results['zero_impressions'])})"
    ])
    rec_tabs = st.tabs(tab_names)

    # Track tab index since budget_constrained tab shifts the rest
    _tab_idx = {"major": 0, "increase": 1}
    _next = 2
    if not budget_constrained.empty:
        _tab_idx["budget"] = _next; _next += 1
    _tab_idx["maintain"] = _next; _next += 1
    _tab_idx["decrease"] = _next; _next += 1
    _tab_idx["review"] = _next; _next += 1
    _tab_idx["no_conv"] = _next; _next += 1
    _tab_idx["cleanup"] = _next

    # Budget Constrained (only if data exists)
    if "budget" in _tab_idx:
        with rec_tabs[_tab_idx["budget"]]:
            st.markdown(f"""
            **{len(budget_constrained)} ad group(s)** are losing impressions primarily due to **budget limits**, not bid rank.
            Increasing bids on these would waste spend — **increase the daily/monthly budget first**.
            """)
            if not budget_constrained.empty:
                display_cols = ['Campaign', 'Ad group', 'Cost', 'Clicks', 'Impr.',
                                'Search impr. share', 'Search lost IS (budget)', 'Search lost IS (rank)']
                display_cols = [c for c in display_cols if c in budget_constrained.columns]
                display_df = budget_constrained[display_cols].copy()
                if 'Search lost IS (budget)' in display_df.columns:
                    display_df['Search lost IS (budget)'] = display_df['Search lost IS (budget)'].apply(
                        lambda x: format_ads_metric(x, 'percentage'))
                if 'Search lost IS (rank)' in display_df.columns:
                    display_df['Search lost IS (rank)'] = display_df['Search lost IS (rank)'].apply(
                        lambda x: format_ads_metric(x, 'percentage'))
                if 'Cost' in display_df.columns:
                    display_df['Cost'] = display_df['Cost'].apply(lambda x: format_ads_metric(x, 'currency'))
                display_df = display_df.rename(columns={
                    'Search lost IS (budget)': 'Lost to Budget',
                    'Search lost IS (rank)': 'Lost to Bids',
                })
                st.dataframe(display_df, width="stretch", hide_index=True)

    # Major Opportunities
    with rec_tabs[_tab_idx["major"]]:
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

            st.dataframe(display_df, width="stretch", hide_index=True)
        
            # Add metric explanations below table
            st.caption("💡 **CTR** = Click-through rate (engagement quality) | **Impr. Share** = % of available impressions you're getting | **Lost to Low Bids** = % of auctions you're losing because your bid is too low")

            # Download button
            csv = df_opp.to_csv(index=False)
            st.download_button(
                "⬇️ Download Major Opportunities",
                csv,
                "major_opportunities.csv",
                "text/csv",
                width="stretch"
            )
        else:
            st.info("No major opportunities found. All high-CTR ad groups are capturing good impression share.")

    # Increase Bids
    with rec_tabs[_tab_idx["increase"]]:
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

            st.dataframe(display_df, width="stretch", hide_index=True)
        
            st.caption("💡 **Lost to Low Bids** = % of auctions you're losing | **Top 3 Position** = % of time you appear in positions 1-3 | **Target: 60-80%**")

            csv = df_inc.to_csv(index=False)
            st.download_button(
                "⬇️ Download Increase Bid List",
                csv,
                "increase_bids.csv",
                "text/csv",
                width="stretch"
            )
        else:
            st.success("✅ No ad groups losing significant auctions to rank.")

    # Maintain
    with rec_tabs[_tab_idx["maintain"]]:
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

            st.dataframe(display_df, width="stretch", hide_index=True)
        
            st.caption("💡 **Perfect Balance:** Top 3 Position 60-80% + Position 1 only 20-40% = You're in the cost-efficient sweet spot!")
        else:
            st.warning("No ad groups currently in the perfect position 2-3 sweet spot.")

    # Decrease Bids
    with rec_tabs[_tab_idx["decrease"]]:
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

            st.dataframe(display_df, width="stretch", hide_index=True)
        
            st.caption("💡 **Overpaying:** Position 1 is expensive! Target: Show position 1 only 20-40% of the time, not 50%+")

            csv = df_dec.to_csv(index=False)
            st.download_button(
                "⬇️ Download Decrease Bid List",
                csv,
                "decrease_bids.csv",
                "text/csv",
                width="stretch"
            )
        else:
            st.success("✅ Position 1 strategy is working well - not overpaying!")

    # Review
    with rec_tabs[_tab_idx["review"]]:
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

            st.dataframe(display_df, width="stretch", hide_index=True)
        
            st.caption("💡 **Low CTR Warning:** CTR <1.5% usually means your ad or keywords don't match what people are searching for. Fix the ad first!")

            csv = df_review.to_csv(index=False)
            st.download_button(
                "⬇️ Download Review List",
                csv,
                "review_quality.csv",
                "text/csv",
                width="stretch"
            )
        else:
            st.success("✅ No major quality issues detected.")

    # No Conversions (only shows if campaign data available)
    with rec_tabs[_tab_idx["no_conv"]]:
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

            st.dataframe(display_df, width="stretch", hide_index=True)
        
            # Show total wasted spend
            total_waste = df_no_conv['Cost'].sum()
            st.error(f"💸 **Total Wasted Spend:** ${total_waste:,.2f} across {len(df_no_conv)} ad groups with zero conversions")

            csv = df_no_conv.to_csv(index=False)
            st.download_button(
                "⬇️ Download No Conversions List",
                csv,
                "no_conversions.csv",
                "text/csv",
                width="stretch"
            )
        else:
            if 'Campaign Conversions' in ads_df_filtered.columns:
                st.success("✅ All campaigns with significant spend are generating conversions!")
            else:
                st.info("ℹ️ No campaign conversion data available. Upload stats in Tab 1 to see this analysis.")

    # Cleanup
    with rec_tabs[_tab_idx["cleanup"]]:
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

            st.dataframe(df_cleanup[available_cols], width="stretch", hide_index=True)

            csv = df_cleanup.to_csv(index=False)
            st.download_button(
                "⬇️ Download Zero Impression List (for bulk pausing)",
                csv,
                "zero_impressions_cleanup.csv",
                "text/csv",
                width="stretch"
            )
        else:
            st.success("✅ No zero-impression ad groups to clean up.")

    # ---- Tab 1 Debug Section ----
    if 'debug_info' in st.session_state and st.session_state.debug_info:
        debug = st.session_state.debug_info
        st.markdown("---")
        # ========== CONSOLIDATED DEBUG & STATUS TABLE ==========
        st.markdown("---")
        st.markdown("### 🔍 Debug & Status Report")
    
        # Build comprehensive single table with all debug data
        all_debug_data = []
    
        # Get debug dict
        debug = st.session_state.get('debug_info', {})
    
        # === PROCESSING STATUS ===
        if 'files_loaded' in st.session_state:
            all_debug_data.append(["Files Loaded", st.session_state.files_loaded, "✅"])
    
        if 'total_rows' in st.session_state:
            all_debug_data.append(["Total Rows", st.session_state.total_rows, "✅"])
    
        if 'agency_distribution' in st.session_state:
            for agency, count in st.session_state.agency_distribution.items():
                all_debug_data.append([f"{agency} Rows", count, "✅"])
    
        # === CAMPAIGN PROCESSING ===
        if 'tab1_campaign_col_detected' in debug:
            all_debug_data.append(["Campaign Column Detected", debug['tab1_campaign_col_detected'], "✅"])
    
        if 'tab1_campaigns_processed' in debug:
            all_debug_data.append(["Campaigns Processed", debug['tab1_campaigns_processed'], "✅"])
    
        if 'tab1_domain_detected' in debug and debug['tab1_domain_detected']:
            all_debug_data.append(["Domain Detected", debug['tab1_domain_detected'], "✅"])
    
        # === PRODUCT ENRICHMENT ===
        if 'product_enrichment_count' in st.session_state:
            enriched = st.session_state.product_enrichment_count
            total = st.session_state.product_enrichment_total
            pct = (100 * enriched / total) if total > 0 else 0
            status = "✅" if enriched > 0 else "⚠️"
            all_debug_data.append(["Product Enrichment", f"{enriched}/{total} ({pct:.1f}%)", status])
    
        if 'product_matching_debug' in st.session_state and st.session_state.product_matching_debug:
            matching_df = pd.DataFrame(st.session_state.product_matching_debug)
            matched_count = matching_df[matching_df['Matched'] == 'YES'].shape[0]
            total_count = matching_df.shape[0]
            match_rate = (100 * matched_count / total_count) if total_count > 0 else 0
            status = "✅" if matched_count > 0 else "⚠️"
            all_debug_data.append(["Product Match Rate", f"{matched_count}/{total_count} ({match_rate:.1f}%)", status])
    
        # === TAB 2 DATA ===
        if 'campaign_stats_count' in st.session_state:
            all_debug_data.append(["Campaign Stats for Tab 2", st.session_state.campaign_stats_count, "✅"])
    
        # Display single consolidated table
        if all_debug_data:
            consolidated_df = pd.DataFrame(all_debug_data, columns=["Metric", "Value", "Status"])
            st.dataframe(consolidated_df, hide_index=True, width="stretch")
    
        # Product Matching Details Table (if available)
        if 'product_matching_debug' in st.session_state and st.session_state.product_matching_debug:
            st.markdown("**Product Matching Details:**")
            matching_detail_df = pd.DataFrame(st.session_state.product_matching_debug)
            st.dataframe(matching_detail_df, hide_index=True, width="stretch")
    
        # Sample Campaign IDs
        if 'tab1_sample_campaigns' in debug and debug['tab1_sample_campaigns']:
            sample_text = ", ".join(str(c) for c in debug['tab1_sample_campaigns'][:10])
            st.markdown(f"**Sample Campaign IDs:** `{sample_text}`")
    
        # Build text export
        debug_text = "=== TAB 1 DEBUG & STATUS REPORT ===\n\n"
        if all_debug_data:
            for row in all_debug_data:
                debug_text += f"{row[0]}: {row[1]} {row[2]}\n"
            debug_text += "\n"
    
        if 'product_matching_debug' in st.session_state and st.session_state.product_matching_debug:
            debug_text += "PRODUCT MATCHING DETAILS:\n"
            for idx, row in matching_detail_df.iterrows():
                debug_text += f"  Campaign ID: {row['Campaign ID']}\n"
                debug_text += f"  Pattern: {row['Pattern']}\n"
                debug_text += f"  Product: {row.get('Product', 'N/A')}\n"
                debug_text += f"  Matched: {row['Matched']}\n\n"
    
        if 'tab1_sample_campaigns' in debug and debug['tab1_sample_campaigns']:
            debug_text += f"Sample Campaign IDs: {sample_text}\n"
    
        # Download and copy buttons
        st.markdown("---")
        col1, col2 = st.columns(2)
    
        with col1:
            st.download_button(
                label="📥 Download Tab 1 Debug Report",
                data=debug_text,
                file_name="tab1_debug_report.txt",
                mime="text/plain",
                width="stretch"
            )
    
        with col2:
            if st.button("📋 Copy to Clipboard", key="copy_tab1_debug", width="stretch"):
                st.code(debug_text, language=None)



