import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ACCOUNTS_FILE = Path(os.getenv("ACCOUNTS_FILE", "accounts.txt"))
PROXY_FILE = Path(os.getenv("PROXY_FILE", "proxy.txt"))

MULTILOGIN_API_BASE = os.getenv("MULTILOGIN_API_BASE", "http://127.0.0.1:35000").rstrip("/")
MULTILOGIN_PROFILE_IDS = [
    profile_id.strip()
    for profile_id in os.getenv("MULTILOGIN_PROFILE_IDS", "").split(",")
    if profile_id.strip()
]

TWO_CAPTCHA_API_KEY = os.getenv("TWO_CAPTCHA_API_KEY", "")
PROXY_TYPE = os.getenv("PROXY_TYPE", "http").lower()
CAPTCHA_POLL_INTERVAL = int(os.getenv("CAPTCHA_POLL_INTERVAL", "5"))
CAPTCHA_TIMEOUT = int(os.getenv("CAPTCHA_TIMEOUT", "180"))
MANUAL_CAPTCHA_TIMEOUT = int(os.getenv("MANUAL_CAPTCHA_TIMEOUT", "180"))
SELENIUM_WAIT_TIMEOUT = int(os.getenv("SELENIUM_WAIT_TIMEOUT", "30"))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "3"))

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = Path(os.getenv("REPORT_PATH", LOG_DIR / "gmail_login_report.json"))
