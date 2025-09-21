# refiner_agent.py
import os
import time
import json
import base64 
import re
import tempfile
from typing import List, Dict, Any
from google.cloud import firestore

import functions_framework
from google.cloud import storage, bigquery
from google.cloud import pubsub_v1
from google.api_core.exceptions import NotFound

# === CONFIG ===
PROJECT_ID = os.environ.get("PROJECT_ID", "molten-enigma-472206-i4")
LOCATION = os.environ.get("LOCATION", "us")

# Firestore client
FIRESTORE_COLLECTION = "jobs"
FIRESTORE_DB = "ai-evaluation-firestore"
firestore_client = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DB)

# Optional Vertex AI imports - if you use Vertex AI Python library
try:
    from google.cloud import aiplatform
    VERTEX_AVAILABLE = True
except Exception:
    VERTEX_AVAILABLE = False

# === CONFIG (use env vars in Cloud Functions) ===
PROJECT_ID = os.environ.get("PROJECT_ID", "molten-enigma-472206-i4")
LOCATION = os.environ.get("LOCATION", "us")   # region for Vertex AI if used
AGENTS_BUCKET = os.environ.get("AGENTS_BUCKET", "agents_output_collection")
SLEEP_SECONDS = int(os.environ.get("SLEEP_SECONDS", "12"))  # 2 minutes default

# BigQuery tables (project.dataset.table)
BQ_COMPANY_METRICS = "molten-enigma-472206-i4.financial_analysis.company_metrics"
BQ_FOUNDER_METRICS = "molten-enigma-472206-i4.financial_analysis.founder_metrics"
BQ_PRODUCT_TECH_METRICS = "molten-enigma-472206-i4.financial_analysis.product_tech_metrics"
BQ_MARKET_METRICS = "molten-enigma-472206-i4.financial_analysis.market_metrics"

# Initialize clients
storage_client = storage.Client(project=PROJECT_ID)
bq_client = bigquery.Client(project=PROJECT_ID)
publisher = pubsub_v1.PublisherClient()  # if you need to republish results (optional)


# ---------------------------
# Helper: list matching files
# ---------------------------
def list_agent_files(bucket_name: str, company_name: str, job_id: str) -> List[str]:
    """List GCS object names matching pattern: {company_name}/*_{job_id}.json"""
    prefix = f"{company_name}/"
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    pattern = re.compile(rf".*_{re.escape(job_id)}\.json$")
    matches = []
    for b in blobs:
        if pattern.match(b.name):
            matches.append(b.name)
    return matches


