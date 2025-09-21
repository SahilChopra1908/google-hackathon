# financial_agent.py
import os
from google.adk import Agent
from google.adk.tools import FunctionTool, ToolContext
from ...shared_libraries import constants
from . import prompt
#from ...tools import finance  


financial_agent = operational_agent =Agent(
   name="financial_agent",
            model=constants.MODEL,
            description="Analyzes financials: revenue, growth, valuation benchmarks.",
            instruction=prompt.financial_prompt,
            #tools=[finance.financial_tool],
            output_key="financial_output",
        )