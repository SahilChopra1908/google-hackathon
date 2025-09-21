# json_uploader_tool.py
import os
import json
import tempfile
from typing import Dict, Any
from google.cloud import storage
from google.adk.tools import FunctionTool, ToolContext
from startup_investment_analyst.shared_libraries import constants

# Ensure GOOGLE_APPLICATION_CREDENTIALS is set
# if constants.SERVICE_ACCOUNT_PATH:
#     os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

# Storage client
try:
    storage_client = storage.Client(project=constants.PROJECT_ID)
except Exception as e:
    print(f"Error initializing GCS client: {e}")
    storage_client = None


async def json_uploader_runner(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Upload JSON content to GCS.
    Expects:
      parts[0] = startup_id / filename
      parts[1] = dictionary content (stringified JSON or dict)
    """
    parts = getattr(tool_context.user_content, "parts", None)
    if not parts or len(parts) < 2:
        return {"error": "Expected at least 2 parts: filename/startup_id and JSON content."}

    startup_id = parts[0].text.strip()
    content = parts[1].text.strip()

    # If content is string, try to parse as dict
    try:
        if isinstance(content, str):
            content_dict = json.loads(content)
        else:
            content_dict = content
    except Exception as e:
        return {"error": f"Failed to parse JSON content: {e}"}

    # Create local JSON file
    tmp_dir = tempfile.mkdtemp()
    filename = f"{startup_id}.json"
    local_path = os.path.join(tmp_dir, filename)

    try:
        with open(local_path, "w") as f:
            json.dump(content_dict, f, indent=2)
    except Exception as e:
        return {"error": f"Failed to write local JSON file: {e}"}

    # Upload to GCS
    bucket_name = getattr(constants, "GCS_BUCKET", None)
    prefix = getattr(constants, "GCS_PREFIX", "").strip().strip("/")
    if not bucket_name:
        return {"error": "GCS_BUCKET not configured in constants."}

    remote_path = f"{prefix}/{filename}" if prefix else filename
    gcs_uri = f"gs://{bucket_name}/{remote_path}"

    if not storage_client:
        return {"error": "GCS client not initialized."}

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(remote_path)
        blob.upload_from_filename(local_path)
        return {"success": True, "gcs_uri": gcs_uri, "local_path": local_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Export as FunctionTool
json_uploader_tool = FunctionTool(json_uploader_runner)