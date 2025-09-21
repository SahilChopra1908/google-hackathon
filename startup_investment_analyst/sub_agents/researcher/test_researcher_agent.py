import asyncio

# Absolute import within the package
from sub_agents.researcher.agent import ResearcherAgent

async def main():
    agent = ResearcherAgent()
    
    # Test with either company_name or startup_id
    company_name = "Zepto"  # example
    startup_id = ""          # leave empty if using company_name
    
    output = await agent.run(startup_id=startup_id, company_name=company_name)
    
    print("=== ResearcherAgent Test Output ===")
    print("Company Name:", output.get("company_name"))
    print("Public Sentiment:", output.get("public_sentiment"))
    print("Summary:", output.get("summary"))
    print("Top Articles:")
    for article in output.get("articles", [])[:3]:  # show top 3 articles
        print("-", article.get("title"), "|", article.get("url"))

if __name__ == "__main__":
    asyncio.run(main())
