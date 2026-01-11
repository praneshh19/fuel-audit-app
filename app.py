import streamlit as st
import pandas as pd
import requests
import base64
import re

# ============================================
# 🔑 ADD YOUR GOOGLE VISION API KEY HERE
# ============================================
VISION_API_KEY = "AIzaSyBFp3PKErq-nTlPkbX0Yoprf9h1rTugISs"   # <-- DO NOT SHARE PUBLICLY



# ============================================
# OCR FUNCTION FOR PDF
# ============================================
def ocr_pdf(pdf_bytes):
    encoded_content = base64.b64encode(pdf_bytes).decode("utf-8")

    url = f"https://vision.googleapis.com/v1/files:annotate?key={VISION_API_KEY}"

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



# ============================================
# INDENT NUMBER EXTRACTION FROM TEXT
# ============================================
def extract_indent(text):
    m = re.search(r"\b(\d{3,6})\b", text)
    return m.group(1) if m else None



# ============================================
# STREAMLIT APP UI
# ============================================
st.set_page_config(page_title="Fuel Audit OCR System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection – FINAL VERSION")

st.write("Upload all files and then select correct column names where requested.")



# ============================================
# FILE UPLOAD SECTION
# ============================================
indent_file = st.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.file_uploader("Vehicle Master (Excel/CSV)", type=["xlsx", "csv"])
bill_pdf = st.file_uploader("Fuel Bill – Combined PDF", type=["pdf"])

run = st.button("🚀 Run Audit")



# ============================================
# PROCESSING
# ============================================
if run:

    if not all([indent_file, gps_file, vehicle_master_file, bill_pdf]):
        st.error("⚠ Please upload all four files first.")
        st.stop()


    # ---------- READ INDENT REGISTER ----------
    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [str(c).strip() for c in indent_df.columns]

    st.subheader("Step 1 – Select Indent Register Columns")

    indent_col_option = st.selectbox("Select Base Link Doc Number Column", list(indent_df.columns))
    vehicle_col_option = st.selectbox("Select Vehicle Column", list(indent_df.columns))

    indent_df["indent_no"] = indent_df[indent_col_option].astype(str).str.extract(r"(\d+)")
    indent_df["vehicle"] = indent_df[vehicle_col_option].astype(str).str.replace(" ", "")



    # ---------- READ GPS ----------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = [str(c).strip() for c in gps_df.columns]

    st.subheader("Step 2 – Select GPS Columns")

    gps_vehicle_col = st.selectbox("Select GPS Vehicle Column", list(gps_df.columns))
    gps_distance_col = st.selectbox("Select GPS Distance Column", list(gps_df.columns))

    gps_df["vehicle"] = gps_df[gps_vehicle_col].astype(str).str.replace(" ", "")
    gps_df["km"] = pd.to_numeric(gps_df[gps_distance_col], errors="coerce")

    gps_summary = gps_df.groupby("vehicle", as_index=False)["km"].sum()



    # ---------- READ VEHICLE MASTER ----------
    if vehicle_master_file.name.endswith(".csv"):
        vehicle_df = pd.read_csv(vehicle_master_file)
    else:
        vehicle_df = pd.read_excel(vehicle_master_file)

    vehicle_df.columns = [str(c).strip() for c in vehicle_df.columns]
    vehicle_list = vehicle_df.iloc[:, 0].astype(str).str.replace(" ", "").tolist()



    # ---------- OCR PROCESSING ----------
    st.subheader("Step 3 – OCR on Fuel Bill PDF")

    st.info("📑 Running OCR… please wait 10–20 seconds")

    pdf_bytes = bill_pdf.read()
    ocr_result = ocr_pdf(pdf_bytes)

    text_full = ""
    for resp in ocr_result.get("responses", []):
        text_full += resp.get("fullTextAnnotation", {}).get("text", "")

    bill_rows = []

    for line in text_full.splitlines():
        indent = extract_indent(line)
        if indent:
            bill_rows.append({"text": line, "indent_no": indent})

    bill_df = pd.DataFrame(bill_rows).drop_duplicates(subset=["indent_no"])



    # ---------- RECONCILIATION ----------
    st.subheader("Step 4 – Reconciliation & Fraud Detection")

    merged = pd.merge(
        bill_df,
        indent_df,
        on="indent_no",
        how="left",
        indicator=True
    )

    merged["status"] = merged["_merge"].map({
        "both": "Matched",
        "left_only": "Bill without Indent ❌",
        "right_only": "Indent without Bill ⚠"
    })



    # ---------- OWNER VEHICLE EXCEPTIONS ----------
    owner_vehicles = [
        "TN66AR6000",
        "PY05P0005",
        "TN02CD0100",
        "TN66AS6000"
    ]

    merged.loc[merged["vehicle"].isin(owner_vehicles), "status"] = "Owner Exception 🟡"



    # ---------- EXPORT ----------
    st.success("✅ Audit Completed — Download Excel Below")

    output_file = "Fuel_Audit_Final.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        indent_df.to_excel(writer, sheet_name="Indent Register", index=False)
        bill_df.to_excel(writer, sheet_name="Bill OCR Extract", index=False)
        merged.to_excel(writer, sheet_name="Bill vs Indent Audit", index=False)
        gps_summary.to_excel(writer, sheet_name="Vehicle Distance", index=False)

    with open(output_file, "rb") as f:
        st.download_button(
            "📥 Download Final Fuel Audit Report",
            f,
            file_name=output_file
        )
