import functions_framework
from google.cloud import storage, pubsub_v1
from flask import request, jsonify
import datetime
import json

# ==== CONFIG ====
BUCKET_NAME = "company-data-ai-hackathon"
TOPIC_DOC = "projects/molten-enigma-472206-i4/topics/gcs-upload-docuement-ai"
TOPIC_AUDIO = "projects/molten-enigma-472206-i4/topics/gcs-upload-audio-ai"

# Initialize clients
storage_client = storage.Client()
publisher = pubsub_v1.PublisherClient()


@functions_framework.http
def upload_pitchdeck(request):
    """
    HTTP Cloud Function to upload multiple pitch decks/audio files to GCS and 
    publish metadata to the correct Pub/Sub topic.
    """
    try:
        company_name = request.form.get("company_name")
        if not company_name:
            return jsonify({"error": "company_name is required"}), 400

        if "file" not in request.files:
            return jsonify({"error": "file(s) required"}), 400

        # Multiple files support
        files = request.files.getlist("file")

        responses = []
        audio_ext = (".mp3", ".wav", ".m4a")

        for file in files:
            filename = file.filename.lower()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            blob_name = f"{company_name}/{timestamp}_{filename}"

            # Upload to GCS
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(blob_name)
            blob.upload_from_file(file, content_type=file.content_type)

            job_id = f"{company_name}_{timestamp}"

            # Route based on file type
            if filename.endswith(audio_ext):
                topic_path = TOPIC_AUDIO
                job_type = "AUDIO"
            else:
                topic_path = TOPIC_DOC
                job_type = "DOCUMENT"

            # Pub/Sub message
            message = {
                "job_id": job_id,
                "bucket": BUCKET_NAME,
                "path": blob_name,
                "filename": filename,
                "company_name": company_name,
                "timestamp": timestamp,
                "job_type": job_type,
            }

            publisher.publish(
                topic_path,
                data=json.dumps(message).encode("utf-8")
            ).result()

            responses.append({
                "job_id": job_id,
                "job_type": job_type,
                "message": f"{filename} uploaded and published to {job_type} pipeline",
                "path": blob_name
            })

        # Wrap responses in a dictionary so UI can safely call .get()
        return jsonify({"files": responses}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

