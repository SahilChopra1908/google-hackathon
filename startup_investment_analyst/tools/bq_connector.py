# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License")
# ...

"""Defines tools for Researcher Agent (investor-focused research)."""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from google.cloud import bigquery
from google.adk.tools import FunctionTool, ToolContext
from ..shared_libraries import constants

# Set service account if provided
# if constants.SERVICE_ACCOUNT_PATH:
#     os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", constants.SERVICE_ACCOUNT_PATH)

# BigQuery client
try:
    bq_client = bigquery.Client(project=constants.PROJECT_ID)
except Exception as e:
    print(f"Error initializing BigQuery client: {e}")
    bq_client = None

DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}

# -----------------------
# Helper functions
# -----------------------

def _get_company_name(startup_id: str) -> str:
    if not bq_client:
        return ""
    q = f"""
        SELECT name 
        FROM `{constants.PROJECT_ID}.{constants.BQ_DATASET}.startups`
        WHERE startup_id = @startup_id LIMIT 1
    """
    job = bq_client.query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("startup_id", "STRING", startup_id)]
    ))
    rows = list(job.result())
    return rows[0]["name"] if rows else ""


def _build_queries(name: str) -> List[str]:
    name = name or "startup"
    return [
        f"{name} funding news",
        f"{name} product review",
        f"{name} competitors",
        f"{name} recent news",
        f"{name} market analysis",
        f"government guidelines for {name} domain",
    ]


def _search_duckduckgo(query: str, max_results: int = 5) -> List[Dict]:
    try:
        resp = requests.post(DUCKDUCKGO_HTML, data={"q": query}, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for res in soup.select(".result__title a"):
            title = res.get_text(strip=True)
            url = res.get("href")
            if not url:
                continue
            snippet_el = res.find_parent(".result").select_one(".result__snippet") if res.find_parent(".result") else None
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def _fetch_metadata(url: str) -> Dict:
    if not url:
        return {}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        desc = ""
        meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc.get("content").strip()
        if not desc:
            p = soup.find("p")
            desc = p.get_text(" ", strip=True)[:300] if p else ""
        return {"page_title": title, "page_description": desc}
    except Exception:
        return {}


def _categorize(articles: List[Dict]) -> Dict[str, List[Dict]]:
    cats = {"funding": [], "reviews": [], "competitors": [], "news": [], "market": []}
    for a in articles:
        text = f"{a.get('title','')} {a.get('snippet','')} {a.get('page_description','')}".lower()
        if any(k in text for k in ["funding", "raised", "seed", "series a", "series b", "invest"]):
            cats["funding"].append(a)
        elif any(k in text for k in ["review", "rating", "customer", "users say", "pros", "cons"]):
            cats["reviews"].append(a)
        elif any(k in text for k in ["competitor", "alternative", "vs ", "compare", "rival"]):
            cats["competitors"].append(a)
        elif any(k in text for k in ["market", "industry", "trend", "growth", "report"]):
            cats["market"].append(a)
        else:
            cats["news"].append(a)
    return cats


def _sentiment_from_titles(titles: List[str]) -> str:
    pos = len([t for t in titles if re.search(r"wins|growth|partnership|launch|raises|award|record", t.lower() or "")])
    neg = len([t for t in titles if re.search(r"lawsuit|decline|loss|breach|hack|cut|layoff", t.lower() or "")])
    if pos - neg > 1:
        return "positive"
    if neg - pos > 1:
        return "negative"
    return "neutral"

# -----------------------
# FunctionTool wrapper
# -----------------------

def researcher_tool(tool_context: ToolContext):
    """Main tool entry for researcher agent."""
    startup_id = tool_context.user_content.parts[0].text.strip()
    company_name = _get_company_name(startup_id) if startup_id else startup_id

    queries = _build_queries(company_name or startup_id)

    articles: List[Dict] = []
    for q in queries:
        articles.extend(_search_duckduckgo(q, max_results=4))
        time.sleep(0.5)

    seen = set()
    unique_articles = []
    for a in articles:
        u = a.get("url")
        if u and u not in seen:
            seen.add(u)
            unique_articles.append(a)

    enriched = []
    for a in unique_articles[:6]:
        meta = _fetch_metadata(a.get("url"))
        enriched.append({**a, **meta})

    categorized = _categorize(enriched)
    sentiment = _sentiment_from_titles([a.get("title", "") for a in enriched])

    return {
        "company_name": company_name or startup_id,
        "public_sentiment": sentiment,
        "articles": enriched,
        "recent_news": categorized.get("news", [])[:5],
        "funding_news": categorized.get("funding", [])[:5],
        "product_reviews": categorized.get("reviews", [])[:5],
        "competitors": categorized.get("competitors", [])[:8],
        "market_trends": categorized.get("market", [])[:5],
        "summary": f"Collected {len(enriched)} public references for {company_name or startup_id}.",
    }


# Wrap as a FunctionTool
research_tool = FunctionTool(researcher_tool)

