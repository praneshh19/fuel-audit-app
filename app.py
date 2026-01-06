if analyze:
    if not indent_file:
        st.error("Upload Indent file")
        st.stop()

    raw = pd.read_excel(indent_file, header=None)

    st.subheader("🔍 RAW EXCEL PREVIEW (Top 15 rows)")
    st.dataframe(raw.head(15))

    # Try every row as header and show columns
    st.subheader("🧠 COLUMN INTERPRETATION TEST")

    for i in range(15):
        try:
            df_test = pd.read_excel(indent_file, header=i)
            cols = [str(c) for c in df_test.columns]
            st.write(f"Header row = {i}", cols)
        except Exception as e:
            st.write(f"Header row = {i} failed:", e)

    st.stop()
