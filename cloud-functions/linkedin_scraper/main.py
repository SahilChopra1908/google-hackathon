import os
import json
import base64
import tempfile
from datetime import datetime
import time

from googleapiclient.discovery import build
from flask import jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from linkedin_scraper import Company
from google.cloud import storage
import functions_framework

# === CONFIG ===
API_KEY = "AIzaSyAAHxaDMBoVjtd-lSnkiVbVaYMhgT5udqQ"
CSE_ID = "c5498adb1e6fd4f3b"

# Optional: patched by container
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
OUTPUT_BUCKET = "agents_output_collection"

storage_client = storage.Client()

def upload_to_gcs(bucket_name: str, destination_blob_name: str, source_file_name: str):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)
    print(f"Uploaded {source_file_name} -> gs://{bucket_name}/{destination_blob_name}")

def make_chrome_driver():
    """Return a Selenium Chrome webdriver configured for headless container usage (Selenium 3.x)."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-client-side-phishing-detection")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-hang-monitor")
    chrome_options.add_argument("--disable-prompt-on-repost")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--safebrowsing-disable-auto-update")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/115 Safari/537.36"
    )

    # Point to chrome binary
    chrome_options.binary_location = CHROME_BIN

    # Selenium 3 uses `executable_path`, not `service`
    driver = webdriver.Chrome(
        executable_path=CHROMEDRIVER_PATH,
        options=chrome_options
    )
    return driver

def get_exact_linkedin(company_name, company_domain=None, max_results=5):
    """Get the exact LinkedIn URL for a company using Google Custom Search with fallbacks."""
    print(f"[DEBUG] Searching LinkedIn for company: {company_name}, domain: {company_domain}")

    service = build("customsearch", "v1", developerKey=API_KEY)

    # Build possible queries
    queries = []

    # Strict with quotes + domain
    if company_domain:
        queries.append(f'"{company_name}" site:linkedin.com/company "{company_domain}"')

    # Strict with quotes
    queries.append(f'"{company_name}" site:linkedin.com/company')

    # Relaxed without quotes
    queries.append(f'{company_name} site:linkedin.com/company')

    # Even more relaxed → allow linkedin.com without forcing /company
    queries.append(f'{company_name} site:linkedin.com')

    # Try each query until something works
    for q in queries:
        print(f"[DEBUG] Trying query: {q}")
        try:
            res = service.cse().list(q=q, cx=CSE_ID, num=max_results).execute()
        except Exception as e:
            print(f"[ERROR] Google CSE request failed for query '{q}': {e}")
            continue

        items = res.get("items", [])
        print(f"[DEBUG] Google returned {len(items)} items for query: {q}")

        for idx, item in enumerate(items, start=1):
            link = item.get("link", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            print(f"[DEBUG] Candidate #{idx} → Title: {title}, Link: {link}, Snippet: {snippet}")

            # Check if link is LinkedIn company page
            if "linkedin.com/company" in link.lower():
                # Extra check → company_name words in title or snippet
                words = company_name.lower().split()
                if any(w in title.lower() or w in snippet.lower() for w in words):
                    print(f"[DEBUG] ✅ Accepted LinkedIn URL: {link}")
                    return link
                else:
                    print(f"[DEBUG] Skipped {link} because name words not found in title/snippet")

    print("[DEBUG] ❌ No LinkedIn URL found after all queries")
    return None


    def scrape_company(company_url, email=None, password=None):
        """Scrape LinkedIn company page with Selenium only"""
        driver = make_chrome_driver()
        driver.get(company_url)
        time.sleep(5)

        data = {}

        # --- BASIC INFO ---
        try:
            data["name"] = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except:
            data["name"] = None

        try:
            data["about"] = driver.find_element(By.CSS_SELECTOR, ".core-section-container__content p").text.strip()
        except:
            data["about"] = None

        # --- WEBSITE ---
        try:
            data["website"] = driver.find_element(
                By.CSS_SELECTOR, "a[data-tracking-control-name*='website']"
            ).get_attribute("href")
        except:
            data["website"] = None

        # --- INDUSTRY ---
        try:
            data["industry"] = driver.find_element(
                By.XPATH, "//dt[contains(text(),'Industry')]/following-sibling::dd"
            ).text.strip()
        except:
            data["industry"] = None

        # --- HEADQUARTERS ---
        try:
            data["headquarters"] = driver.find_element(
                By.XPATH, "//dt[contains(text(),'Headquarters')]/following-sibling::dd"
            ).text.strip()
        except:
            data["headquarters"] = None

        # --- FOUNDED ---
        try:
            data["founded"] = driver.find_element(
                By.XPATH, "//dt[contains(text(),'Founded')]/following-sibling::dd"
            ).text.strip()
        except:
            data["founded"] = None

        # --- EMPLOYEES (Headcount) ---
        try:
            data["head_count"] = driver.find_element(
                By.XPATH, "//dt[contains(text(),'Company size')]/following-sibling::dd"
            ).text.strip()
        except:
            data["head_count"] = None

        # --- EMPLOYEES (List of employees shown in sidebar) ---
        try:
            employees_section = driver.find_elements(By.CSS_SELECTOR, ".org-people-profile-card__profile-title")
            data["employees"] = [e.text.strip() for e in employees_section if e.text.strip()]
        except:
            data["employees"] = []

        # --- SPECIALTIES ---
        try:
            specialties = driver.find_elements(By.XPATH, "//dt[contains(text(),'Specialties')]/following-sibling::dd//li")
            data["specialties"] = [s.text.strip() for s in specialties if s.text.strip()]
        except:
            data["specialties"] = None

        # --- AFFILIATED COMPANIES (if visible) ---
        try:
            affiliated = driver.find_elements(By.CSS_SELECTOR, ".org-affiliated-companies-module__company-name")
            data["affiliated_companies"] = [a.text.strip() for a in affiliated if a.text.strip()]
        except:
            data["affiliated_companies"] = []

        driver.quit()
        return data

    @functions_framework.http
    def linkedin_lookup(request):
        try:
            if request.is_json:
                payload = request.get_json()
            else:
                # fallback: try decoding raw bytes
                payload = json.loads(request.data.decode("utf-8"))

            print(f"[DEBUG] Incoming HTTP payload: {payload}")

            company_name = payload.get("company_name")
            company_domain = payload.get("company_domain") or payload.get("company_website")

            if not company_name:
                return jsonify({"error": "company_name is required"}), 400

            linkedin_url = get_exact_linkedin(company_name, company_domain)

            if not linkedin_url:
                return jsonify({"error": "LinkedIn company profile not found"}), 404

            company_data = scrape_company(
                linkedin_url,
                os.environ.get("LINKEDIN_EMAIL"),
                os.environ.get("LINKEDIN_PASSWORD")
            )
            company_data["linkedin_url"] = linkedin_url
            company_data["processed_at"] = datetime.utcnow().isoformat()

            # Save to GCS
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            local_file = os.path.join(tempfile.gettempdir(), f"linkedin_scraper_output_{ts}.json")
            with open(local_file, "w", encoding="utf-8") as f:
                json.dump(company_data, f, indent=2, ensure_ascii=False)

            gcs_path = f"{company_name}/linkedin_scraper_output_{ts}.json"
            upload_to_gcs(OUTPUT_BUCKET, gcs_path, local_file)

            return jsonify({"status": "ok", "linkedin_url": linkedin_url}), 200

        except Exception as e:
            print(f"[ERROR] {e}")
            return jsonify({"error": str(e)}), 500

