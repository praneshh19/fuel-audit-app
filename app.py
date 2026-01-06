import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Fuel Audit System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection System")

st.markdown("""
Upload your files and click **Analyze**  
You will receive a **multi-sheet Excel report** with:
- Fraud cases
- Control exceptions
- Indent reconciliation
- Vehicle mileage analysis
""")

# ------------------ Helper Functions ------------------

def extract_indent(base_doc):
    if pd.isna(base_doc):
        return None
    match = re.search(r":\s*(\d+)", str(base_doc))
    return f"IND-{match.group(1)}" if match else None

def fuzzy_vehicle(raw, master_list):
    if pd.isna(raw):
        return None, 0
    raw = str(raw).strip()
    if raw in master_list:
        return raw, 100
    return raw, 50  # low confidence but usable

# ------------------ File Upload ------------------

st.sidebar.header("📂 Upload Files")

indent_file = st.sidebar.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.sidebar.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.sidebar.file_uploader("Vehicle Master (CSV)", type=["csv"])

analyze = st.sidebar.button("🚀 Analyze")

# ------------------ Processing ------------------

if analyze:
    if not indent_file or not gps_file or not vehicle_master_file:
        st.error("⚠️ Please upload all required files.")
        st.stop()

    # ---------- LOAD INDENT FILE (FIX HEADER) ----------
    indent_df = pd.read_excel(indent_file, header=5)

    # ---------- FLATTEN MULTI-LEVEL HEADERS ----------
    if isinstance(indent_df.columns, pd.MultiIndex):
        indent_df.columns = [
            " ".join([str(x) for x in col if "unnamed" not in str(x).lower()]).strip()
            for col in indent_df.columns
        ]

    # ---------- CLEAN COLUMN NAMES ----------
    indent_df.columns = (
        indent_df.columns
        .astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace("\n", " ", regex=False)
        .str.strip()
        .str.lower()
    )

    st.write("✅ Detected Indent Columns:", indent_df.columns.tolist())

    # ---------- REQUIRED COLUMNS ----------
    base_doc_col = "base link doc number"
    indent_date_col = "requested date"
    vehicle_col = "vehicle no name"

    for col in [base_doc_col, indent_date_col, vehicle_col]:
        if col not in indent_df.columns:
            st.error(f"❌ Required column missing: {col}")
            st.stop()

    # ---------- PROCESS INDENT DATA ----------
    indent_df["indent no"] = indent_df[base_doc_col].apply(extract_indent)
    indent_df["indent date"] = pd.to_datetime(indent_df[indent_date_col], errors="coerce")
    indent_df["vehicle raw"] = indent_df[vehicle_col]

    indent_df = indent_df.dropna(subset=["indent no"])

    # ---------- LOAD GPS ----------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = gps_df.columns.str.strip()

    gps_summary = gps_df.groupby("Vehicle Number", as_index=False)["Distance"].sum()
    gps_summary.columns = ["vehicle", "total km"]

    # ---------- LOAD VEHICLE MASTER ----------
    vehicle_master = pd.read_csv(vehicle_master_file)
    vehicle_list = vehicle_master.iloc[:, 0].astype(str).tolist()

    # ---------- ANALYSIS ----------
    fraud = []
    exceptions = []
    recon = []

    indent_count = indent_df["indent no"].value_counts()

    for _, row in indent_df.iterrows():
        indent_no = row["indent no"]
        vehicle_raw = row["vehicle raw"]
        indent_date = row["indent date"]

        vehicle_final, score = fuzzy_vehicle(vehicle_raw, vehicle_list)

        # Duplicate indent fraud
        if indent_count[indent_no] > 1:
            fraud.append({
                "Indent Number": indent_no,
                "Vehicle": vehicle_raw,
                "Fraud Reason": "Duplicate indent usage"
            })

        # Vehicle mismatch
        if score < 90:
            exceptions.append({
                "Indent Number": indent_no,
                "Vehicle Entered": vehicle_raw,
                "Issue": "Vehicle number mismatch / needs review"
            })

        recon.append({
            "Indent Number": indent_no,
            "Indent Date": indent_date,
            "Vehicle (Final)": vehicle_final
        })

    fraud_df = pd.DataFrame(fraud)
    exception_df = pd.DataFrame(exceptions)
    recon_df = pd.DataFrame(recon)

    # ---------- MILEAGE ----------
    mileage_df = pd.merge(
        gps_summary,
        indent_df.groupby("vehicle raw", as_index=False).size(),
        left_on="vehicle",
        right_on="vehicle raw",
        how="left"
    ).rename(columns={"size": "fuel entries"}).drop(columns=["vehicle raw"])

    # ---------- EXPORT EXCEL ----------
    output_file = "Fuel_Audit_Report.xlsx"
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        fraud_df.to_excel(writer, sheet_name="FRAUD_REPORT", index=False)
        exception_df.to_excel(writer, sheet_name="CONTROL_EXCEPTIONS", index=False)
        recon_df.to_excel(writer, sheet_name="INDENT_RECON", index=False)
        mileage_df.to_excel(writer, sheet_name="VEHICLE_MILEAGE", index=False)

    # ---------- UI ----------
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
