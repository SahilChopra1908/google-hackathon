from flask import Flask, render_template, request, jsonify, redirect, url_for
from google.cloud import bigquery
from google.cloud import firestore
import requests
import time
import io
import logging

app = Flask(__name__)

# ==== CONFIG ====
PROJECT_ID = "molten-enigma-472206-i4"
DATASET = "financial_analysis"
TABLES = {
    "📈 Market Metrics": "market_metrics",
    "👨‍💼 Founder Metrics": "founder_metrics",
    "🏢 Company Metrics": "company_metrics",
    "🛠 Product Metrics": "product_tech_metrics",
}

UPLOAD_API_URL = "https://pitch-deck-uploader-225085788448.us-central1.run.app"

# Configure logging
logging.basicConfig(level=logging.INFO)

# BigQuery & Firestore clients
bq_client = bigquery.Client(project=PROJECT_ID)
db = firestore.Client(project=PROJECT_ID, database="ai-evaluation-firestore")

# ===== ROUTES =====

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/submit-assessment", methods=["POST"])
def submit_assessment():
    company_name = request.form.get("company_name")
    uploaded_files = request.files.getlist("pitch_files")
    uploaded_audio = request.files.getlist("audio_files")

    if not company_name or (not uploaded_files and not uploaded_audio):
        logging.error("Missing company name or files")
        return jsonify({"success": False, "message": "Provide company name and upload files."})

    try:
        all_files = uploaded_files + uploaded_audio
        job_id = None  # Will store the first valid job_id

        for f in all_files:
            filename_lower = f.filename.lower()
            if filename_lower.endswith(".pdf"):
                mime_type = "application/pdf"
            elif filename_lower.endswith(".ppt"):
                mime_type = "application/vnd.ms-powerpoint"
            elif filename_lower.endswith(".pptx"):
                mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            elif filename_lower.endswith(".mp3"):
                mime_type = "audio/mpeg"
            elif filename_lower.endswith(".wav"):
                mime_type = "audio/wav"
            elif filename_lower.endswith(".m4a"):
                mime_type = "audio/mp4"
            else:
                mime_type = "application/octet-stream"

            logging.info(f"Preparing to upload file: {f.filename} (MIME: {mime_type})")

            # Convert FileStorage to BytesIO
            f.seek(0)
            file_bytes = io.BytesIO(f.read())
            logging.info(f"File size: {len(file_bytes.getvalue())} bytes")

            files = {"file": (f.filename, file_bytes, mime_type)}
            data = {"company_name": company_name}

            logging.info(f"Sending file {f.filename} to uploader API...")
            resp = requests.post(UPLOAD_API_URL, files=files, data=data)
            logging.info(f"Uploader API response status code: {resp.status_code}")
            resp.raise_for_status()

            resp_json = resp.json()
            logging.info(f"Uploader API response JSON: {resp_json}")

            if "files" not in resp_json:
                return jsonify({"success": False, "message": f"Unexpected response: {resp_json}"})

            # Extract job_id
            for file_resp in resp_json["files"]:
                job_id = file_resp.get("job_id")
                filename = file_resp.get("message", f.filename).split()[0]

                if not job_id:
                    logging.error(f"Failed to get Job ID for {filename}")
                    return jsonify({"success": False, "message": f"Failed to get Job ID for {filename}"})

                logging.info(f"File {filename} uploaded successfully. Job ID: {job_id}")

        if not job_id:
            logging.error("No job_id returned from uploader API")
            return jsonify({"success": False, "message": "No job_id returned from uploader API"})

        # Poll Firestore until status is completed
        logging.info(f"Waiting for assessment to complete in Firestore for Job ID: {job_id}")
        while True:
            doc = db.collection("jobs").document(job_id).get()
            if not doc.exists:
                logging.info(f"Firestore document for job_id={job_id} does not exist yet. Retrying in 5s...")
                time.sleep(5)
                continue

            status = doc.to_dict().get("status")
            logging.info(f"Firestore job_id={job_id} status: {status}")

            if status == "completed":
                logging.info(f"Assessment completed for Job ID: {job_id}")
                break
            elif status == "failed":
                logging.error(f"Assessment failed for Job ID: {job_id}")
                return jsonify({"success": False, "message": f"Assessment failed for Job ID: {job_id}"})
            else:
                logging.info(f"Assessment still in progress for Job ID: {job_id}. Waiting 5s...")
                time.sleep(5)

        logging.info(f"Returning success for Job ID: {job_id}")
        return jsonify({"success": True, "message": "Assessment completed successfully!", "job_id": job_id})

    except Exception as e:
        logging.exception(f"Exception occurred: {e}")
        return jsonify({"success": False, "message": f"Error: {e}"})



@app.route("/complete-results")
def complete_results():
    # For now, fixed startup_id for testing
    startup_id = request.args.get("job_id") or "ST002"
    results_data = {}

    for tab_name, table_name in TABLES.items():
        table_ref = f"{PROJECT_ID}.{DATASET}.{table_name}"
        table = bq_client.get_table(table_ref)
        schema_info = {field.name: field.description for field in table.schema}

        query = f"""
            SELECT * FROM `{table_ref}`
            WHERE startup_id = @startup_id
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
        )

        query_result = list(bq_client.query(query, job_config=job_config).result())
        if not query_result:
            results_data[tab_name] = []
            continue

        row = query_result[0]
        tab_rows = []
        for field in row.keys():
            if field == "startup_id":
                continue
            tab_rows.append({"desc": schema_info.get(field, field), "value": row[field]})

        results_data[tab_name] = tab_rows

    return render_template("results.html", job_id=startup_id, results_data=results_data)


@app.route("/deal-note")
def deal_note():
    startup_id = request.args.get("job_id")
    # Fallback for testing if job_id is not in the URL
    if not startup_id:
        startup_id = "ST002"

    deal_note_content = "No deal note found for this startup."

    try:
        table_ref = f"{PROJECT_ID}.{DATASET}.final_deal_note"
        query = f"""
            SELECT summary FROM `{table_ref}`
            WHERE startup_id = @startup_id
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
        )

        query_result = list(bq_client.query(query, job_config=job_config).result())
        if query_result and query_result[0]['summary']:
            deal_note_content = query_result[0]['summary']

    except Exception as e:
        logging.error(f"Error fetching deal note for {startup_id}: {e}")
        deal_note_content = f"An error occurred while fetching the deal note. Please check the logs."

    return render_template("deal_note.html", job_id=startup_id, deal_note=deal_note_content)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
