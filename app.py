import streamlit as st
import pandas as pd

# ------------------ PAGE SETUP ------------------
st.set_page_config(page_title="Fuel Audit Debug", layout="wide")
st.title("🛠️ Fuel Audit – Excel Debug Mode")

st.markdown("""
This screen shows **exactly how Pandas reads your Excel file**.

👉 Upload ONLY the **Indent Register Excel**  
👉 Click **Analyze**  
👉 Copy the output and send it back
""")

# ------------------ FILE UPLOAD ------------------
st.sidebar.header("📂 Upload File")
indent_file = st.sidebar.file_uploader(
    "Indent Register (Excel)",
    type=["xlsx"]
)

analyze = st.sidebar.button("🚀 Analyze")

# ------------------ DEBUG LOGIC ------------------
if analyze:

    if not indent_file:
        st.error("❌ Please upload the Indent Register Excel file")
        st.stop()

    # Read raw Excel with NO headers
    raw_df = pd.read_excel(indent_file, header=None)

    st.subheader("🔍 RAW EXCEL (Top 20 Rows as Pandas Sees It)")
    st.dataframe(raw_df.head(20))

    st.divider()

    st.subheader("🧠 HEADER ROW TEST (0 to 20)")

    for i in range(21):
        try:
            test_df = pd.read_excel(indent_file, header=i)
            cols = [str(c) for c in test_df.columns]
            st.write(f"Header row = {i}")
            st.write(cols)
            st.write("—" * 50)
        except Exception as e:
            st.write(f"Header row = {i} FAILED:", e)

    st.divider()

    st.success("✅ Debug completed. Copy the output above and send it back.")
