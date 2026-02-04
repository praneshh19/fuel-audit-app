import streamlit as st
import pandas as pd
import requests
import base64
import re
import io
from pdf2image import convert_from_bytes


# ============================================
# 🔑 ADD YOUR GOOGLE VISION API KEY HERE
# ============================================
VISION_API_KEY = "AIzaSyBFp3PKErq-nTlPkbX0Yoprf9h1rTugISs"   # <-- only here


# ============================================
# GOOGLE OCR FUNCTION (MULTI-IMAGE SAFE)
# ============================================
def ocr_image(image_bytes):
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    url = f"https://vision.googleapis.com/v1/images:annotate?key={VISION_API_KEY}"

    payload = {
        "requests": [
            {
                "image": {"content": img_b64},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]
            }
        ]
    }

    response = requests.post(url, json=payload)

    # --------- IMPORTANT ----------
    # do NOT crash the app
    # Show the real Google error message to user
    # ------------------------------------------
    try:
        data = response.json()
    except Exception:
        st.error("❌ Google Vision returned non-JSON response")
        st.code(response.text)
        return ""

    if "error" in data:
        st.error("❌ Google Vision API Error")
        st.code(data["error"])
        return ""

    if (
        "responses" not in data
        or not data["responses"]
        or "fullTextAnnotation" not in data["responses"][0]
    ):
        return ""

    return data["responses"][0]["fullTextAnnotation"]["text"]


# ============================================
# SUPPORT FUNCTIONS
# ============================================
def extract_indent(text):
    m = re.search(r"\b(\d{3,6})\b", text)
    return m.group(1) if m else None


# ============================================
# STREAMLIT UI
# ============================================
st.set_page_config(page_title="Fuel Audit – Multi Image OCR", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection — Google OCR (Multiple Images)")

st.write("Upload Excel files and fuel bill **images** (JPG/PNG) or **scanned PDFs**.")


# ========== INPUT FILE UPLOADS ==========
indent_file = st.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.file_uploader("Vehicle Master (Excel/CSV)", type=["xlsx", "csv"])

bill_files = st.file_uploader(
    "Upload Fuel Bill Images or Scanned PDFs",
    type=["jpg", "jpeg", "png", "pdf"],
    accept_multiple_files=True
)

run = st.button("🚀 Run Audit")


# ============================================
# MAIN PROCESS
# ============================================
if run:

    if not all([indent_file, gps_file, vehicle_master_file, bill_files]):
        st.error("⚠ Please upload all required files.")
        st.stop()

    # ---------- STEP 1: Indent Register ----------
    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [str(c).strip() for c in indent_df.columns]

    st.subheader("Step 1 — Map Indent Register Columns")

    indent_col = st.selectbox("Select 'Base Link Doc Number' column", indent_df.columns)
    vehicle_col = st.selectbox("Select 'Vehicle Number' column", indent_df.columns)

    indent_df["indent_no"] = indent_df[indent_col].astype(str).str.extract(r"(\d+)")
    indent_df["vehicle"] = indent_df[vehicle_col].astype(str).str.replace(" ", "")


    # ---------- STEP 2: GPS ----------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = [str(c).strip() for c in gps_df.columns]

    st.subheader("Step 2 — Map GPS Columns")

    gps_vehicle_col = st.selectbox("Select GPS vehicle column", gps_df.columns)
    gps_distance_col = st.selectbox("Select GPS distance column", gps_df.columns)

    gps_df["vehicle"] = gps_df[gps_vehicle_col].astype(str).str.replace(" ", "")
    gps_df["km"] = pd.to_numeric(gps_df[gps_distance_col], errors="coerce")

    gps_summary = gps_df.groupby("vehicle", as_index=False)["km"].sum()


    # ---------- STEP 3: OCR MULTIPLE IMAGES/PDFs ----------
    st.subheader("Step 3 — Running OCR on fuel bill images/PDFs")

    bill_rows = []
    progress = st.progress(0)

    for i, uploaded_file in enumerate(bill_files):
        file_bytes = uploaded_file.read()
        file_name = uploaded_file.name.lower()

        # Check if it's a PDF file
        if file_name.endswith(".pdf"):
            # Convert PDF pages to images
            try:
                pages = convert_from_bytes(file_bytes, dpi=300)
                for page in pages:
                    # Convert PIL Image to bytes
                    img_buffer = io.BytesIO()
                    page.save(img_buffer, format="PNG")
                    img_bytes = img_buffer.getvalue()

                    text = ocr_image(img_bytes)

                    for line in text.splitlines():
                        indent = extract_indent(line)
                        if indent:
                            bill_rows.append({"text": line, "indent_no": indent})
            except Exception as e:
                st.error(f"❌ Error processing PDF '{uploaded_file.name}': {e}")
        else:
            # Process as image (JPG/PNG)
            text = ocr_image(file_bytes)

            for line in text.splitlines():
                indent = extract_indent(line)
                if indent:
                    bill_rows.append({"text": line, "indent_no": indent})

        progress.progress((i + 1) / len(bill_files))


    if bill_rows:
        bill_df = pd.DataFrame(bill_rows).drop_duplicates(subset=["indent_no"])
    else:
        bill_df = pd.DataFrame(columns=["text", "indent_no"])
        st.warning("⚠ No indent numbers extracted from uploaded files. Check if OCR is working correctly.")


    # ---------- STEP 4: RECON ----------
    st.subheader("Step 4 — Reconciliation & Fraud Detection")

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


    # ---------- Owner Exception ----------
    owner_vehicles = [
        "TN66AR6000",
        "PY05P0005",
        "TN02CD0100",
        "TN66AS6000"
    ]

    merged.loc[merged["vehicle"].isin(owner_vehicles), "status"] = "Owner Exception 🟡"


    # ---------- STEP 5: EXPORT ----------
    output_file = "Fuel_Audit_Multi_Image_GoogleOCR.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        indent_df.to_excel(writer, sheet_name="Indent Register", index=False)
        bill_df.to_excel(writer, sheet_name="Bill OCR Extract", index=False)
        merged.to_excel(writer, sheet_name="Bill vs Indent Audit", index=False)
        gps_summary.to_excel(writer, sheet_name="Vehicle Distance", index=False)

    st.success("✅ Audit completed successfully")

    with open(output_file, "rb") as f:
        st.download_button(
            "📥 Download Final Excel Report",
            f,
            file_name=output_file
        )
