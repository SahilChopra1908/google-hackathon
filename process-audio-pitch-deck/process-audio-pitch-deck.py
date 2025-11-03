import os
import re
import json
import base64
import tempfile
from datetime import datetime
import uuid
import google.generativeai as genai
from google.cloud import bigquery, storage
import functions_framework

# -------------------------------
# Environment & Config
# -------------------------------
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

BQ_PROJECT = os.getenv("BQ_PROJECT")
BQ_DATASET = os.getenv("BQ_DATASET")
BQ_TABLES = os.getenv("BQ_TABLES", "").split(",")

storage_client = storage.Client(project=BQ_PROJECT)
bq_client = bigquery.Client(project=BQ_PROJECT)

# -------------------------------
# Helpers (reuse from your raw code)
# -------------------------------
def parse_numeric(value: str):
    if value is None:
        return None
    val = value.lower().replace(",", "").strip()
    multiplier = 1
    if "million" in val: multiplier = 1_000_000
    elif "billion" in val: multiplier = 1_000_000_000
    elif "lakh" in val: multiplier = 100_000
    elif "crore" in val: multiplier = 10_000_000
    match = re.search(r"[\d.]+", val)
    if not match: return None
    try:
        return float(match.group()) * multiplier
    except: return None

def get_dataset_schema(project_id, dataset_id, allowed_tables):
    schema_map = {}
    for table in allowed_tables:
        if not table.strip():
            continue
        table_ref = bq_client.dataset(dataset_id, project=project_id).table(table)
        table_obj = bq_client.get_table(table_ref)
        schema_map[table] = [field.name for field in table_obj.schema]
    return schema_map

def build_prompt(schema_map):
    fields = []
    for _, cols in schema_map.items():
        fields.extend(cols)
    unique_fields = list(set(fields))
    json_schema = {col: "" for col in unique_fields}
    prompt = f"""
You are a helpful assistant. 
Step 1: Transcribe the audio/video into clean text.
Step 2: Extract structured information.

Return the result strictly in JSON with the following fields:
{json.dumps(json_schema, indent=2)}

Rules:
- Every field must be present in JSON
- If no match is found, use "" or []
"""
    return prompt

def process_audio_with_dynamic_prompt(audio_file: str, schema_map: dict):
    model = genai.GenerativeModel("gemini-2.5-pro")
    prompt = build_prompt(schema_map)

    with open(audio_file, "rb") as f:
        audio_bytes = f.read()

    response = model.generate_content(
        [prompt, {"mime_type": "audio/wav", "data": audio_bytes}]
    )
    raw_text = response.text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Invalid JSON from Gemini: {raw_text[:200]}...")

