import os
import sys
from google.cloud import bigquery
from .shared_libraries import constants

# Ensure credentials are set
# if constants.SERVICE_ACCOUNT_PATH:
# 	os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)


def check_startup(startup_id: str):
	client = bigquery.Client(project=constants.PROJECT_ID)
	missing = {}
	present_tables = []

	for key, table in constants.TABLES.items():
		query = f"""
			SELECT * FROM `{constants.PROJECT_ID}.{constants.BQ_DATASET}.{table}`
			WHERE startup_id = @startup_id
			LIMIT 1
		"""
		job = client.query(query, job_config=bigquery.QueryJobConfig(
			query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
		))
		rows = [dict(r) for r in job.result()]
		if rows:
			present_tables.append(table)
			row = rows[0]
			missing_fields = [k for k, v in row.items() if v in (None, "") or (isinstance(v, list) and len(v) == 0)]
			if missing_fields:
				missing[table] = missing_fields

	return {"startup_id": startup_id, "present_tables": present_tables, "missing_fields": missing}


if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("Usage: python -m startup_investment_analyst.run_local <startup_id>")
		sys.exit(1)
	startup_id = sys.argv[1]
	result = check_startup(startup_id)
	print(result) 