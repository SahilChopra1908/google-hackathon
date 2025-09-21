import json
import os
from datetime import datetime

# Make sure to install the required libraries:
# pip install google-cloud-storage google-cloud-bigquery
from google.adk import Agent
from google.adk.agents import ParallelAgent, SequentialAgent
from google.adk.tools import FunctionTool
from google.cloud import bigquery
from google.cloud import storage
from google.genai import types

from .shared_libraries import constants
from .sub_agents.checker.agent import checker_agent
from .sub_agents.financial.agent import financial_agent
from .sub_agents.market_intel.agent import market_intel_agent
from .sub_agents.operational.agent import operational_agent
from .sub_agents.researcher.agent import researcher_agent
from .sub_agents.synthesis.agent import synthesis_agent


# ----------------------------
# BigQuery Writer Tool and Agent
# ----------------------------

def insert_into_bigquery(table_id: str, rows_to_insert: list[dict]) -> dict:
    """
    Inserts a list of dictionary rows into a BigQuery table.
    - table_id: The full ID of the table (e.g., "project.dataset.table").
    - rows_to_insert: A list of dictionaries, where each key is a column name.
    """
    try:
        bigquery_client = bigquery.Client()
        errors = bigquery_client.insert_rows_json(table_id, rows_to_insert)
        if not errors:
            return {"status": "success", "message": f"Successfully inserted {len(rows_to_insert)} rows."}
        else:
            return {"status": "error", "message": f"Encountered errors: {errors}"}
    except Exception as e:
        print(f"Error inserting rows into BigQuery: {e}")
        return {"status": "error", "message": str(e)}

bigquery_writer_tool = FunctionTool(
    func=insert_into_bigquery
)

class BigQueryWriterAgent(Agent):
    """
    Agent that takes the final output and saves it to a BigQuery table.
    """
    def __init__(self):
        super().__init__(
            name="bigquery_writer_agent",
            model=constants.MODEL,
            description="Agent to save the final analysis to a BigQuery table.",
            instruction="""
                You have received the final investment analysis in which you have full analysis and startup_id.
                Your task is to call the `insert_into_bigquery` tool to save this analysis to the 'final_deal_note' table.

                1.  **Prepare the Row**: Create a dictionary for the row. The dictionary must have a 'startup_id' key and a 'summary' key.
                    - The value for 'startup_id' comes from the "startup_id" key in your input.
                    - The value for 'summary' comes from full input you received.
                2.  **Format for Tool**: The `rows_to_insert` parameter must be a LIST containing the single dictionary you prepared.
                3.  **Set Table ID**: The `table_id` parameter must be set to "molten-enigma-472206-i4.financial_analysis.final_deal_note".
                4.  **Call the Tool**: Execute the `insert_into_bigquery` tool with the prepared parameters.
            """,
            tools=[bigquery_writer_tool],
        )

# Instantiate the BigQuery Writer Agent
bigquery_writer_agent = BigQueryWriterAgent()

# ----------------------------
# Parallel agents (post-check)
# ----------------------------
parallel_stage = ParallelAgent(
    name="parallel_analysis_stage",
    description="Run research, financial, operational, and market intelligence agents in parallel.",
    sub_agents=[
        researcher_agent,
        financial_agent,
        operational_agent,
        market_intel_agent,
    ],
)

# ----------------------------
# Sequential workflow: checker → parallel → synthesis → bigquery_writer
# ----------------------------
workflow = SequentialAgent(
    name="investment_workflow",
    description="Checker → parallel → synthesis → bigquery_writer workflow",
    sub_agents=[
        checker_agent,
        parallel_stage,
        synthesis_agent,
        bigquery_writer_agent,
    ],
)

# ----------------------------
# Top-level agent
# ----------------------------
root_agent = Agent(
    name=constants.AGENT_NAME,
    model=constants.MODEL,
    description="The Orchestrator agent managing the AI Analyst workflow.",
    instruction="""
        Your Job is to orchestrate the agents to perform the financial analysis.
        The final output of the analysis must be saved to the BigQuery table by the `bigquery_writer_agent`.
    """,
    sub_agents=[workflow],
    generate_content_config=types.GenerateContentConfig(temperature=0.2),
    output_key="final_investment_analysis",
)