import os
from google.adk import Agent
from ...shared_libraries import constants
from . import prompt

# if constants.SERVICE_ACCOUNT_PATH:
# 	os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

class SynthesisAgent(Agent):
	def __init__(self):
		super().__init__(
			name="synthesis_agent",
			model=constants.MODEL,
			description="Synthesizes insights into investor-ready deal note.",
			instruction=prompt.synthesis_prompt,
			output_key="synthesis_output",
		)

	async def run(self, dealnote_input: dict = None, startup_id: str = "", **kwargs):
		dealnote_input = dealnote_input or {}
		financial = dealnote_input.get("financial", {})
		operational = dealnote_input.get("operations", {})
		market = dealnote_input.get("market", {})
		research = dealnote_input.get("research", {})

		# gather scores (fallbacks)
		f_score = financial.get("investment_score") or 50
		o_score = operational.get("operational_score") or 50
		m_score = market.get("market_score") or 50
		r_score = 50

		# weights
		overall = 0.35*f_score + 0.25*o_score + 0.30*m_score + 0.10*r_score
		rec = (
			"STRONG BUY" if overall >= 85 else
			"BUY" if overall >= 70 else
			"HOLD" if overall >= 55 else
			"PASS"
		)

		summary = (
			f"Investment summary for {startup_id}:\n"
			f"- Financial score: {f_score}\n"
			f"- Operational score: {o_score}\n"
			f"- Market score: {m_score}\n"
			f"- Overall: {round(overall,1)} -> {rec}\n"
		)

		return {
			"executive_summary": summary,
			"investment_score": round(overall, 1),
			"recommendation": rec,
		}

synthesis_agent = SynthesisAgent()
