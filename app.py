import streamlit as st
import pandas as pd
import requests
import io
import re

# ==========================
#  CONFIGURATION – ADD KEY HERE
# ==========================
VISION_API_KEY = "AIzaSyBFp3PKErq-nTlPkbX0Yoprf9h1rTugISs"   # <-- DO NOT SHARE PUBLICLY

# ==========================
#  STREAMLIT UI
# ==========================
st.set_page_config(page_title="Fuel Audit – Full OCR System", layout="wide")
st.title("⛽ Fuel Audit & Fraud Detection – Final Version")

st.write("Upload Indent Register, GPS Report, Vehicle Master and Fuel Bill PDF")

indent_file = st.file_uploader("Indent Register (Excel)", type=["xlsx"])
gps_file = st.file_uploader("GPS Distance Report (Excel)", type=["xlsx"])
vehicle_master_file = st.file_uploader("Vehicle Master (Excel/CSV)", type=["xlsx", "csv"])
bill_pdf = st.file_uploader("Fuel Bill – Combined PDF", type=["pdf"])

run = st.button("🚀 Run Full Analysis")

# ==========================
#  GOOGLE OCR FUNCTION
# ==========================
def ocr_pdf(file_bytes):
    url = f"https://vision.googleapis.com/v1/files:annotate?key={VISION_API_KEY}"

    request_json = {
        "requests": [
            {
                "inputConfig": {
                    "mimeType": "application/pdf",
                    "content": file_bytes.decode("latin1")
                },
                "features": [
                    {"type": "DOCUMENT_TEXT_DETECTION"}
                ]
            }
        ]
    }

    response = requests.post(url, json=request_json)
    response.raise_for_status()
    return response.json()

# ==========================
#  INDENT NUMBER EXTRACTOR
# ==========================
def extract_indent(text):
    m = re.search(r"\b(30\d{2,4}|31\d{2,4})\b", text)
    return m.group(0) if m else None

# ==========================
#  PROCESS
# ==========================
if run:

    if not all([indent_file, gps_file, vehicle_master_file, bill_pdf]):
        st.error("Upload all 4 files before running.")
        st.stop()

    # ---------- Load core data ----------
    indent_df = pd.read_excel(indent_file, header=5)
    gps_df = pd.read_excel(gps_file)

    if vehicle_master_file.name.endswith(".csv"):
        vehicle_df = pd.read_csv(vehicle_master_file)
    else:
        vehicle_df = pd.read_excel(vehicle_master_file)

    # ---------- Normalize columns ----------
    indent_df.columns = [c.lower().strip() for c in indent_df.columns]
    gps_df.columns = [c.lower().strip() for c in gps_df.columns]
    vehicle_df.columns = [c.lower().strip() for c in vehicle_df.columns]

    # ---------- Mandatory mappings ----------
    base_col = "base link doc  number"
    veh_col = "vehicle no  name"
    qty_col = "quantity"

    if base_col not in indent_df.columns:
        st.error("Indent Register missing column: Base Link doc number")
        st.stop()

    indent_df["indent_no"] = indent_df[base_col].astype(str).str.extract(r"(\d+)")
    indent_df["vehicle"] = indent_df[veh_col]

    # ---------- GPS summary ----------
    gps_df.rename(columns={
        "vehicle no.": "vehicle",
        "distance travelled [km]": "km"
    }, inplace=True)

    km_summary = gps_df.groupby("vehicle", as_index=False)["km"].sum()

    # ---------- OCR ----------
    st.info("📑 Running OCR on Fuel Bill PDF… this may take 10–20 seconds")

    pdf_bytes = bill_pdf.read()
    ocr_result = ocr_pdf(io.BytesIO(pdf_bytes).getvalue())

    pages_text = ""
    for r in ocr_result.get("responses", []):
        pages_text += r.get("fullTextAnnotation", {}).get("text", "") + "\n"

    # ---------- Extract bills ----------
    rows = []
    for line in pages_text.splitlines():
        indent = extract_indent(line)
        if indent:
            rows.append({"raw": line, "indent_no": indent})

    bill_df = pd.DataFrame(rows).drop_duplicates(subset=["indent_no"])

    # ---------- Reconciliation ----------
    merged = pd.merge(
        bill_df,
        indent_df,
        on="indent_no",
        how="left",
        indicator=True
    )

    # ---------- Flags ----------
    merged["status"] = merged["_merge"].map({
        "both": "Matched",
        "left_only": "Bill without Indent ❌",
        "right_only": "Indent without Bill ⚠"
    })

    # Owner vehicle exceptions
    owner_vehicles = [
        "TN66AR6000",
        "PY05P0005",
        "TN02CD0100",
        "TN66AS6000"
    ]

    merged.loc[merged["vehicle"].isin(owner_vehicles), "status"] = "Owner Exception 🟡"

    # ---------- Output ----------
    st.success("✅ Analysis complete. Download full Excel below.")

    output_name = "Fuel_Audit_Final_Report.xlsx"
    with pd.ExcelWriter(output_name, engine="openpyxl") as writer:
        indent_df.to_excel(writer, sheet_name="Indent Register", index=False)
        bill_df.to_excel(writer, sheet_name="Bill OCR Extract", index=False)
        merged.to_excel(writer, sheet_name="Bill vs Indent Audit", index=False)
        km_summary.to_excel(writer, sheet_name="Vehicle Distance", index=False)

    with open(output_name, "rb") as f:
        st.download_button(
            "📥 Download Final Excel Report",
            f,
            file_name=output_name
        )
