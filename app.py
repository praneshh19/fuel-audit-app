import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Fuel Audit System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection System")

st.markdown("""
Upload files and click **Analyze**.
This version auto-adapts to ERP Excel formats.
""")

# ------------------ HELPERS ------------------

def extract_indent(val):
    if pd.isna(val):
        return None
    m = re.search(r"(\d+)", str(val))
    return f"IND-{m.group(1)}" if m else None

def normalize(s):
    return (
        str(s)
        .lower()
        .replace("\u00a0", " ")
        .replace("\n", " ")
        .strip()
    )

def find_col_contains(df, keyword):
    keyword = keyword.lower()
    for c in df.columns:
        if keyword in normalize(c):
            return c
    return None

def fuzzy_vehicle(raw, master):
    if pd.isna(raw):
        return None, 0
    raw = str(raw).strip()
    return (raw, 100) if raw in master else (raw, 50)

# ------------------ FILE UPLOAD ------------------

st.sidebar.header("📂 Upload Files")
indent_file = st.sidebar.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.sidebar.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.sidebar.file_uploader("Vehicle Master (CSV)", type=["csv"])
analyze = st.sidebar.button("🚀 Analyze")

# ------------------ PROCESS ------------------

if analyze:
    if not indent_file or not gps_file or not vehicle_master_file:
        st.error("Upload all files")
        st.stop()

    # -------- READ RAW EXCEL --------
    raw = pd.read_excel(indent_file, header=None)

    header_row = None
    for i in range(len(raw)):
        row_text = " ".join(raw.iloc[i].astype(str)).lower()
        if "base link" in row_text:
            header_row = i
            break

    if header_row is None:
        st.error("❌ Could not find any row containing 'Base Link'")
        st.stop()

    indent_df = pd.read_excel(indent_file, header=header_row)

    # -------- CLEAN COLUMNS --------
    indent_df.columns = [normalize(c) for c in indent_df.columns]

    st.write("🧠 Columns detected:", indent_df.columns.tolist())

    # -------- FLEXIBLE COLUMN DETECTION --------
    base_doc_col = find_col_contains(indent_df, "base link")
    vehicle_col = find_col_contains(indent_df, "vehicle")
    date_col = find_col_contains(indent_df, "date")

    if not base_doc_col or not vehicle_col or not date_col:
        st.error("❌ Could not auto-map required columns")
        st.stop()

    # -------- PROCESS INDENT DATA --------
    indent_df["indent no"] = indent_df[base_doc_col].apply(extract_indent)
    indent_df["indent date"] = pd.to_datetime(indent_df[date_col], errors="coerce")
    indent_df["vehicle raw"] = indent_df[vehicle_col]

    indent_df = indent_df.dropna(subset=["indent no"])

    # -------- GPS --------
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
        veh_raw = r["vehicle raw"]

        veh_final, score = fuzzy_vehicle(veh_raw, vehicle_list)

        if indent_count[ind] > 1:
            fraud.append({
                "Indent Number": ind,
                "Vehicle": veh_raw,
                "Reason": "Duplicate indent"
            })

        if score < 90:
            exceptions.append({
                "Indent Number": ind,
                "Vehicle Entered": veh_raw,
                "Issue": "Vehicle mismatch"
            })

        recon.append({
            "Indent Number": ind,
            "Indent Date": r["indent date"],
            "Vehicle (Final)": veh_final
        })

    fraud_df = pd.DataFrame(fraud)
    exc_df = pd.DataFrame(exceptions)
    recon_df = pd.DataFrame(recon)

    # -------- EXPORT --------
    output = "Fuel_Audit_Report.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as w:
        fraud_df.to_excel(w, "FRAUD_REPORT", index=False)
        exc_df.to_excel(w, "CONTROL_EXCEPTIONS", index=False)
        recon_df.to_excel(w, "INDENT_RECON", index=False)

    st.success("✅ Analysis completed")

    with open(output, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output
        )
