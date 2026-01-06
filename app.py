import streamlit as st
import pandas as pd
import re

# ------------------ PAGE SETUP ------------------
st.set_page_config(page_title="Fuel Audit System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection System")

st.markdown("""
Upload your files and click **Analyze**

You will receive a **multi-sheet Excel report** containing:
- Fraud cases
- Control exceptions
- Indent reconciliation
- Vehicle mileage analysis
""")

# ------------------ HELPER FUNCTIONS ------------------

def extract_indent(base_doc):
    if pd.isna(base_doc):
        return None
    match = re.search(r":\s*(\d+)", str(base_doc))
    return f"IND-{match.group(1)}" if match else None

def clean_columns(df):
    df.columns = (
        df.columns
        .astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace("\n", " ", regex=False)
        .str.strip()
        .str.lower()
    )
    return df

def fuzzy_vehicle(raw, master_list):
    if pd.isna(raw):
        return None, 0
    raw = str(raw).strip()
    if raw in master_list:
        return raw, 100
    return raw, 50

# ------------------ FILE UPLOAD ------------------

st.sidebar.header("📂 Upload Files")

indent_file = st.sidebar.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.sidebar.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.sidebar.file_uploader("Vehicle Master (CSV)", type=["csv"])

analyze = st.sidebar.button("🚀 Analyze")

# ------------------ PROCESSING ------------------

if analyze:
    if not indent_file or not gps_file or not vehicle_master_file:
        st.error("⚠️ Please upload all required files.")
        st.stop()

    # -------- FIND HEADER ROW (BULLETPROOF) --------
    raw = pd.read_excel(indent_file, header=None)

    header_row = None
    for i in range(len(raw)):
        row_text = " ".join(raw.iloc[i].astype(str)).lower()
        if "base link" in row_text:
            header_row = i
            break

    if header_row is None:
        st.error("❌ Header row with 'Base Link doc number' not found")
        st.stop()

    # -------- READ WITH CORRECT HEADER --------
    indent_df = pd.read_excel(indent_file, header=header_row)

    # -------- CLEAN COLUMN NAMES --------
    indent_df = clean_columns(indent_df)

    st.write("✅ FINAL INDENT COLUMNS:", indent_df.columns.tolist())

    # -------- REQUIRED COLUMNS --------
    required = [
        "base link doc number",
        "vehicle no name",
        "created date"
    ]

    for col in required:
        if col not in indent_df.columns:
            st.error(f"❌ Required column missing: {col}")
            st.stop()

    # -------- PROCESS INDENT DATA --------
    indent_df["indent no"] = indent_df["base link doc number"].apply(extract_indent)
    indent_df["indent date"] = pd.to_datetime(indent_df["created date"], errors="coerce")
    indent_df["vehicle raw"] = indent_df["vehicle no name"]

    indent_df = indent_df.dropna(subset=["indent no"])

    # -------- GPS DATA --------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = gps_df.columns.str.strip()

    gps_summary = gps_df.groupby("Vehicle Number", as_index=False)["Distance"].sum()
    gps_summary.columns = ["vehicle", "total km"]

    # -------- VEHICLE MASTER --------
    vehicle_master = pd.read_csv(vehicle_master_file)
    vehicle_list = vehicle_master.iloc[:, 0].astype(str).tolist()

    # -------- ANALYSIS --------
    fraud = []
    exceptions = []
    recon = []

    indent_count = indent_df["indent no"].value_counts()

    for _, row in indent_df.iterrows():
        indent_no = row["indent no"]
        vehicle_raw = row["vehicle raw"]

        vehicle_final, score = fuzzy_vehicle(vehicle_raw, vehicle_list)

        if indent_count[indent_no] > 1:
            fraud.append({
                "Indent Number": indent_no,
                "Vehicle": vehicle_raw,
                "Fraud Reason": "Duplicate indent usage"
            })

        if score < 90:
            exceptions.append({
                "Indent Number": indent_no,
                "Vehicle Entered": vehicle_raw,
                "Issue": "Vehicle number mismatch"
            })

        recon.append({
            "Indent Number": indent_no,
            "Indent Date": row["indent date"],
            "Vehicle (Final)": vehicle_final
        })

    fraud_df = pd.DataFrame(fraud)
    exception_df = pd.DataFrame(exceptions)
    recon_df = pd.DataFrame(recon)

    # -------- MILEAGE --------
    mileage_df = pd.merge(
        gps_summary,
        indent_df.groupby("vehicle raw", as_index=False).size(),
        left_on="vehicle",
        right_on="vehicle raw",
        how="left"
    ).rename(columns={"size": "fuel entries"}).drop(columns=["vehicle raw"])

    # -------- EXPORT --------
    output_file = "Fuel_Audit_Report.xlsx"
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        fraud_df.to_excel(writer, sheet_name="FRAUD_REPORT", index=False)
        exception_df.to_excel(writer, sheet_name="CONTROL_EXCEPTIONS", index=False)
        recon_df.to_excel(writer, sheet_name="INDENT_RECON", index=False)
        mileage_df.to_excel(writer, sheet_name="VEHICLE_MILEAGE", index=False)

    st.success("✅ Analysis completed successfully")

    col1, col2 = st.columns(2)
    col1.metric("🚨 Fraud Cases", len(fraud_df))
    col2.metric("⚠️ Exceptions", len(exception_df))

    with open(output_file, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
