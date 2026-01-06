import streamlit as st
import pandas as pd
import re

# ==================================================
# PAGE SETUP
# ==================================================
st.set_page_config(page_title="Fuel Audit System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection System")

st.markdown("""
Phase-2 Enabled:
✔ Vehicle Normalisation  
✔ Fuel Quantity Aggregation  
✔ Mileage Analysis (KM / Litre)
""")

# ==================================================
# HELPER FUNCTIONS
# ==================================================

def normalize(text):
    return (
        str(text)
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("\u00a0", "")
        .strip()
    )

def clean_col(text):
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
    # 1️⃣ INDENT REGISTER
    # ==================================================

    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [clean_col(c) for c in indent_df.columns]

    BASE_DOC_COL = "base link doc  number"
    INDENT_DATE_COL = "requsted date"
    VEHICLE_COL = "name"
    QTY_COL = "quantity"

    for col in [BASE_DOC_COL, INDENT_DATE_COL, VEHICLE_COL, QTY_COL]:
        if col not in indent_df.columns:
            st.error(f"❌ Missing column in Indent file: {col}")
            st.stop()

    indent_df["indent_no"] = indent_df[BASE_DOC_COL].apply(extract_indent)
    indent_df["indent_date"] = pd.to_datetime(indent_df[INDENT_DATE_COL], errors="coerce")
    indent_df["vehicle_raw"] = indent_df[VEHICLE_COL]
    indent_df["vehicle_norm"] = indent_df["vehicle_raw"].apply(normalize)
    indent_df["fuel_qty"] = pd.to_numeric(indent_df[QTY_COL], errors="coerce")

    indent_df = indent_df.dropna(subset=["indent_no"])

    # ==================================================
    # 2️⃣ GPS DATA
    # ==================================================

    gps_df = pd.read_excel(gps_file, header=1)
    gps_df.columns = [clean_col(c) for c in gps_df.columns]

    gps_vehicle_col = None
    gps_km_col = None

    for col in gps_df.columns:
        if "vehicle" in col:
            gps_vehicle_col = col
        if "km" in col or "distance" in col:
            gps_km_col = col

    if not gps_vehicle_col or not gps_km_col:
        st.error("❌ GPS vehicle or distance column not found")
        st.stop()

    gps_df["vehicle_norm"] = gps_df[gps_vehicle_col].apply(normalize)
    gps_df["km"] = pd.to_numeric(gps_df[gps_km_col], errors="coerce")

    gps_summary = gps_df.groupby("vehicle_norm", as_index=False)["km"].sum()

    # ==================================================
    # 3️⃣ VEHICLE MASTER
    # ==================================================

    vm = pd.read_csv(vehicle_master_file)
    vm.columns = [clean_col(c) for c in vm.columns]
    vm["vehicle_norm"] = vm.iloc[:, 0].apply(normalize)

    # ==================================================
    # 4️⃣ FUEL SUMMARY
    # ==================================================

    fuel_summary = (
        indent_df
        .groupby("vehicle_norm", as_index=False)["fuel_qty"]
        .sum()
    )

    # ==================================================
    # 5️⃣ MILEAGE ANALYSIS
    # ==================================================

    mileage_df = pd.merge(
        gps_summary,
        fuel_summary,
        on="vehicle_norm",
        how="left"
    )

    mileage_df["mileage_km_per_litre"] = (
        mileage_df["km"] / mileage_df["fuel_qty"]
    )

    # ==================================================
    # 6️⃣ FRAUD (DUPLICATE INDENT)
    # ==================================================

    fraud_df = (
        indent_df["indent_no"]
        .value_counts()
        .reset_index()
    )
    fraud_df.columns = ["indent_no", "usage_count"]
    fraud_df = fraud_df[fraud_df["usage_count"] > 1]

    # ==================================================
    # 7️⃣ EXPORT
    # ==================================================

    output = "Fuel_Audit_Report.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        indent_df.to_excel(writer, "INDENT_RAW", index=False)
        fuel_summary.to_excel(writer, "VEHICLE_FUEL_SUMMARY", index=False)
        mileage_df.to_excel(writer, "MILEAGE_ANALYSIS", index=False)
        fraud_df.to_excel(writer, "FRAUD_DUPLICATE_INDENT", index=False)

    st.success("✅ Phase-2 Analysis Completed")

    with open(output, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
