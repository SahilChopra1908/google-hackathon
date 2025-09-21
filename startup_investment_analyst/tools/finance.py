# financial_tool.py
# Tool wrapper for FinancialAgent

import os
from typing import Dict, Any
from google.cloud import bigquery
from google.adk.tools import ToolContext, FunctionTool
from ..shared_libraries import constants

# Set service account if provided
# if constants.SERVICE_ACCOUNT_PATH:
#     os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

# Initialize BigQuery client
try:
    bq_client = bigquery.Client(project=constants.PROJECT_ID)
except Exception as e:
    print(f"Error initializing BigQuery client: {e}")
    bq_client = None


async def financial_tool_runner(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Tool wrapper for FinancialAgent.
    Reads financial metrics from BigQuery and produces investor-focused analysis.
    """
    startup_id = tool_context.user_content.parts[0].text.strip()
    if not bq_client or not startup_id:
        return {"error": "BigQuery client not initialized or startup_id missing."}

    # Fetch financial metrics
    query = f"""
        SELECT growth_rate, burn_rate, profit_margin, customer_acquisition_cost, ebitda, team_size
        FROM `{constants.PROJECT_ID}.{constants.BQ_DATASET}.company_metrics`
        WHERE startup_id = @startup_id
        LIMIT 1
    """
    job = bq_client.query(query, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
    ))
    rows = [dict(r) for r in job.result()]
    metrics = rows[0] if rows else {}

    # Compute investment score
    score = 50
    gr = metrics.get("growth_rate") or 0
    burn = metrics.get("burn_rate") or 0
    pm = metrics.get("profit_margin") if metrics.get("profit_margin") is not None else -0.5

    if gr >= 0.25:
        score += 15
    elif gr >= 0.1:
        score += 5
    if burn > 100000:
        score -= 10
    if pm > 0:
        score += 10
    elif pm < -0.5:
        score -= 10

    score = max(0, min(100, score))

    # Recommendation
    if score >= 70:
        recommendation = "Invest"
    elif score >= 40:
        recommendation = "Monitor"
    else:
        recommendation = "Avoid"

    # Compose summary
    summary_points = [
        f"Growth rate: {gr:.2%}",
        f"Burn rate: ${burn:,}",
        f"Profit margin: {pm:.2%}" if pm is not None else "Profit margin: N/A",
        f"EBITDA: {metrics.get('ebitda', 'N/A')}",
        f"Team size: {metrics.get('team_size', 'N/A')}",
    ]

    detailed_analysis = f"""
    The company shows a growth rate of {gr:.2%} with a burn rate of ${burn:,}. 
    Profit margins are {pm:.2%} and EBITDA is {metrics.get('ebitda', 'N/A')}.
    The team size is {metrics.get('team_size', 'N/A')}, which indicates operational capacity.
    Based on these metrics, the investment attractiveness score is {score}/100, leading to a recommendation of '{recommendation}'.
    """

    return {
        "startup_name": startup_id,
        "summary": summary_points,
        "detailed_analysis": detailed_analysis.strip(),
        "investment_score": score,
        "recommendation": recommendation,
        "financial_data": metrics
    }


# Wrap as FunctionTool
financial_tool = FunctionTool(financial_tool_runner)
