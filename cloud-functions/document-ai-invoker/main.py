import os
import json
import base64
import tempfile
from datetime import datetime

import functions_framework
from PyPDF2 import PdfReader, PdfWriter

from google.cloud import storage
from google.cloud import documentai_v1 as documentai

# === CONFIG with hardcoded values ===
PROJECT_ID = "molten-enigma-472206-i4"      # <-- your GCP Project ID
DOC_AI_LOCATION = "us"                      # <-- region where your DocAI processor is deployed
PROCESSOR_ID = "6ecdc4f42d2cf133"          # <-- your Document AI processor ID
OUTPUT_BUCKET = "agents_output_collection"  # <-- bucket where JSON output will be uploaded
MAX_PAGES = 15                              # <-- max pages per split for PDF

# Clients
storage_client = storage.Client(project=PROJECT_ID)
docai_client = documentai.DocumentProcessorServiceClient()


def download_from_gcs(bucket_name: str, blob_name: str, destination_file: str):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(destination_file)
    print(f"Downloaded gs://{bucket_name}/{blob_name} -> {destination_file}")


def upload_to_gcs(bucket_name: str, destination_blob_name: str, source_file_name: str):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)
    print(f"Uploaded {source_file_name} -> gs://{bucket_name}/{destination_blob_name}")


def split_pdf_if_needed(input_pdf_path: str, max_pages: int = MAX_PAGES):
    reader = PdfReader(input_pdf_path)
    total_pages = len(reader.pages)
    parts = []

    if total_pages <= max_pages:
        parts.append(input_pdf_path)
        return parts

    for i in range(0, total_pages, max_pages):
        writer = PdfWriter()
        for j in range(i, min(i + max_pages, total_pages)):
            writer.add_page(reader.pages[j])

        part_filename = os.path.join(
            tempfile.gettempdir(),
            f"{os.path.basename(input_pdf_path)}_part_{(i//max_pages)+1}.pdf"
        )
        with open(part_filename, "wb") as f:
            writer.write(f)
        parts.append(part_filename)
        print(f"Created split part: {part_filename}")

    return parts


def extract_entities(entities):
    """Recursively extract schema-defined entities into dict."""
    data = {}
    for entity in entities:
        field_name = entity.type_
        value = None
        if getattr(entity, "mention_text", None):
            value = entity.mention_text
        elif getattr(entity, "normalized_value", None) and getattr(entity.normalized_value, "text", None):
            value = entity.normalized_value.text
        if getattr(entity, "properties", None):
            data[field_name] = extract_entities(entity.properties)
        else:
            data[field_name] = value
    return data


def process_document_with_docai(file_path: str) -> dict:
    """Process one PDF file with Document AI and return schema-only dict."""
    name = docai_client.processor_path(PROJECT_ID, DOC_AI_LOCATION, PROCESSOR_ID)
    with open(file_path, "rb") as f:
        content = f.read()
    raw_document = documentai.RawDocument(content=content, mime_type="application/pdf")
    request = {"name": name, "raw_document": raw_document}
    result = docai_client.process_document(request=request)
    return extract_entities(result.document.entities)


@functions_framework.cloud_event
def process_pitchdeck(cloud_event):
    """
    Cloud Function entrypoint. Expects Pub/Sub message with JSON payload:
    {
      "job_id": "12345",
      "bucket": "company-data-ai-hackathon",
      "path": "Cashvisory/01. file.pdf",
      "filename": "01. file.pdf",
      "company_name": "ABC Corp"
    }
    """
    job_id = None
    try:
        # --- Decode Pub/Sub message ---
        message_data = cloud_event.data.get("message", {}).get("data")
        if not message_data:
            raise ValueError("No data field in Pub/Sub message")

        payload_json = base64.b64decode(message_data).decode("utf-8")
        payload = json.loads(payload_json)

        job_id = payload.get("job_id", f"job-{datetime.utcnow().isoformat()}")
        bucket_name = payload.get("bucket") or payload.get("bucket_name")
        gcs_path = payload.get("path") or payload.get("gcs_path") or ""
        filename = payload.get("filename") or os.path.basename(gcs_path)
        if gcs_path and gcs_path.endswith(filename) and "/" in gcs_path:
            blob_path = gcs_path
        else:
            folder = payload.get("path", "").strip("/")
            blob_path = f"{folder}/{filename}" if folder else filename
        company_name = payload.get("company_name", "unknown")

        print(f"Received job {job_id}. Bucket: {bucket_name}, blob: {blob_path}, company: {company_name}")

        # --- Download PDF ---
        local_pdf = os.path.join(tempfile.gettempdir(), filename)
        download_from_gcs(bucket_name, blob_path, local_pdf)

        # --- Split if needed ---
        parts = split_pdf_if_needed(local_pdf, max_pages=MAX_PAGES)

        # --- Process each part with Document AI ---
        all_results = []
        for p in parts:
            print(f"Processing part {p} with Document AI...")
            schema_fields = process_document_with_docai(p)
            all_results.append({
                "part_filename": os.path.basename(p),
                "schema_fields": schema_fields
            })

        # --- Save output JSON ---
        output = {
            "job_id": job_id,
            "company_name": company_name,
            "bucket": bucket_name,
            "blob": blob_path,
            "filename": filename,
            "processed_at": datetime.utcnow().isoformat(),
            "parts_count": len(parts),
            "results": all_results
        }
        local_output = os.path.join(tempfile.gettempdir(), f"{job_id}_document_ai_output.json")
        with open(local_output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        gcs_output_path = f"{company_name}/document_ai_output_{job_id}.json"
        upload_to_gcs(OUTPUT_BUCKET, gcs_output_path, local_output)

        print(f"Job {job_id} completed successfully")

    except Exception as e:
        print(f"Error processing job {job_id if job_id else 'unknown'}: {e}")

    return ("", 200)  # Always return 200 for Pub/Sub ack

