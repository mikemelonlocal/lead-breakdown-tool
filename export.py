"""
Export functions for Lead Analyzer.
Excel, HTML, CSV generation.
"""
import io
import re
from datetime import datetime

import pandas as pd
import numpy as np

from utils import (
    safe_sheet_name, drop_effective_cost_basis, pretty_headers,
    is_currency_col, is_percent_col
)

try:
    import openpyxl
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


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


_MELON_MAX_DEVICE_CODES = {"AM", "AT", "AD", "HM", "HT", "HD"}


