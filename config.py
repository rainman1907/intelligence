WEBSITE_URL = "https://myrestaurants.site"
TIMEOUT = 10
RETRY_COUNT = 3
HEADLESS = True
MAX_WORKERS = 1
HUMAN_DELAY_RANGE = (2, 5)
# Force Turkish UI for better selector matching; adjust if needed
BROWSER_LANGUAGE = "tr-TR,tr"

# Optional: custom Chrome flags
CHROME_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]

# Optional: path to Chrome/Chromium binary; leave empty to auto-detect
CHROME_BINARY = ""
