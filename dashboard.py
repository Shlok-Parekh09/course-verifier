import streamlit as st
import pandas as pd
import json
import os
import glob

# Set page config
st.set_page_config(page_title="Enterprise Verification Dashboard", layout="wide", page_icon="📊")

# --- DATA LOADERS ---
@st.cache_data
def load_legacy_data():
    file_path = "master_dashboard_results.json"
    if not os.path.exists(file_path):
        # Fallback to the temporary file if master doesn't exist yet
        file_path = "autonomous_verified_data.json"
        
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Error loading legacy data: {e}")
            return pd.DataFrame()
    else:
        return pd.DataFrame()

@st.cache_data
def load_fee_data():
    # Find the latest fee report in the fee_reports directory
    fee_reports_dir = "fee_reports"
    if os.path.exists(fee_reports_dir):
        excel_files = glob.glob(os.path.join(fee_reports_dir, "fee_verification_*.xlsx"))
        if excel_files:
            # Get the most recently created file
            latest_file = max(excel_files, key=os.path.getctime)
            try:
                return pd.read_excel(latest_file)
            except Exception as e:
                st.error(f"Error loading fee data: {e}")
                return pd.DataFrame()
    return pd.DataFrame()

# Load Data
df_legacy = load_legacy_data()
df_fee = load_fee_data()

# --- SIDEBAR ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Legacy Verification Results", "Fee Intelligence Layer"])
st.sidebar.markdown("---")
st.sidebar.info("Enterprise AI Verification System Dashboard\n\nBuild 3.0")

# --- PAGE: LEGACY VERIFICATION ---
if page == "Legacy Verification Results":
    st.title("🏛️ Legacy Course Verification Results")
    
    if df_legacy.empty:
        st.warning("No legacy verification data found (`autonomous_verified_data.json` missing or empty).")
    else:
        # Calculate Metrics
        total_courses = len(df_legacy)
        
        # 'web_status' in legacy JSON usually says "MATCH", "DISCREPANCY", or "FALSE" (meaning failed to verify)
        matches = df_legacy[df_legacy['web_status'].astype(str).str.upper() == 'MATCH'].shape[0]
        discrepancies = df_legacy[df_legacy['web_status'].astype(str).str.upper() == 'DISCREPANCY'].shape[0]
        unverified = total_courses - matches - discrepancies
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Courses Processed", total_courses)
        col2.metric("Perfect Matches", matches)
        col3.metric("Discrepancies Found", discrepancies)
        col4.metric("Unverified / Failed", unverified)
        
        st.markdown("---")
        
        # Discrepancy Highlight Section
        st.subheader("⚠️ Discrepancy Explorer")
        st.markdown("These courses have mismatched data between the PDF and the Web.")
        
        df_discrepancies = df_legacy[df_legacy['web_status'].astype(str).str.upper() == 'DISCREPANCY']
        
        if not df_discrepancies.empty:
            # Select relevant columns for discrepancy view
            cols_to_show = ['name', 'uni', 'cost', 'web_cost', 'duration', 'reason']
            # Only select columns that actually exist
            existing_cols = [c for c in cols_to_show if c in df_discrepancies.columns]
            st.dataframe(df_discrepancies[existing_cols], use_container_width=True)
        else:
            st.success("No discrepancies found! All verified courses match perfectly.")
            
        st.markdown("---")
        
        # Full Data Table
        st.subheader("📚 Full Course Verification Log")
        search_query = st.text_input("Search by University or Course Name:", "")
        
        filtered_df = df_legacy.copy()
        if search_query:
            search_query = search_query.lower()
            filtered_df = filtered_df[
                filtered_df['name'].str.lower().str.contains(search_query, na=False) |
                filtered_df['uni'].str.lower().str.contains(search_query, na=False)
            ]
            
        st.dataframe(filtered_df, use_container_width=True)

# --- PAGE: FEE INTELLIGENCE ---
elif page == "Fee Intelligence Layer":
    st.title("💰 Fee Intelligence Layer Results")
    
    if df_fee.empty:
        st.warning("No fee extraction data found. Please ensure `fee_reports/fee_verification_*.xlsx` exists.")
    else:
        total_processed = len(df_fee)
        
        high_conf = df_fee[df_fee['Confidence'] == 'HIGH'].shape[0] if 'Confidence' in df_fee.columns else 0
        med_conf = df_fee[df_fee['Confidence'] == 'MEDIUM'].shape[0] if 'Confidence' in df_fee.columns else 0
        low_conf = df_fee[df_fee['Confidence'] == 'LOW'].shape[0] if 'Confidence' in df_fee.columns else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total URLs Processed", total_processed)
        col2.metric("High Confidence", high_conf)
        col3.metric("Medium Confidence", med_conf)
        col4.metric("Low Confidence / Failed", low_conf)
        
        st.markdown("---")
        st.subheader("🔍 Extraction Audit Table")
        
        st.dataframe(df_fee, use_container_width=True)
