from google.adk import Agent
from ...shared_libraries import constants
from .prompt import checker_prompt
from ...tools import checker_null_fields_tool
# ...tools.checker_gcs_backfill_tool import checker_gcs_backfill_tool

checker_agent = Agent(
  name="checker_agent",
            model="gemini-2.5-flash-lite",
            description="Reads data from all the necessary tables from Bigquery and forward to the next agent.",
            instruction=checker_prompt,
            output_key="checker_output",
            tools=[checker_null_fields_tool.checker_fetch_data_tool],
        )