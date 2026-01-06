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

# ------------------ HELPER FUNCTIONS ------------------

def normalize(text):
    return (
        str(text)
        .lower()
        .replace("\u00a0", " ")
        .replace("\n", " ")
        .strip()
    )

def find_col_contains(df, keyword):
    keyword = keyword.lower()
    for col in df.columns:
        if keyword in normalize(col):
            return col
    return None

def extract_indent(val):
    if pd.isna(val):
        return None
    m = re.search(r"(\d+)", str(val))
    return f"IND-{m.group(1)}" if m else None

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

    # ==================================================
    # 1️⃣ INDENT REGISTER (CONFIRMED STRUCTURE)
    # ==================================================
    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [normalize(c) for c in indent_df.columns]

    st.write("✅ Indent Columns Detected:", indent_df.columns.tolist())

    base_doc_col = "base link doc  number"
    indent_date_col = "requsted date"   # ERP typo
    vehicle_col = "name"

    for col in [base_doc_col, indent_date_col, vehicle_col]:
        if col not in indent_df.columns:
            st.error(f"❌ Required column missing in Indent file: {col}")
            st.stop()

    indent_df["indent no"] = indent_df[base_doc_col].apply(extract_indent)
    indent_df["indent date"] = pd.to_datetime(indent_df[indent_date_col], errors="coerce")
    indent_df["vehicle"] = indent_df[vehicle_col]

    indent_df = indent_df.dropna(subset=["indent no"])

    # ==================================================
    # 2️⃣ GPS DATA (ROBUST COLUMN DETECTION)
    # ==================================================
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = [normalize(c) for c in gps_df.columns]

    st.write("📍 GPS Columns Detected:", gps_df.columns.tolist())

    gps_vehicle_col = find_col_contains(gps_df, "vehicle")
    gps_distance_col = find_col_contains(gps_df, "distance") or find_col_contains(gps_df, "km")

    if not gps_vehicle_col or not gps_distance_col:
        st.error("❌ Could not auto-detect Vehicle or Distance column in GPS file")
        st.stop()

    gps_summary = (
        gps_df
        .groupby(gps_vehicle_col, as_index=False)[gps_distance_col]
        .sum()
    )
    gps_summary.columns = ["vehicle", "total km"]

    # ==================================================
    # 3️⃣ VEHICLE MASTER
    # ==================================================
    vm = pd.read_csv(vehicle_master_file)
    vehicle_list = vm.iloc[:, 0].astype(str).tolist()

    # ==================================================
    # 4️⃣ ANALYSIS
    # ==================================================
    fraud = []
    recon = []

    indent_count = indent_df["indent no"].value_counts()

    for _, r in indent_df.iterrows():
        ind = r["indent no"]
        veh = r["vehicle"]

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

    # ==================================================
    # 5️⃣ EXPORT EXCEL
    # ==================================================
    output = "Fuel_Audit_Report.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as w:
        fraud_df.to_excel(w, sheet_name="FRAUD_REPORT", index=False)
        recon_df.to_excel(w, sheet_name="INDENT_RECON", index=False)
        gps_summary.to_excel(w, sheet_name="VEHICLE_MILEAGE", index=False)

    # ==================================================
    # 6️⃣ UI OUTPUT
    # ==================================================
    st.success("✅ Analysis completed successfully")

    col1, col2 = st.columns(2)
    col1.metric("🚨 Fraud Cases", len(fraud_df))
    col2.metric("📍 Vehicles Analysed", gps_summary.shape[0])

    with open(output, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