# -------------------------
# Helper: download & load
# -------------------------
def download_and_load_json(bucket_name: str, blob_name: str) -> Dict[str, Any]:
    fd, tmp_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(tmp_path)
    with open(tmp_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    os.remove(tmp_path)
    return data


# -------------------------
# Merge multiple JSONs
# -------------------------
def merge_agent_outputs(list_of_jsons: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge several agent output JSONs into one aggregated dictionary.
    - Concatenate 'results' arrays
    - Keep top-level fields from first JSON (job_id, company_name, etc.)
    """
    merged = {}
    if not list_of_jsons:
        return merged
    merged.update({k: v for k, v in list_of_jsons[0].items() if k != "results"})
    merged["results"] = []
    for j in list_of_jsons:
        r = j.get("results", [])
        merged["results"].extend(r)
    return merged


# -------------------------
# Heuristic mapper (fallback)
# -------------------------
def heuristic_map_to_tables(merged: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Map extracted schema_fields into rows for each BigQuery table using heuristics.
    Returns dict with keys: 'company_metrics', 'founder_metrics', 'product_tech_metrics', 'market_metrics'
    Each maps to a list of row dicts (ready for insert_rows_json).
    """
    job_id = merged.get("job_id")
    company_name = merged.get("company_name")
    rows_company = []
    rows_founder = []
    rows_product = []
    rows_market = []

    # Collect all schema_fields from all parts into one flat dict (last value wins)
    flat = {}
    for part in merged.get("results", []):
        sf = part.get("schema_fields", {})
        for k, v in sf.items():
            flat[k] = v

    # Helper to pop keys by prefix
    def keys_with_prefix(pref):
        return {k: flat[k] for k in list(flat.keys()) if k.startswith(pref)}

    # Company metrics mapping
    company = {
        "startup_id": job_id,
        "company_name": company_name,
        "current_userbase": flat.get("company_metrics:current_userbase"),
        "key_problems_solved": flat.get("company_metrics:key_problems_solved"),
        "capital_ask": flat.get("company_metrics:capital_ask"),
        # add more fields mapping as available
    }
    rows_company.append({k: v for k, v in company.items() if v is not None})

    # Founder mapping: attempt to derive founder block(s)
    founder_block = keys_with_prefix("founder_metrics:") or keys_with_prefix("startups:founder") or keys_with_prefix("founder:")
    if founder_block:
        # It's possible there are multiple founder entries; for simplicity create one row
        frow = {
            "startup_id": job_id,
            "founder_id": f"{job_id}_founder_1",
            "name": founder_block.get("founder_metrics:name") or founder_block.get("startups:founder") or founder_block.get("founder:name"),
            "background": founder_block.get("founder_metrics:background"),
            "track_record": founder_block.get("founder_metrics:track_record"),
            "domain_expertise": founder_block.get("founder_metrics:domain_expertise"),
            "linkedin_url": founder_block.get("founder_metrics:linkedin_url")
        }
        rows_founder.append({k: v for k, v in frow.items() if v is not None})

    # Product mapping (heuristic)
    product = {
        "startup_id": job_id,
        "product_name": flat.get("product_metrics:product_name") or flat.get("startups:product"),
        "product_stage": flat.get("product_metrics:stage"),
        "product_summary": flat.get("product_metrics:summary")
    }
    rows_product.append({k: v for k, v in product.items() if v is not None})

    # Market/tech mapping
    market = {
        "startup_id": job_id,
        "competitors": flat.get("market_metrics:competitors"),
        "market_growth_rate": flat.get("market_metrics:market_growth_rate"),
        "total_addressable_market": flat.get("market_metrics:total_addressable_market"),
        "service_addressable_market": flat.get("market_metrics:service_addressable_market")
    }
    rows_market.append({k: v for k, v in market.items() if v is not None})

    return {
        "company_metrics": rows_company,
        "founder_metrics": rows_founder,
        "product_tech_metrics": rows_product,
        "market_metrics": rows_market
    }


# -------------------------
# Vertex AI (Gemini) mapping
# -------------------------
def call_gemini_mapping(merged_json: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Ask Gemini 2.5 Pro to map schema_fields into the target tables.
    This function attempts to call Vertex AI if available. Replace with your exact Vertex client call if needed.
    If Vertex isn't available or call fails, raises an exception which the caller will catch and fallback to heuristics.
    """
    if not VERTEX_AVAILABLE:
        raise RuntimeError("Vertex AI sdk not available in environment.")

    # Initialize Vertex
    aiplatform.init(project=PROJECT_ID, location=LOCATION)

    # Use the text generation model - replace model name with the exact one you have access to
    # For example, "gemini-2.5-pro" if available to your project.
    MODEL_NAME = "gemini-2.5-pro"  # ensure your project has access to this model
    model = aiplatform.TextGenerationModel.from_pretrained(MODEL_NAME)

    # Create prompt: ask the model to return JSON with four keys mapping to arrays of row objects
    prompt = f"""
You are given extracted JSON from Document AI for a startup. Map the extracted 'schema_fields'
into rows for these BigQuery tables: company_metrics, founder_metrics, product_tech_metrics, market_metrics.

Input JSON:
{json.dumps(merged_json, indent=2)}

Return a JSON object with exactly these keys:
- company_metrics: array of objects (each with startup_id and relevant fields)
- founder_metrics: array of objects (startup_id, founder_id, name, background, track_record, domain_expertise, linkedin_url)
- product_tech_metrics: array of objects (startup_id, product_name, product_stage, product_summary)
- market_metrics: array of objects (startup_id, competitors, market_growth_rate, total_addressable_market, service_addressable_market)

Do NOT include any other keys. Use startup_id = the job_id from input. If a field isn't present, omit it.
Output only the JSON.
"""

    response = model.predict(prompt, max_output_tokens=1024)
    text = response.text.strip()

    # Parse JSON out of the model output robustly
    # Models sometimes wrap JSON in triple backticks; strip them
    text = re.sub(r"^```(?:json)?", "", text)
    text = re.sub(r"```$", "", text).strip()

    mapped = json.loads(text)
    return mapped


# -------------------------
# Insert into BigQuery
# -------------------------
# -------------------------
# Insert into BigQuery
# -------------------------
def insert_rows_into_bq(table_name: str, rows: list):
    """
    Inserts a list of rows into the specified BigQuery table.
    Only keeps fields that exist in the table schema.
    Handles both plain table names and fully-qualified table IDs.
    """
    if not rows:
        print(f"No rows to insert for table {table_name}")
        return

    # Ensure table_name is fully-qualified
    if table_name.count(".") == 2:
        # Already in project.dataset.table format
        full_table_id = table_name
    else:
        full_table_id = f"molten-enigma-472206-i4.financial_analysis.{table_name}"

    try:
        # Fetch table schema to filter allowed fields
        table_ref = bq_client.get_table(full_table_id)
        allowed_fields = {field.name for field in table_ref.schema}

        # Keep only allowed fields
        cleaned_rows = [{k: v for k, v in row.items() if k in allowed_fields} for row in rows]

        # Insert into BigQuery
        errors = bq_client.insert_rows_json(table_ref, cleaned_rows)
        if errors:
            print(f"Errors when inserting into {full_table_id}: {errors}")
        else:
            print(f"Inserted {len(cleaned_rows)} rows into {full_table_id}.")

    except Exception as e:
        print(f"Exception inserting into {full_table_id}: {e}")




# -------------------------
# Cloud Function entrypoint
# -------------------------
@functions_framework.cloud_event
def refiner_agent(cloud_event):
    """
    Pub/Sub-triggered Cloud Function.
    Expects message.data to be base64 JSON similar to your original:
    {
      "job_id": "...",
      "company_name": "...",
      "bucket": "...",
      "path": "...",
      "filename": "...",
      ...
    }
    """
    try:
        message_data_b64 = cloud_event.data.get("message", {}).get("data")
        if not message_data_b64:
            print("No data field in incoming Pub/Sub message")
            return ("", 200)

        payload_str = base64.b64decode(message_data_b64).decode("utf-8")
        payload = json.loads(payload_str)

        job_id = payload.get("job_id")
        company_name = payload.get("company_name")
        bucket_name = "agents_output_collection"

        if not job_id or not company_name:
            print("Missing job_id or company_name; skipping.")
            return ("", 200)

        print(f"Refiner received job_id={job_id}, company={company_name}. Sleeping {SLEEP_SECONDS}s to wait for other processors.")
        time.sleep(SLEEP_SECONDS)

        # list files
        print("Listing agent output files in GCS...")
        matches = list_agent_files(bucket_name, company_name, job_id)
        if not matches:
            print(f"No matching files found for {company_name}/*_{job_id}.json in bucket {bucket_name}")
            return ("", 200)

        print(f"Found {len(matches)} files: {matches}")

        # download all
        jsons = []
        for bname in matches:
            print(f"Downloading {bname} ...")
            try:
                j = download_and_load_json(bucket_name, bname)
                jsons.append(j)
            except Exception as ex:
                print(f"Failed to download/load {bname}: {ex}")

        merged = merge_agent_outputs(jsons)
        print("Merged JSON prepared.")

        # Try to call Gemini (Vertex AI) to map; fallback to heuristic
        try:
            mapped = call_gemini_mapping(merged)
            print("Mapping via Gemini succeeded.")
        except Exception as e:
            print(f"Gemini mapping failed or not available: {e}. Falling back to heuristic mapper.")
            mapped = heuristic_map_to_tables(merged)

        # Insert into BigQuery
        print("Inserting into BigQuery...")
        insert_rows_into_bq(BQ_COMPANY_METRICS, mapped.get("company_metrics", []))
        insert_rows_into_bq(BQ_FOUNDER_METRICS, mapped.get("founder_metrics", []))
        insert_rows_into_bq(BQ_PRODUCT_TECH_METRICS, mapped.get("product_tech_metrics", []))
        insert_rows_into_bq(BQ_MARKET_METRICS, mapped.get("market_metrics", []))

        print(f"Refiner job {job_id} completed successfully.")


        # Push job_id to Firestore
        try:
            doc_ref = firestore_client.collection(FIRESTORE_COLLECTION).document(job_id)
            doc_ref.set({
                "job_id": job_id,
                "company_name": company_name,
                "status": "completed",
                "firestore_db": FIRESTORE_DB,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            print(f"Pushed job_id={job_id} to Firestore collection '{FIRESTORE_COLLECTION}'.")
        except Exception as e:
            print(f"Failed to push job_id={job_id} to Firestore: {e}")

    except Exception as exc:
        print(f"Unexpected error in refiner_agent: {exc}")

    return ("", 200)
