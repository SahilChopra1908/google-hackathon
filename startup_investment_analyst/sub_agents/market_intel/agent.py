import os
from google.adk import Agent
from google.cloud import bigquery
from ...shared_libraries import constants
from . import prompt

market_intel_agent = Agent(name="market_intel_agent",
			model=constants.MODEL,
			description="Provides market benchmarks and competitive intel.",
			instruction=prompt.market_prompt,
			output_key="market_intel_output",
)
