# operational_agent.py
import os
from google.adk import Agent
from google.adk.tools import FunctionTool, ToolContext
from ...shared_libraries import constants
from .prompt import operational_prompt
#from ...tools import operational_tool  # your operational_tool


# Instantiate
operational_agent =Agent(
   name="operational_agent",
            model=constants.MODEL,
            description="Assesses operational strength: team size, hiring trends, ratings, funding, and risks.",
            instruction=operational_prompt,
            #tools=[operational_tool.operational_tool],
            output_key="operational_output",
        )
