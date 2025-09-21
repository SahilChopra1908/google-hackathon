import time
import os
import vertexai
from .agent import root_agent  # update path if agent is elsewhere
from vertexai.preview import reasoning_engines
from vertexai import agent_engines

# -------------------------------
# Project configuration
# -------------------------------
PROJECT_ID = "molten-enigma-472206-i4"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://hackathon-agent-deploy4"

# Initialize Vertex AI SDK
vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=STAGING_BUCKET,
)

# -------------------------------
# Wrap your agent in an AdkApp
# -------------------------------
app = reasoning_engines.AdkApp(
    agent=root_agent,
    enable_tracing=True,
)

# -------------------------------
# Local test session
# -------------------------------
try:
    session = app.create_session(user_id="u_127")
    print("✅ Local session created:", session)

    events = list(app.stream_query(
        user_id="u_127",
        session_id=session.id,
        message="startup_id:ST002"
    ))

    print("\n--- Full Local Event Stream ---")
    for event in events:
        print(event)

    final_text_responses = [
        e for e in events
        if e.get("content", {}).get("parts", [{}])[0].get("text")
        and not e.get("content", {}).get("parts", [{}])[0].get("function_call")
    ]

    if final_text_responses:
        print("\n--- Final Local Response ---")
        print(final_text_responses[0]["content"]["parts"][0]["text"])

except Exception as e:
    print("❌ Error during local testing:", e)

# -------------------------------
# Deploy remote AgentEngine
# -------------------------------

# Optional: clear staging folder before deploy (helps avoid old artifacts)
os.system(f"gsutil rm -r {STAGING_BUCKET}/agent_engine/*")

unique_display_name = f"testing_hackathon_project_{int(time.time())}"

remote_app = agent_engines.create(
    agent_engine=app,
    display_name=unique_display_name,
    requirements=[
        "google-cloud-aiplatform[adk,agent_engines]",
        "google-cloud-bigquery",
        "google-cloud-storage",
        "cloudpickle==3.1.1",
        "pydantic==2.11.7",
        "beautifulsoup4",   # <-- add this
        "requests"          # <-- add this too if your scraper uses requests
    ],
    extra_packages=["./startup_investment_analyst"],
)


print(f"\n🚀 Deployment finished!")
print(f"Resource Name: {remote_app.resource_name}")

# -------------------------------
# Create remote session
# -------------------------------
try:
    remote_session = remote_app.create_session(user_id="u_456")
    print("\n✅ Remote session created:", remote_session)

    for event in remote_app.stream_query(
        user_id="u_456",
        session_id=remote_session["id"],
        message="ST002"
    ):
        print(event)

except Exception as e:
    print("❌ Error during remote query:", e)
    print("Tip: Run the following to debug logs:")
    print(f"gcloud ai reasoning-engines logs tail {remote_app.resource_name.split('/')[-1]} "
          f"--project {PROJECT_ID} --location {LOCATION}")