from google.adk import Agent
from . import prompt
from ...tools import bq_connector
from ...shared_libraries import constants
from google.adk.tools import google_search
#from google.adk.tools import FunctionTool

#research_tool = FunctionTool(bq_connector.researcher_tool)

researcher_agent = Agent(
    model=constants.MODEL,
    name="researcher_agent",
    description="Collects and enriches startup data from BigQuery and public sources for investors.",
    instruction=prompt.researcher_prompt,
    tools=[google_search],
    output_key="researcher_output",
)
