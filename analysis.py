"""
Core lead analysis engine for Lead Analyzer.
"""
import re

import pandas as pd
import numpy as np
import streamlit as st

from utils import get_col, detect_traffic_source_col, choose_source_column, _norm
from classification import (
    classify_platform, classify_product, classify_device,
    extract_utm_from_campaign_id, _CAMPAIGN_NUM_PRODUCT_MAP
)


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
    
    # Classify product: landing page first, then campaign number fallback.
    # classify_product checks landing page path keywords first, and only
    # falls back to campaign number when the page is generic (e.g. /quote).
    # If classify_product returns "Other" (no signal), use the mapping
    # enrichment value (if available) as a last resort.
    df["product"] = df.apply(
        lambda r: classify_product(r[col_campaign], r[col_landing], r["platform"]), axis=1
    )
    if 'Product' in df.columns:
        # Where classify_product couldn't determine product, use mapping
        mask = df["product"] == "Other"
        df.loc[mask, "product"] = df.loc[mask, "Product"].fillna("Other")
    
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

    # ---------- Landing Page vs UTM Product Mismatch Detection ----------
    product_mismatch = None
    if col_campaign and col_landing:
        def _lp_product(landing_page):
            """Classify product from landing page path only."""
            s_lp = (str(landing_page) or "").lower()
            path_part = s_lp.split('/', 3)[-1] if '/' in s_lp else ''
            if "renters" in path_part: return "Renters"
            if "condo" in path_part: return "Condo"
            if "homeowners" in path_part or "home-insurance" in path_part: return "Home"
            if "auto" in path_part or "car-insurance" in path_part: return "Auto"
            return None  # Ambiguous / generic page

        def _utm_product(campaign_id, platform):
            """Classify product from campaign number / UTM only."""
            raw = (str(campaign_id) or "").strip()
            h = re.match(r'^[0-9A-Fa-f]{32}(.+)$', raw)
            if h: raw = h.group(1)
            s_id = raw.upper()
            if platform == "Melon Max":
                if "QSA" in s_id: return "Auto"
                if "QSH" in s_id: return "Home"
            num_match = re.search(r'(?:MLSG|MLSB|MLG|MLB|[GB])[DM]F?(\d{3,4})', s_id)
            if not num_match: num_match = re.search(r'F(\d{3,4})', s_id)
            if num_match:
                return _CAMPAIGN_NUM_PRODUCT_MAP.get(num_match.group(1))
            return None

        df["_lp_product"] = df[col_landing].apply(_lp_product)
        df["_utm_product"] = df.apply(lambda r: _utm_product(r[col_campaign], r["platform"]), axis=1)

        # Mismatch = both are known (not None) and they disagree
        mismatch_mask = (
            df["_lp_product"].notna() &
            df["_utm_product"].notna() &
            (df["_lp_product"] != df["_utm_product"])
        )

        if mismatch_mask.any():
            # Clean landing page path for display
            df["_lp_path"] = df[col_landing].apply(
                lambda x: re.sub(r'^https?://[^/]*', '', str(x).strip()).rstrip('/') or '/'
            )

            group_cols_mm = ["platform", "_lp_path", "_lp_product", "_utm_product"]
            if "agency" in df.columns:
                group_cols_mm = ["agency"] + group_cols_mm

            product_mismatch = df[mismatch_mask].groupby(group_cols_mm, as_index=False).agg(
                quote_starts=(col_qs, "sum"),
                phone_clicks=(col_phone, "sum"),
                sms_clicks=(col_sms, "sum"),
                leads=("lead_opportunities", "sum")
            ).sort_values("leads", ascending=False).reset_index(drop=True)

            product_mismatch = product_mismatch.rename(columns={
                "_lp_path": "landing_page",
                "_lp_product": "lp_product",
                "_utm_product": "utm_product"
            })

            # Add TOTAL row
            totals_mm = {
                "platform": "",
                "landing_page": "",
                "lp_product": "",
                "utm_product": "TOTAL",
                "quote_starts": product_mismatch["quote_starts"].sum(),
                "phone_clicks": product_mismatch["phone_clicks"].sum(),
                "sms_clicks": product_mismatch["sms_clicks"].sum(),
                "leads": product_mismatch["leads"].sum()
            }
            if "agency" in product_mismatch.columns:
                totals_mm["agency"] = ""
            product_mismatch = pd.concat(
                [product_mismatch, pd.DataFrame([totals_mm])], ignore_index=True
            )

        # Clean up temp columns
        df.drop(columns=["_lp_product", "_utm_product", "_lp_path"], errors="ignore", inplace=True)

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

    # ---------- Aggregate Platform × Landing Page × UTM ----------
    platform_lp_utm = None
    if col_campaign and col_landing:
        df_lpu = df.copy()
        df_lpu["utm"] = df_lpu[col_campaign].apply(extract_utm_from_campaign_id)
        df_lpu["utm"] = df_lpu["utm"].replace("", "Unmatched")
        # Clean landing page to path only (strip protocol + domain)
        df_lpu["landing_page"] = df_lpu[col_landing].apply(
            lambda x: re.sub(r'^https?://[^/]*', '', str(x).strip()).rstrip('/') or '/'
        )

        group_cols_lpu = (
            ["device", "platform", "landing_page", "utm"]
            if add_device_column
            else ["platform", "landing_page", "utm"]
        )

        platform_lp_utm = df_lpu.groupby(group_cols_lpu, as_index=False).agg(
            quote_starts=(col_qs, "sum"),
            phone_clicks=(col_phone, "sum"),
            sms_clicks=(col_sms, "sum"),
            leads=("lead_opportunities", "sum")
        ).sort_values(
            ["platform", "leads", "landing_page", "utm"],
            ascending=[True, False, True, True]
        ).reset_index(drop=True)

        platform_lp_utm = platform_lp_utm[
            (platform_lp_utm["quote_starts"] > 0) |
            (platform_lp_utm["phone_clicks"] > 0) |
            (platform_lp_utm["sms_clicks"] > 0) |
            (platform_lp_utm["leads"] > 0)
        ].reset_index(drop=True)

        totals_lpu = {
            "platform": "",
            "landing_page": "",
            "utm": "TOTAL",
            "quote_starts": platform_lp_utm["quote_starts"].sum(),
            "phone_clicks": platform_lp_utm["phone_clicks"].sum(),
            "sms_clicks": platform_lp_utm["sms_clicks"].sum(),
            "leads": platform_lp_utm["leads"].sum()
        }
        if add_device_column:
            totals_lpu["device"] = ""
        platform_lp_utm = pd.concat(
            [platform_lp_utm, pd.DataFrame([totals_lpu])], ignore_index=True
        )

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
        "platform_lp_utm": platform_lp_utm,
        "product_mismatch": product_mismatch,
        "device_overview": device_overview,
        "device_platform": device_platform
    }

