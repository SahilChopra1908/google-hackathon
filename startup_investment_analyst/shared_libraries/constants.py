MODEL = "gemini-2.5-flash"
AGENT_NAME = "startup_investment_analyst"

# Project configuration (prefer environment variables; fallback to defaults)
import os

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("PROJECT_ID", "molten-enigma-472206-i4"))
BQ_DATASET = os.getenv("BQ_DATASET", "financial_analysis")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", os.getenv("LOCATION", "us-central1"))

# Service Account Key Path (optional if running in GCP environment)
# SERVICE_ACCOUNT_PATH = os.getenv(
# 	"GOOGLE_APPLICATION_CREDENTIALS",
# 	"/home/prabhakar/Documents/google-hackathon/startup_investment_analyst/molten-enigma-472206-i4-916c106c94ee.json",
# )

# BigQuery table names
TABLES = {
	#"startups": "startups",
	"market_metrics": "market_metrics",
	"company_metrics": "company_metrics",
	"founder_metrics": "founder_metrics",
	"product_tech_metrics": "product_tech_metrics",
	#"deal_notes": "deal_notes",
}

# GCS bucket for uploaded documents (if used)
GCS_BUCKET = os.getenv("GCS_BUCKET", "company-data-ai-hackathon")
