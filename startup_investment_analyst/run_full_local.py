import asyncio
from startup_investment_analyst.sub_agents.checker.agent import checker_agent
from startup_investment_analyst.sub_agents.researcher.agent import researcher_agent
from startup_investment_analyst.sub_agents.financial.agent import financial_agent
from startup_investment_analyst.sub_agents.operational.agent import operational_agent
from startup_investment_analyst.sub_agents.market_intel.agent import market_intel_agent
from startup_investment_analyst.sub_agents.synthesis.agent import synthesis_agent

async def run_once(startup_id: str):
	# 1) checker
	checker_out = await checker_agent.run(startup_id=startup_id)

	# 2) parallel (sequential here for simplicity)
	research_out = await researcher_agent.run(startup_id=startup_id)
	financial_out = await financial_agent.run(startup_id=startup_id)
	operational_out = await operational_agent.run(startup_id=startup_id)
	market_out = await market_intel_agent.run(startup_id=startup_id)

	combined = {
		"research": research_out,
		"financial": financial_out,
		"operations": operational_out,
		"market": market_out,
	}

	# 3) synthesis
	synth_out = await synthesis_agent.run(dealnote_input=combined, startup_id=startup_id)
	return {
		"checker": checker_out,
		"combined": combined,
		"synthesis": synth_out,
	}

if __name__ == "__main__":
	import sys
	if len(sys.argv) < 2:
		print("Usage: python3 -m startup_investment_analyst.run_full_local <startup_id>")
		sys.exit(1)
	startup_id = sys.argv[1]
	res = asyncio.run(run_once(startup_id))
	from pprint import pprint
	pprint(res["synthesis"]) 