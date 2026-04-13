"""
Utility functions for Lead Analyzer.
Column detection, string normalization, formatting helpers.
"""
import re
import pathlib

import pandas as pd
import numpy as np
import streamlit as st


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
    return df[cols]


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
    d = pretty_headers(df)
    
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



@st.cache_data(show_spinner="Loading file...")
def load_uploaded(file):
    """Load uploaded CSV or Excel file with caching."""
    suffix = pathlib.Path(file.name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file)
    elif suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
            return pd.read_excel(file, engine="openpyxl")
        except ImportError:
            st.error("Excel support requires the 'openpyxl' package.")
            return None
        except Exception as e:
            st.error(f"Could not read Excel file: {e}")
            return None
    else:
        st.error("Unsupported file type.")
        return None


def validate_upload(df, filename=""):
    """Validate an uploaded dataframe. Returns list of (level, message) tuples."""
    issues = []
    if df is None or df.empty:
        issues.append(("error", "File is empty or could not be read."))
        return issues

    # Check for expected columns
    expected = ["campaign", "quote", "phone", "sms", "landing"]
    col_names_lower = [c.lower() for c in df.columns]
    found_any = any(any(exp in cn for cn in col_names_lower) for exp in expected)
    if not found_any:
        issues.append(("warning", f"No expected columns found in {filename}. Expected columns containing: Campaign, Quote Starts, Phone Clicks, SMS Clicks, or Landing Page."))

    # Check for numeric data
    numeric_cols = df.select_dtypes(include=["number"]).columns
    if len(numeric_cols) == 0:
        issues.append(("warning", "No numeric columns detected. Metrics may not calculate correctly."))

    return issues


def extract_date_range_from_filename(filename):
    """Extract date range from filename pattern: campaign_report_YYYY-MM-DD_to_YYYY-MM-DD.
    Returns (start_date_str, end_date_str) or (None, None).
    """
    match = re.search(r'(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})', filename)
    if match:
        return match.group(1), match.group(2)
    return None, None
