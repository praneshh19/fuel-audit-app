import streamlit as st
import pandas as pd
import re

# ------------------ PAGE SETUP ------------------
st.set_page_config(page_title="Fuel Audit System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection System")

st.markdown("""
Upload files and click **Analyze**  
You will receive a **multi-sheet Excel audit report**
""")

# ------------------ HELPERS ------------------

def extract_indent(val):
    if pd.isna(val):
        return None
    m = re.search(r"(\d+)", str(val))
    return f"IND-{m.group(1)}" if m else None

def clean_columns(df):
    df.columns = (
        df.columns
        .astype(str)
        .str.lower()
        .str.replace("\u00a0", " ", regex=False)
        .str.replace("\n", " ", regex=False)
        .str.strip()
    )
    return df

# ------------------ FILE UPLOAD ------------------

st.sidebar.header("📂 Upload Files")

indent_file = st.sidebar.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.sidebar.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.sidebar.file_uploader("Vehicle Master (CSV)", type=["csv"])

analyze = st.sidebar.button("🚀 Analyze")

# ------------------ PROCESS ------------------

if analyze:

    if not indent_file or not gps_file or not vehicle_master_file:
        st.error("❌ Please upload all required files")
        st.stop()

    # -------- READ INDENT REGISTER (CONFIRMED HEADER) --------
    indent_df = pd.read_excel(indent_file, header=5)
    indent_df = clean_columns(indent_df)

    st.write("✅ Columns detected:", indent_df.columns.tolist())

    # -------- COLUMN MAPPING (CONFIRMED) --------
    base_doc_col = "base link doc  number"
    indent_date_col = "requsted date"   # ERP spelling
    vehicle_col = "name"

    for col in [base_doc_col, indent_date_col, vehicle_col]:
        if col not in indent_df.columns:
            st.error(f"❌ Required column missing: {col}")
            st.stop()

    # -------- PROCESS INDENT DATA --------
    indent_df["indent no"] = indent_df[base_doc_col].apply(extract_indent)
    indent_df["indent date"] = pd.to_datetime(indent_df[indent_date_col], errors="coerce")
    indent_df["vehicle raw"] = indent_df[vehicle_col]

    indent_df = indent_df.dropna(subset=["indent no"])

    # -------- GPS DATA --------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = gps_df.columns.str.strip()

    gps_summary = gps_df.groupby("Vehicle Number", as_index=False)["Distance"].sum()
    gps_summary.columns = ["vehicle", "total km"]

    # -------- VEHICLE MASTER --------
    vm = pd.read_csv(vehicle_master_file)
    vehicle_list = vm.iloc[:, 0].astype(str).tolist()

    # -------- ANALYSIS --------
    fraud, exceptions, recon = [], [], []

    indent_count = indent_df["indent no"].value_counts()

    for _, r in indent_df.iterrows():
        ind = r["indent no"]
        veh = r["vehicle raw"]

        # Duplicate indent fraud
        if indent_count[ind] > 1:
            fraud.append({
                "Indent Number": ind,
                "Vehicle": veh,
                "Reason": "Duplicate indent usage"
            })

        recon.append({
            "Indent Number": ind,
            "Indent Date": r["indent date"],
            "Vehicle": veh
        })

    fraud_df = pd.DataFrame(fraud)
    recon_df = pd.DataFrame(recon)

    # -------- EXPORT --------
    output = "Fuel_Audit_Report.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as w:
        fraud_df.to_excel(w, "FRAUD_REPORT", index=False)
        recon_df.to_excel(w, "INDENT_RECON", index=False)

    st.success("✅ Analysis completed successfully")

    with open(output, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
