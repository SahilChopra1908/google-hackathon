import streamlit as st
import requests
import time
from google.cloud import firestore

# ==== CONFIG ====
UPLOAD_API_URL = "https://pitch-deck-uploader-225085788448.us-central1.run.app"
REDIRECT_URL = "https://your-final-results-page.com"  # change to your target URL

# Firestore client
db = firestore.Client(
    project="molten-enigma-472206-i4",
    database="ai-evaluation-firestore"
)

st.set_page_config(page_title="AI Startup Evaluation Tool", page_icon="📊", layout="centered")

st.title("📊 AI Startup Evaluation Tool")
st.subheader("Upload Pitch Deck for Assessment")

# Input: Company name
company_name = st.text_input("Enter Company Name:")

# Input: File upload
uploaded_file = st.file_uploader("Upload Pitch Deck (PDF, PPT, PPTX)", type=["pdf", "ppt", "pptx"])

# Only show assessment button once a file is uploaded
if uploaded_file and company_name:
    files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
    data = {"company_name": company_name}

    if st.button("Run Startup Comprehensive Assessment"):
        try:
            # 1. Call upload function
            resp = requests.post(UPLOAD_API_URL, files=files, data=data)
            resp.raise_for_status()
            job_id = resp.json().get("job_id")

            if not job_id:
                st.error("❌ Failed to get Job ID from upload service.")
            else:
                st.info(f"Upload successful. Tracking Job ID: {job_id}")

                # 2. Poll Firestore for result
                with st.spinner("Processing pitch deck with Document AI..."):
                    while True:
                        doc = db.collection("jobs").document(job_id).get()

                        if not doc.exists:
                            time.sleep(5)
                            continue

                        job_data = doc.to_dict()
                        status = job_data.get("status")

                        if status == "completed":
                            st.success("✅ Assessment Completed")

                            # Optionally show result JSON
                            # st.json(job_data.get("result"))

                            # Redirect to external URL with job_id as query param
                            new_url = f"{REDIRECT_URL}?job_id={job_id}"
                            js = f"window.open('{new_url}', '_self')"  # _self = same tab
                            st.markdown(f"<script>{js}</script>", unsafe_allow_html=True)
                            break

                        elif status == "failed":
                            st.error("❌ Assessment failed")
                            break

                        else:
                            time.sleep(5)  # still processing, poll again

        except Exception as e:
            st.error(f"Error: {e}")

