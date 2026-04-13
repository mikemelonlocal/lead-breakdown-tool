"""
Reusable Streamlit UI components for Lead Analyzer.
"""
import pandas as pd
import numpy as np
import streamlit as st

from utils import (
    pretty_headers, is_currency_col, is_percent_col,
    fmt_currency_series, fmt_percent_series, _norm
)


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


