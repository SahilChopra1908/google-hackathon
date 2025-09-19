import streamlit as st
import requests
import time
from google.cloud import firestore

# ==== CONFIG ====
UPLOAD_API_URL = "https://pitch-deck-uploader-225085788448.us-central1.run.app"
REDIRECT_URL = "/complete-results"  # local path for results

# Firestore client
db = firestore.Client(
    project="molten-enigma-472206-i4",
    database="ai-evaluation-firestore"
)

st.set_page_config(page_title="AI Startup Evaluation Tool", page_icon="📊", layout="centered")

st.title("📊 AI Startup Evaluation Tool")
st.subheader("Upload Pitch Deck and Audio for Assessment")

# Session state to track if upload is in progress
if "uploading" not in st.session_state:
    st.session_state.uploading = False

# Input: Company name
company_name = st.text_input("Enter Company Name:")

# Input: Multiple pitch deck files
uploaded_files = st.file_uploader(
    "Upload Pitch Deck(s) (PDF, PPT, PPTX)",
    type=["pdf", "ppt", "pptx"],
    accept_multiple_files=True
)

# Input: Multiple audio files
uploaded_audio = st.file_uploader(
    "Upload Pitch Audio (MP3, WAV, M4A)",
    type=["mp3", "wav", "m4a"],
    accept_multiple_files=True
)

# Only show assessment button once files are uploaded
if (uploaded_files or uploaded_audio) and company_name:
    # Disable button if already uploading
    if st.button("Run Startup Comprehensive Assessment", disabled=st.session_state.uploading):
        st.session_state.uploading = True
        try:
            all_files = []
            if uploaded_files:
                all_files.extend(uploaded_files)
            if uploaded_audio:
                all_files.extend(uploaded_audio)

            for uploaded_file in all_files:
                # Detect MIME type dynamically
                if uploaded_file.name.lower().endswith(".pdf"):
                    mime_type = "application/pdf"
                elif uploaded_file.name.lower().endswith(".ppt"):
                    mime_type = "application/vnd.ms-powerpoint"
                elif uploaded_file.name.lower().endswith(".pptx"):
                    mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                elif uploaded_file.name.lower().endswith(".mp3"):
                    mime_type = "audio/mpeg"
                elif uploaded_file.name.lower().endswith(".wav"):
                    mime_type = "audio/wav"
                elif uploaded_file.name.lower().endswith(".m4a"):
                    mime_type = "audio/mp4"
                else:
                    mime_type = "application/octet-stream"

                files = {"file": (uploaded_file.name, uploaded_file, mime_type)}
                data = {"company_name": company_name}

                # 1. Call upload function
                resp = requests.post(UPLOAD_API_URL, files=files, data=data)
                resp.raise_for_status()
                job_id = resp.json().get("job_id")

                if not job_id:
                    st.error(f"❌ Failed to get Job ID for {uploaded_file.name}.")
                else:
                    st.success(f"✅ {uploaded_file.name} uploaded successfully.")

                    # 2. Poll Firestore for result with custom spinner text
                    with st.spinner("☕ Running your assessment... grab a cup of coffee, we’ll be back soon!"):
                        while True:
                            doc = db.collection("jobs").document(job_id).get()

                            if not doc.exists:
                                time.sleep(5)
                                continue

                            job_data = doc.to_dict()
                            status = job_data.get("status")

                            if status == "completed":
                                st.success(f"✅ Assessment Completed for {uploaded_file.name}")

                                # Redirect to /complete-results with job_id
                                new_url = f"{REDIRECT_URL}?job_id={job_id}"
                                js = f"window.open('{new_url}', '_self')"  # same tab
                                st.markdown(f"<script>{js}</script>", unsafe_allow_html=True)
                                break

                            elif status == "failed":
                                st.error(f"❌ Assessment failed for {uploaded_file.name}")
                                break

                            else:
                                time.sleep(5)  # still processing

        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            st.session_state.uploading = False

