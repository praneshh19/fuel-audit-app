import streamlit as st
import pandas as pd
import pytesseract
from pytesseract import image_to_string
from pdf2image import convert_from_bytes
from PIL import Image
import re
import io


# ============================
# INDENT NUMBER EXTRACTION
# ============================
def extract_indent(text):
    m = re.search(r"\b(\d{3,6})\b", text)
    return m.group(1) if m else None


# ============================
# OCR HANDLERS
# ============================
def ocr_image_bytes(img_bytes):
    img = Image.open(io.BytesIO(img_bytes))
    text = pytesseract.image_to_string(img)
    return text


def ocr_pdf_bytes(pdf_bytes):
    pages = convert_from_bytes(pdf_bytes, dpi=300)
    full_text = ""
    for p in pages:
        text = pytesseract.image_to_string(p)
        full_text += text + "\n"
    return full_text


# ============================
# STREAMLIT UI
# ============================
st.set_page_config(page_title="Fuel Audit – Offline OCR", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection – OFFLINE VERSION (NO API KEY)")

st.write("Upload all files and select the correct columns when prompted.")


# ============================
# FILE UPLOADS
# ============================
indent_file = st.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.file_uploader("Vehicle Master (Excel/CSV)", type=["xlsx", "csv"])

bill_file = st.file_uploader(
    "Fuel Bill (PDF or Image)",
    type=["pdf", "jpg", "jpeg", "png"]
)

run = st.button("🚀 Run Audit")


# ============================
# MAIN LOGIC
# ============================
if run:

    if not all([indent_file, gps_file, vehicle_master_file, bill_file]):
        st.error("⚠ Please upload all four files first.")
        st.stop()

    # ---------- READ INDENT REGISTER ----------
    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [str(c).strip() for c in indent_df.columns]

    st.subheader("Step 1 – Map Indent Register Columns")

    indent_col = st.selectbox("Select Base Link Doc Number Column", indent_df.columns)
    vehicle_col = st.selectbox("Select Vehicle Column", indent_df.columns)

    indent_df["indent_no"] = indent_df[indent_col].astype(str).str.extract(r"(\d+)")
    indent_df["vehicle"] = indent_df[vehicle_col].astype(str).str.replace(" ", "")

    # ---------- READ GPS ----------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = [str(c).strip() for c in gps_df.columns]

    st.subheader("Step 2 – Map GPS Columns")

    gps_vehicle_col = st.selectbox("Select GPS Vehicle Column", gps_df.columns)
    gps_distance_col = st.selectbox("Select GPS Distance Column", gps_df.columns)

    gps_df["vehicle"] = gps_df[gps_vehicle_col].astype(str).str.replace(" ", "")
    gps_df["km"] = pd.to_numeric(gps_df[gps_distance_col], errors="coerce")

    gps_summary = gps_df.groupby("vehicle", as_index=False)["km"].sum()

    # ---------- READ VEHICLE MASTER ----------
    if vehicle_master_file.name.endswith(".csv"):
        vehicle_df = pd.read_csv(vehicle_master_file)
    else:
        vehicle_df = pd.read_excel(vehicle_master_file)

    vehicle_df.columns = [str(c).strip() for c in vehicle_df.columns]

    # ---------- OCR ----------
    st.subheader("Step 3 – OCR Fuel Bills (Offline)")

    file_bytes = bill_file.read()
    file_type = bill_file.type.lower()

    st.info("🖨 Performing OCR… please wait")

    if "pdf" in file_type:
        text_full = ocr_pdf_bytes(file_bytes)
    else:
        text_full = ocr_image_bytes(file_bytes)

    # ---------- EXTRACT INDENTS FROM BILL ----------
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

    output_file = "Fuel_Audit_Offline_Final.xlsx"

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