def insert_into_bigquery(project_id, dataset_id, schema_map, extracted_data):
    today = datetime.utcnow()
    skip_fields = {"funding_rounds", "traffic_stats", "social_media_followers"}

    # --- Step 1: Ensure IDs are present ---
    for id_field in ["startup_id", "founder_id", "job_id"]:
        if not extracted_data.get(id_field) or str(extracted_data.get(id_field)).strip() == "":
            new_id = str(uuid.uuid4())
            extracted_data[id_field] = new_id
            print(f"🆔 Auto-generated {id_field}: {new_id}")

    # --- Step 2: Fix startup_name vs founder_name mix-ups ---
    startup_name = extracted_data.get("startup_name", "")
    founder_name = extracted_data.get("founder_name", "") or extracted_data.get("name", "")

    if founder_name and any(x in founder_name.lower() for x in ["inc", "ltd", "corp", "pvt"]):
        print("⚠️ Detected founder_name looks like a company, swapping with startup_name")
        startup_name, founder_name = founder_name, startup_name

    extracted_data["startup_name"] = startup_name
    extracted_data["founder_name"] = founder_name

    # --- Step 3: Insert into each table ---
    for table, fields in schema_map.items():
        row = {}
        table_ref = bq_client.dataset(dataset_id, project=project_id).table(table)
        table_obj = bq_client.get_table(table_ref)

        for field in fields:
            if field in skip_fields:
                row[field] = []
                continue

            # --- Special handling for startups table ---
            if table == "startups" and field == "name":
                value = extracted_data.get("startup_name", "N/A")
            elif table == "startups" and field == "founder":
                value = extracted_data.get("founder", extracted_data.get("founder_name", ""))
            else:
                value = extracted_data.get(field, None)

            schema_field = next((f for f in table_obj.schema if f.name == field), None)
            if not schema_field:
                continue

            # --- Date & timestamp handling ---
            if schema_field.field_type in ["DATE", "DATETIME", "TIMESTAMP"] and not value:
                value = today
            if schema_field.field_type == "DATE" and isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d")
            elif schema_field.field_type in ["DATETIME", "TIMESTAMP"] and isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d %H:%M:%S")

            # --- Repeated fields ---
            if schema_field.mode == "REPEATED":
                if value is None:
                    value = []
                elif isinstance(value, str) and "," in value:
                    value = [v.strip() for v in value.split(",") if v.strip()]
                elif not isinstance(value, list):
                    value = [value]
                if schema_field.field_type == "STRING":
                    value = [str(v) for v in value if v not in [None, ""]]

            # --- Numeric fields ---
            if schema_field.field_type in ["INTEGER", "INT64"]:
                if isinstance(value, str): value = parse_numeric(value)
                if isinstance(value, float): value = int(round(value))
            elif schema_field.field_type in ["FLOAT", "FLOAT64", "NUMERIC"]:
                if isinstance(value, str): value = parse_numeric(value)

            # --- Boolean fields ---
            if schema_field.field_type == "BOOLEAN":
                if isinstance(value, str):
                    val = value.strip().lower()
                    if val in ["true", "yes", "1"]:
                        value = True
                    elif val in ["false", "no", "0", ""]:
                        value = False
                    else:
                        value = True
                elif value is None:
                    value = False
                else:
                    value = bool(value)

            # --- Non-nullable strings ---
            if schema_field.field_type == "STRING" and not schema_field.is_nullable and value is None:
                value = "N/A"

            row[field] = value

        print("\n🔍 DEBUG: Preparing to insert row")
        print(f"   ➤ Table: {project_id}.{dataset_id}.{table}")
        print(f"   ➤ Row data: {row}")

        errors = bq_client.insert_rows_json(table_ref, [row])
        if errors:
            print(f"❌ Insert error in {table}: {errors}")
        else:
            print(f"✅ Inserted into {table}")

# -------------------------------
# Cloud Function Entrypoint
# -------------------------------
@functions_framework.cloud_event
def process_audio(cloud_event):
    """
    Triggered by Pub/Sub when an audio file is uploaded.
    Expects payload:
    {
      "job_id": "...",
      "bucket": "...",
      "path": "Company/audio.wav",
      "filename": "audio.wav",
      "company_name": "Acme"
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

        # --- Download from GCS ---
        local_audio = os.path.join(tempfile.gettempdir(), filename)
        bucket_obj = storage_client.bucket(bucket_name)
        blob = bucket_obj.blob(gcs_path)
        blob.download_to_filename(local_audio)
        print(f"⬇️ Downloaded to {local_audio}")

        # --- BigQuery schema ---
        schema_map = get_dataset_schema(BQ_PROJECT, BQ_DATASET, BQ_TABLES)

        # --- Process audio with Gemini ---
        extracted = process_audio_with_dynamic_prompt(local_audio, schema_map)

        # --- Insert into BigQuery ---
        insert_into_bigquery(BQ_PROJECT, BQ_DATASET, schema_map, extracted)

        print(f"✅ Job {job_id} finished successfully")

    except Exception as e:
        print(f"🔥 Error processing audio job {job_id or 'unknown'}: {e}")

    return ("", 200)  # Always ack Pub/Sub
