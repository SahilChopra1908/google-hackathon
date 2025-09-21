import os
import json
from google.cloud import bigquery, storage
from google.adk.tools import FunctionTool, ToolContext
from ..shared_libraries import constants

# Set credentials
# if constants.SERVICE_ACCOUNT_PATH:
#     os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

# BigQuery client
try:
    bq_client = bigquery.Client(project=constants.PROJECT_ID)
except Exception as e:
    print(f"Error initializing BigQuery client: {e}")
    bq_client = None

# Storage client
try:
    storage_client = storage.Client(project=constants.PROJECT_ID)
except Exception as e:
    print(f"Error initializing GCS client: {e}")
    storage_client = None


async def checker_gcs_backfill_runner(tool_context: ToolContext) -> dict[str]:
    """
    Download GCS file, extract fields, and update BigQuery.
    Expects:
    - startup_id
    - gcs_file_path
    - missing_fields_summary (JSON string)
    """
    parts = tool_context.user_content.parts
    startup_id = parts[0].text.strip()
    gcs_file_path = parts[1].text.strip()
    missing_fields_summary = json.loads(parts[2].text.strip())
    print("Line 38")

    if not bq_client or not storage_client:
        return {"error": "BigQuery or GCS client not initialized."}

    # --- Fetch GCS content ---
    bucket_name = constants.GCS_BUCKET
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(gcs_file_path)
    if not blob.exists():
        return {"error": f"GCS file not found: {gcs_file_path}"}
    content = blob.download_as_text()

    # --- Parse JSON/PDF stub ---
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {}

    updates_applied = {}

    for table, fields in missing_fields_summary.items():
        updates = {}
        for f in fields:
            if f in parsed and parsed[f] not in (None, "", []):
                updates[f] = parsed[f]
        if updates:
            # Update BigQuery
            set_clause = ", ".join([f"{col} = @{col}" for col in updates.keys()])
            query = f"""
                UPDATE `{constants.PROJECT_ID}.{constants.BQ_DATASET}.{table}`
                SET {set_clause}
                WHERE startup_id = @startup_id
            """
            params = [bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
            for col, val in updates.items():
                params.append(bigquery.ScalarQueryParameter(col, "STRING", val))
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            bq_client.query(query, job_config=job_config).result()
            updates_applied[table] = updates

    return {
        "startup_id": startup_id,
        "gcs_file_path": gcs_file_path,
        "updates_applied": updates_applied
    }


checker_gcs_backfill_tool = FunctionTool(checker_gcs_backfill_runner)
