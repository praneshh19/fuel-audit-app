import streamlit as st
import pandas as pd
import requests
import io
import re
import base64

# ==========================
#  ADD YOUR REGENERATED KEY HERE
# ==========================
VISION_API_KEY = "AIzaSyBFp3PKErq-nTlPkbX0Yoprf9h1rTugISs"   # <-- do not share this publicly


# ==========================
#  OCR FUNCTION FOR PDF
# ==========================
def ocr_pdf(pdf_bytes):
    url = f"https://vision.googleapis.com/v1/files:annotate?key={VISION_API_KEY}"

    encoded_content = base64.b64encode(pdf_bytes).decode("utf-8")

    request_json = {
        "requests": [
            {
                "inputConfig": {
                    "mimeType": "application/pdf",
                    "content": encoded_content
                },
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]
            }
        ]
    }

    response = requests.post(url, json=request_json)
    response.raise_for_status()
    return response.json()


# ==========================
#  INDENT NUMBER FROM TEXT
# ==========================
def extract_indent(text):
    m = re.search(r"\b(30\d{2,4}|31\d{2,4})\b", text)
    return m.group(0) if m else None


# ==========================
#  STREAMLIT UI
# ==========================
st.set_page_config(page_title="Fuel Audit – OCR System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection – OCR Enabled")

st.write("Upload all four files and click **Run Analysis**")

indent_file = st.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.file_uploader("Vehicle Master (Excel/CSV)", type=["xlsx", "csv"])
bill_pdf = st.file_uploader("Fuel Bill – Combined PDF", type=["pdf"])

run = st.button("🚀 Run Analysis")


# ==========================
#  MAIN PROCESSING
# ==========================
if run:

    if not all([indent_file, gps_file, vehicle_master_file, bill_pdf]):
        st.error("⚠ Please upload all 4 files first.")
        st.stop()

    # ------------ LOAD FILES ------------
    indent_df = pd.read_excel(indent_file, header=5)
    gps_df = pd.read_excel(gps_file)

    if vehicle_master_file.name.endswith(".csv"):
        vehicle_df = pd.read_csv(vehicle_master_file)
    else:
        vehicle_df = pd.read_excel(vehicle_master_file)

    # ------------ NORMALISE HEADERS ------------
    indent_df.columns = [c.strip() for c in indent_df.columns]
    gps_df.columns = [c.strip() for c in gps_df.columns]
    vehicle_df.columns = [c.strip() for c in vehicle_df.columns]

    # ------------ FIND IMPORTANT COLUMNS AUTOMATICALLY ------------
    # Base Link Doc number (Indent ref)
    base_col = [c for c in indent_df.columns if "base" in c.lower() and "doc" in c.lower()][0]

    # Vehicle number column
    veh_col = [c for c in indent_df.columns if "vehicle" in c.lower()][0]

    # ------------ CREATE CLEAN INDENT N0 ------------
    indent_df["indent_no"] = indent_df[base_col].astype(str).str.extract(r"(\d+)")
    indent_df["vehicle"] = indent_df[veh_col].astype(str).str.replace(" ", "")

    # ------------ GPS SUMMARY ------------
    km_col = [c for c in gps_df.columns if "distance" in c.lower()][0]
    gps_vehicle_col = [c for c in gps_df.columns if "vehicle" in c.lower()][0]

    gps_df["vehicle"] = gps_df[gps_vehicle_col].astype(str).str.replace(" ", "")
    gps_df["km"] = pd.to_numeric(gps_df[km_col], errors="coerce")

    km_summary = gps_df.groupby("vehicle", as_index=False)["km"].sum()

    # ------------ OCR BILL PROCESSING ------------
    st.info("📑 Running OCR on Fuel Bill PDF…")

    pdf_bytes = bill_pdf.read()
    ocr_result = ocr_pdf(pdf_bytes)

    full_text = ""
    for r in ocr_result.get("responses", []):
        full_text += r.get("fullTextAnnotation", {}).get("text", "")

    rows = []
    for line in full_text.splitlines():
        indent = extract_indent(line)
        if indent:
            rows.append({"text": line, "indent_no": indent})

    bill_df = pd.DataFrame(rows).drop_duplicates(subset=["indent_no"])

    # ------------ RECONCILIATION ------------
    merged = pd.merge(
        bill_df,
        indent_df,
        on="indent_no",
        how="left",
        indicator=True
    )

    merged["status"] = merged["_merge"].map({
        "both": "Matched",
        "left_only": "Bill Without Indent ❌",
        "right_only": "Indent Without Bill ⚠"
    })

    # Owner vehicle list
    owner_vehicles = [
        "TN66AR6000",
        "PY05P0005",
        "TN02CD0100",
        "TN66AS6000"
    ]

    merged.loc[merged["vehicle"].isin(owner_vehicles), "status"] = "Owner Exception 🟡"

    # ------------ SAVE REPORT ------------
    output_name = "Fuel_Audit_Final_Report.xlsx"

    with pd.ExcelWriter(output_name, engine="openpyxl") as writer:
        indent_df.to_excel(writer, sheet_name="Indent Register", index=False)
        bill_df.to_excel(writer, sheet_name="Bill OCR Extract", index=False)
        merged.to_excel(writer, sheet_name="Bill vs Indent Audit", index=False)
        km_summary.to_excel(writer, sheet_name="Vehicle Distance", index=False)

    st.success("✅ Analysis complete")

    with open(output_name, "rb") as f:
        st.download_button(
            "📥 Download Excel Report",
            f,
            file_name=output_name
        )
