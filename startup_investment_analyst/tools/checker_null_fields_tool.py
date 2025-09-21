import os
from typing import Dict, Any
from google.cloud import bigquery
from google.adk.tools import FunctionTool, ToolContext
from ..shared_libraries import constants

# Set credentials
# if constants.SERVICE_ACCOUNT_PATH:
#     os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

# BigQuery client
try:
    bq_client = bigquery.Client(project=constants.PROJECT_ID)
    print("✅ BigQuery client initialized")
except Exception as e:
    print(f"❌ Error initializing BigQuery client: {e}")
    bq_client = None


# Updated function signature to accept startup_id directly
def checker_fetch_data_runner(startup_id: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Fetch all available row data for a startup_id from multiple BigQuery tables.
    """
    # The agent will now pass the startup_id directly as an argument.
    # No need to extract it from tool_context.user_content.parts
    if not bq_client or not startup_id:
        return {"error": "BigQuery client not initialized or startup_id missing."}
    
    print(f"🔍 Fetching data for startup_id: {startup_id}")
    startup_data = {}

    for table_name in constants.TABLES.values():
        try:
            query = f"""
                SELECT * FROM `{constants.PROJECT_ID}.{constants.BQ_DATASET}.{table_name}`
                WHERE startup_id = @startup_id
                LIMIT 1
            """
            job = bq_client.query(query, job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
            ))
            rows = [dict(r) for r in job.result()]

            if rows:
                startup_data[table_name] = rows[0]
                print(f"✅ Data fetched from {table_name}")

        except Exception as e:
            print(f"⚠️ Error fetching data from {table_name}: {e}")
            startup_data[table_name] = {"error": str(e)}

    print(startup_data)

    return {
        "startup_id": startup_id,
        "data": startup_data,
        "message": f"Fetched data from {len(startup_data)} table(s)."
    }


# Export as FunctionTool
checker_fetch_data_tool = FunctionTool(checker_fetch_data_runner)
