import streamlit as st
import pandas as pd
import requests
import base64
import re


# ============================
# 🔑 ADD YOUR GOOGLE API KEY HERE
# ============================
VISION_API_KEY = "AIzaSyBFp3PKErq-nTlPkbX0Yoprf9h1rTugISs"     # <--- put ONLY here


# ============================
# OCR IMAGE FUNCTION
# ============================
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
    response.raise_for_status()

    data = response.json()
    return data["responses"][0].get("fullTextAnnotation", {}).get("text", "")


# ============================
# Extract indent numbers
# ============================
def extract_indent(text):
    m = re.search(r"\b(\d{3,6})\b", text)
    return m.group(1) if m else None


# ============================
# STREAMLIT APP UI
# ============================
st.set_page_config(page_title="Fuel Audit – Multi Image OCR", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection – GOOGLE OCR (MULTIPLE IMAGES)")


st.markdown("""
Upload the following:

1️⃣ Indent Register (Excel)  
2️⃣ GPS Distance Report (Excel)  
3️⃣ Vehicle Master (Excel/CSV)  
4️⃣ **Multiple fuel bill IMAGES** (JPG/PNG)  
""")


# ========== FILE UPLOADS ==========
indent_file = st.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.file_uploader("Vehicle Master (Excel/CSV)", type=["xlsx", "csv"])

bill_images = st.file_uploader(
    "Upload Multiple Fuel Bill Images",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)

run = st.button("🚀 Run Audit")


# ============================
# MAIN PROCESS
# ============================
if run:

    if not all([indent_file, gps_file, vehicle_master_file, bill_images]):
        st.error("⚠ Please upload all required files.")
        st.stop()

    # ---------- Load Indent Register ----------
    indent_df = pd.read_excel(indent_file, header=5)
    indent_df.columns = [str(c).strip() for c in indent_df.columns]

    st.subheader("Step 1 – Map Indent Register Columns")

    indent_col = st.selectbox("Select 'Base Link Doc Number' column", indent_df.columns)
    vehicle_col = st.selectbox("Select 'Vehicle Number' column", indent_df.columns)

    indent_df["indent_no"] = indent_df[indent_col].astype(str).str.extract(r"(\d+)")
    indent_df["vehicle"] = indent_df[vehicle_col].astype(str).str.replace(" ", "")


    # ---------- Load GPS Data ----------
    gps_df = pd.read_excel(gps_file)
    gps_df.columns = [str(c).strip() for c in gps_df.columns]

    st.subheader("Step 2 – Map GPS Columns")

    gps_vehicle_col = st.selectbox("Select GPS vehicle column", gps_df.columns)
    gps_distance_col = st.selectbox("Select GPS distance column", gps_df.columns)

    gps_df["vehicle"] = gps_df[gps_vehicle_col].astype(str).str.replace(" ", "")
    gps_df["km"] = pd.to_numeric(gps_df[gps_distance_col], errors="coerce")

    gps_summary = gps_df.groupby("vehicle", as_index=False)["km"].sum()


    # ---------- OCR MULTIPLE IMAGES ----------
    st.subheader("Step 3 – OCR on uploaded fuel bill images")

    all_text = ""
    progress = st.progress(0)

    bill_rows = []

    for i, img in enumerate(bill_images):
        bytes_data = img.read()

        text = ocr_image(bytes_data)
        all_text += "\n" + text

        for line in text.splitlines():
            indent = extract_indent(line)
            if indent:
                bill_rows.append({"text": line, "indent_no": indent})

        progress.progress((i + 1) / len(bill_images))


    bill_df = pd.DataFrame(bill_rows).drop_duplicates(subset=["indent_no"])


    # ---------- Reconciliation ----------
    st.subheader("Step 4 – Bill vs Indent Reconciliation & Fraud Detection")

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


    # ---------- Owner Exceptions ----------
    owner_vehicles = [
        "TN66AR6000",
        "PY05P0005",
        "TN02CD0100",
        "TN66AS6000"
    ]

    merged.loc[merged["vehicle"].isin(owner_vehicles), "status"] = "Owner Exception 🟡"


    # ---------- Final Excel ----------
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
