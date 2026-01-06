import streamlit as st
import pandas as pd
import re

# ==================================================
# PAGE SETUP
# ==================================================
st.set_page_config(page_title="Fuel Audit System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection System")

st.markdown("""
Upload files and click **Analyze**  
You will receive a **multi-sheet Excel audit report**
""")

# ==================================================
# HELPER FUNCTIONS
# ==================================================

def normalize(text):
    return (
        str(text)
        .lower()
        .replace("\u00a0", " ")
        .replace("\n", " ")
        .strip()
    )

def extract_indent(value):
    if pd.isna(value):
        return None
    m = re.search(r"(\d+)", str(value))
    return f"IND-{m.group(1)}" if m else None

# ==================================================
# FILE UPLOAD
# ==================================================

st.sidebar.header("📂 Upload Files")

indent_file = st.sidebar.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.sidebar.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.sidebar.file_uploader("Vehicle Master (CSV)", type=["csv"])

analyze = st.sidebar.button("🚀 Analyze")

# ==================================================
# MAIN LOGIC
# ==================================================

if analyze:

    if not indent_file or not gps_file or not vehicle_master_file:
        st.error("❌ Please upload all required files")
        st.stop()

    # ==================================================
    # 1️⃣ INDENT REGISTER (CONFIRMED STRUCTURE)
    # ==================================================

    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [normalize(c) for c in indent_df.columns]

    st.subheader("Indent Columns Detected")
    st.write(indent_df.columns.tolist())

    BASE_DOC_COL = "base link doc  number"
    INDENT_DATE_COL = "requsted date"  # ERP typo
    VEHICLE_COL = "name"

    missing_cols = [c for c in [BASE_DOC_COL, INDENT_DATE_COL, VEHICLE_COL] if c not in indent_df.columns]
    if missing_cols:
        st.error(f"❌ Missing columns in Indent file: {missing_cols}")
        st.stop()

    indent_df["indent_no"] = indent_df[BASE_DOC_COL].apply(extract_indent)
    indent_df["indent_date"] = pd.to_datetime(indent_df[INDENT_DATE_COL], errors="coerce")
    indent_df["vehicle"] = indent_df[VEHICLE_COL]

    indent_df = indent_df.dropna(subset=["indent_no"])

    # ==================================================
    # 2️⃣ GPS DISTANCE REPORT (FIXED HEADER)
    # ==================================================

    gps_df = pd.read_excel(gps_file, header=1)
    gps_df.columns = [normalize(c) for c in gps_df.columns]

    st.subheader("GPS Columns Detected")
    st.write(gps_df.columns.tolist())

    gps_vehicle_col = None
    gps_distance_col = None

    for col in gps_df.columns:
        if "vehicle" in col:
            gps_vehicle_col = col
        if "km" in col or "distance" in col:
            gps_distance_col = col

    if not gps_vehicle_col or not gps_distance_col:
        st.error("❌ Could not detect Vehicle or Distance column in GPS file")
        st.stop()

    gps_summary = (
        gps_df
        .groupby(gps_vehicle_col, as_index=False)[gps_distance_col]
        .sum()
    )
    gps_summary.columns = ["vehicle", "total_km"]

    # ==================================================
    # 3️⃣ VEHICLE MASTER
    # ==================================================

    vehicle_master = pd.read_csv(vehicle_master_file)
    vehicle_master.columns = [normalize(c) for c in vehicle_master.columns]
    vehicle_list = vehicle_master.iloc[:, 0].astype(str).tolist()

    # ==================================================
    # 4️⃣ ANALYSIS
    # ==================================================

    fraud_rows = []
    recon_rows = []

    indent_usage = indent_df["indent_no"].value_counts()

    for _, row in indent_df.iterrows():
        indent_no = row["indent_no"]
        vehicle = row["vehicle"]

        if indent_usage[indent_no] > 1:
            fraud_rows.append({
                "Indent Number": indent_no,
                "Vehicle": vehicle,
                "Fraud Reason": "Duplicate indent usage"
            })

        recon_rows.append({
            "Indent Number": indent_no,
            "Indent Date": row["indent_date"],
            "Vehicle": vehicle
        })

    fraud_df = pd.DataFrame(fraud_rows)
    recon_df = pd.DataFrame(recon_rows)

    # ==================================================
    # 5️⃣ EXPORT REPORT
    # ==================================================

    output_file = "Fuel_Audit_Report.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        fraud_df.to_excel(writer, sheet_name="FRAUD_REPORT", index=False)
        recon_df.to_excel(writer, sheet_name="INDENT_RECON", index=False)
        gps_summary.to_excel(writer, sheet_name="VEHICLE_MILEAGE", index=False)

    # ==================================================
    # 6️⃣ UI OUTPUT
    # ==================================================

    st.success("✅ Analysis completed successfully")

    col1, col2 = st.columns(2)
    col1.metric("🚨 Fraud Cases", len(fraud_df))
    col2.metric("🚗 Vehicles Analysed", gps_summary.shape[0])

    with open(output_file, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
