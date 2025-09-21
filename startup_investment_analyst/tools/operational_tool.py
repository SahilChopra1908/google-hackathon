# operational_tool.py
# Tool wrapper for OperationalAgent

import os
from typing import Dict, Any
from google.cloud import bigquery
from google.adk.tools import ToolContext, FunctionTool
from ..shared_libraries import constants

# Set service account if provided
# if constants.SERVICE_ACCOUNT_PATH:
#     os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

# Initialize BigQuery client safely
try:
    bq_client = bigquery.Client(project=constants.PROJECT_ID)
except Exception as e:
    print(f"Error initializing BigQuery client: {e}")
    bq_client = None


async def operational_tool_runner(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Reads operational data from BigQuery and produces an investor-friendly summary.
    """
    # Extract startup_id safely
    try:
        startup_id = tool_context.user_content.parts[0].text.strip()
    except Exception:
        return {"error": "startup_id not found in ToolContext."}

    if not bq_client:
        return {"error": "BigQuery client not initialized."}
    if not startup_id:
        return {"error": "startup_id is empty."}

    # Fetch operational metrics
    query = f"""
        SELECT team_size, hiring_trend, app_store_rating, play_store_rating, amazon_store_rating,
               geographical_locations, funding_rounds, profit_margin
        FROM `{constants.PROJECT_ID}.{constants.BQ_DATASET}.company_metrics`
        WHERE startup_id = @startup_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
    )

    try:
        job = bq_client.query(query, job_config=job_config)
        rows = [dict(r) for r in job.result()]
        ops = rows[0] if rows else {}
    except Exception as e:
        return {"error": f"Failed to fetch operational data: {e}"}

    # Compute operational score
    score = 50
    team = ops.get("team_size") or 0
    hiring = ops.get("hiring_trend") or 0
    ratings = [ops.get("app_store_rating") or 0,
               ops.get("play_store_rating") or 0,
               ops.get("amazon_store_rating") or 0]
    valid_ratings = [r for r in ratings if r]
    avg_rating = sum(valid_ratings) / (len(valid_ratings) or 1)

    if avg_rating >= 4.0:
        score += 15
    elif avg_rating >= 3.5:
        score += 5

    if team >= 10 and hiring >= 0.2:
        score += 10
    elif team < 5:
        score -= 10

    score = max(0, min(100, score))

    # Identify risks
    risks = []
    if team < 5:
        risks.append("Small team")
    if avg_rating < 3.5:
        risks.append("Low ratings")
    if ops.get("funding_rounds", 0) == 0:
        risks.append("No funding history")

    # Compose summary
    summary = f"""
Operational Analysis Summary for {startup_id}:
- Team size: {team}
- Hiring trend: {hiring}
- Average ratings: {avg_rating:.2f}
- Geographical presence: {ops.get('geographical_locations', 'N/A')}
- Funding rounds: {ops.get('funding_rounds', 'N/A')}
- Profit margin: {ops.get('profit_margin', 'N/A')}
- Risks identified: {', '.join(risks) if risks else 'None'}
- Operational score: {score}/100
"""

    return {
        "startup_id": startup_id,
        "operational_data": ops,
        "operational_score": score,
        "risks": risks,
        "summary": summary.strip(),
    }


# Wrap as FunctionTool (ADK-compliant)
operational_tool = FunctionTool(func=operational_tool_runner)
