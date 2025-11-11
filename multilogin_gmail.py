"""
Multilogin Gmail Automation
---------------------------

High-level automation workflow that:
1. Loads Gmail accounts and a fixed proxy configuration from disk.
2. Starts the corresponding Multilogin profile for each account with proxy applied.
3. Attaches Selenium (undetected-chromedriver) to the profile instance.
4. Signs into Gmail, automatically solving reCAPTCHA challenges via 2Captcha.

Prerequisites:
    pip install selenium undetected-chromedriver requests python-dotenv

Environment variables can be stored in a local .env file (see config.py).
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
import undetected_chromedriver as uc
from requests import HTTPError
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import settings


ACCOUNTS_FILE = Path("accounts.txt")
PROXY_FILE = Path("proxy.txt")
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "automation.log"


def ensure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


@dataclass(frozen=True)
class ProxyConfig:
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"

    def to_multilogin_payload(self) -> Dict[str, str]:
        payload = {
            "type": self.protocol.lower(),
            "host": self.host,
            "port": self.port,
        }
        if self.username:
            payload["login"] = self.username
        if self.password:
            payload["password"] = self.password
        return payload

    def to_requests_proxy(self) -> Dict[str, str]:
        proxy_auth = ""
        if self.username and self.password:
            proxy_auth = f"{self.username}:{self.password}@"
        proxy_uri = f"{self.protocol.lower()}://{proxy_auth}{self.host}:{self.port}"
        return {"http": proxy_uri, "https": proxy_uri}


class MultiloginGmailAutomation:
    def __init__(self) -> None:
        ensure_logging()
        self.accounts = self.load_accounts()
        self.proxy = self.load_proxy()
        self.captcha_api_key = settings.captcha_api_key
        self.profile_ids = self.load_profile_ids()

        if len(self.profile_ids) < len(self.accounts):
            raise ValueError(
                f"Configured {len(self.profile_ids)} profile(s) but {len(self.accounts)} account(s) "
                "detected. Provide at least one profile per account."
            )

        self.session = requests.Session()
        if self.proxy:
            self.session.proxies.update(self.proxy.to_requests_proxy())
        if settings.multilogin_api_token:
            self.session.headers.update(
                {"Authorization": f"Bearer {settings.multilogin_api_token}"}
            )

        logging.info("Initialized automation with %d account(s).", len(self.accounts))

    @staticmethod
    def load_accounts() -> List[Tuple[str, str]]:
        if not ACCOUNTS_FILE.exists():
            raise FileNotFoundError(
                f"Missing {ACCOUNTS_FILE}. Create it with entries in the format email:password."
            )

        accounts: List[Tuple[str, str]] = []
        for idx, raw_line in enumerate(ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                logging.warning("Skipping malformed account line %d: %s", idx, raw_line)
                continue
            email, password = line.split(":", 1)
            accounts.append((email.strip(), password.strip()))

        if not accounts:
            raise ValueError("No valid accounts found in accounts.txt.")

        return accounts

    @staticmethod
    def _parse_proxy_line(line: str) -> ProxyConfig:
        protocol = "http"
        clean_line = line.strip()
        if not clean_line:
            raise ValueError("Proxy file is empty.")

        if "://" in clean_line:
            protocol, clean_line = clean_line.split("://", 1)

        parts = clean_line.split(":")
        if len(parts) not in (2, 4):
            raise ValueError(
                "Proxy must be in ip:port or ip:port:username:password format."
            )

        host, port = parts[0], parts[1]
        if len(parts) == 4:
            username, password = parts[2], parts[3]
        else:
            username = password = None

        return ProxyConfig(
            host=host,
            port=int(port),
            username=username,
            password=password,
            protocol=protocol,
        )

    def load_proxy(self) -> ProxyConfig:
        if not PROXY_FILE.exists():
            raise FileNotFoundError(
                f"Missing {PROXY_FILE}. Create it with a single proxy entry (ip:port or ip:port:user:pass)."
            )

        proxy_line = PROXY_FILE.read_text(encoding="utf-8").strip()
        proxy_config = self._parse_proxy_line(proxy_line)
        logging.info("Loaded proxy configuration %s:%s.", proxy_config.host, proxy_config.port)
        return proxy_config

    @staticmethod
    def load_profile_ids() -> List[str]:
        if settings.multilogin_profiles:
            return settings.multilogin_profiles
        raise ValueError(
            "No Multilogin profile IDs configured. Set MULTILOGIN_PROFILE_IDS in .env (comma separated)."
        )

    def apply_proxy_to_profile(self, profile_id: str) -> None:
        payload = {
            "proxy": {
                **self.proxy.to_multilogin_payload(),
                "changeIpUrl": "",
            }
        }
        url = f"{settings.multilogin_api_base}/api/v2/profile/{profile_id}"
        try:
            response = self.session.patch(url, json=payload, timeout=30)
            response.raise_for_status()
            logging.info("Updated proxy settings for profile %s.", profile_id)
        except HTTPError as exc:
            logging.error("Failed to apply proxy to profile %s: %s", profile_id, exc)
            raise

    def start_multilogin_profile(self, profile_id: str) -> Dict[str, str]:
        params = {"profileId": profile_id, "automation": "1"}
        url = f"{settings.multilogin_api_base}/api/v2/profile/start"

        logging.info("Starting Multilogin profile %s ...", profile_id)
        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "OK":
                raise RuntimeError(f"Profile start failed: {data}")
            automation_info = data["value"]["automation"]
            logging.info(
                "Profile %s started on port %s.", profile_id, automation_info.get("port")
            )
            return automation_info
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            logging.error("Unable to start profile %s: %s", profile_id, exc)
            raise

    def stop_multilogin_profile(self, profile_id: str) -> None:
        url = f"{settings.multilogin_api_base}/api/v2/profile/stop"
        params = {"profileId": profile_id}
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            logging.info("Stopped Multilogin profile %s.", profile_id)
        except requests.RequestException as exc:
            logging.warning("Failed to stop profile %s gracefully: %s", profile_id, exc)

    def solve_captcha(self, site_key: str, url: str) -> Optional[str]:
        if not self.captcha_api_key:
            logging.warning(
                "No 2Captcha API key configured. Switching to manual captcha fallback."
            )
            return self.manual_captcha_fallback(site_key, url)

        payload = {
            "key": self.captcha_api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": url,
            "json": 1,
            "soft_id": 2883,
        }

        logging.info("Submitting captcha challenge to 2Captcha.")
        try:
            submission = self.session.post(
                "http://2captcha.com/in.php", data=payload, timeout=30
            )
            submission.raise_for_status()
            result = submission.json()
        except (requests.RequestException, ValueError) as exc:
            logging.error("Captcha submission failed: %s", exc)
            return self.manual_captcha_fallback(site_key, url)

        if result.get("status") != 1:
            logging.error("Captcha submission rejected: %s", result)
            return self.manual_captcha_fallback(site_key, url)

        captcha_id = result.get("request")
        logging.info("Captcha queued (ID %s). Polling for solution ...", captcha_id)

        elapsed = 0
        while elapsed < settings.captcha_timeout:
            time.sleep(settings.captcha_poll_interval)
            elapsed += settings.captcha_poll_interval
            try:
                poll = self.session.get(
                    "http://2captcha.com/res.php",
                    params={
                        "key": self.captcha_api_key,
                        "action": "get",
                        "id": captcha_id,
                        "json": 1,
                    },
                    timeout=15,
                )
                poll.raise_for_status()
                poll_result = poll.json()
            except (requests.RequestException, ValueError) as exc:
                logging.error("Captcha polling failed: %s", exc)
                continue

            if poll_result.get("status") == 1:
                token = poll_result.get("request")
                logging.info("Captcha solved.")
                return token

            if poll_result.get("request") != "CAPCHA_NOT_READY":
                logging.error("Captcha solving error: %s", poll_result)
                break

        logging.warning("Captcha solving timed out after %s seconds.", elapsed)
        return self.manual_captcha_fallback(site_key, url)

    @staticmethod
    def manual_captcha_fallback(site_key: str, url: str) -> Optional[str]:
        message = (
            f"Manual captcha required for site key {site_key} at {url}. "
            "Open the browser window, solve the captcha, then press Enter to continue. "
            "If you have a voice assistant, the instructions have been spoken."
        )
        logging.warning(message)
        MultiloginGmailAutomation.voice_prompt(message)
        input("Press Enter after completing the captcha (or press Enter immediately to skip): ")
        return None

    @staticmethod
    def voice_prompt(message: str) -> None:
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.say(message)
            engine.runAndWait()
        except Exception:
            logging.debug("Voice prompt unavailable; pyttsx3 not installed or misconfigured.")

    def build_driver(self, port: int) -> WebDriver:
        options = ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--start-maximized")

        # Attach to the Multilogin-controlled Chrome instance.
        debugger_address = f"{settings.remote_debug_host}:{port}"
        options.debugger_address = debugger_address

        logging.info("Attaching Selenium to debugger address %s.", debugger_address)

        try:
            driver = uc.Chrome(options=options)
            driver.set_page_load_timeout(settings.page_load_timeout)
            driver.implicitly_wait(settings.implicit_wait)
            return driver
        except WebDriverException as exc:
            logging.error("Failed to attach to Multilogin browser: %s", exc)
            raise

    def handle_recaptcha_if_present(self, driver: WebDriver) -> None:
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
        if not iframes:
            return

        iframe = iframes[0]
        src = iframe.get_attribute("src")
        parsed = urlparse(src)
        site_key_candidates = parse_qs(parsed.query).get("k", [])
        site_key = site_key_candidates[0] if site_key_candidates else ""
        if not site_key:
            logging.warning("Could not determine reCAPTCHA site key.")
            return

        token = self.solve_captcha(site_key, driver.current_url)
        if not token:
            logging.info("No captcha token provided; waiting for manual completion.")
            return

        logging.info("Injecting captcha token into page.")
        driver.execute_script(
            """
            var token = arguments[0];
            var callback = arguments[1];
            var recaptchaField = document.getElementById('g-recaptcha-response');
            if (!recaptchaField) {
                recaptchaField = document.createElement('textarea');
                recaptchaField.id = 'g-recaptcha-response';
                recaptchaField.name = 'g-recaptcha-response';
                recaptchaField.style.display = 'none';
                document.body.appendChild(recaptchaField);
            }
            recaptchaField.value = token;
            if (callback && typeof callback === 'function') {
                callback(token);
            }
            """
        )
        driver.execute_script(
            """
            document.dispatchEvent(new Event('captchaFilled', { bubbles: true }));
            """
        )

    def gmail_login(self, email: str, password: str, profile_id: str) -> bool:
        logging.info("Attempting Gmail login for %s on profile %s.", email, profile_id)
        automation_info = self.start_multilogin_profile(profile_id)
        driver: Optional[WebDriver] = None

        try:
            driver = self.build_driver(automation_info["port"])
            wait = WebDriverWait(driver, settings.page_load_timeout)

            driver.get(settings.gmail_login_url)

            email_input = wait.until(
                EC.presence_of_element_located((By.ID, "identifierId"))
            )
            email_input.clear()
            email_input.send_keys(email)
            driver.find_element(By.ID, "identifierNext").click()

            self.handle_recaptcha_if_present(driver)

            password_input = wait.until(
                EC.presence_of_element_located((By.NAME, "Passwd"))
            )
            password_input.clear()
            password_input.send_keys(password)
            driver.find_element(By.ID, "passwordNext").click()

            self.handle_recaptcha_if_present(driver)

            wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'mail.google.com/mail')]")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-inbox-name]")),
                )
            )

            logging.info("Login successful for %s.", email)
            return True

        except (TimeoutException, NoSuchElementException) as exc:
            logging.error("Login failed for %s: %s", email, exc)
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logging.exception("Unexpected error during login for %s: %s", email, exc)
            return False
        finally:
            if driver:
                driver.quit()
            self.stop_multilogin_profile(profile_id)

    def run(self) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for account, profile_id in zip(self.accounts, self.profile_ids):
            email, password = account
            self.apply_proxy_to_profile(profile_id)

            attempt = 0
            success = False
            while attempt < settings.login_retries and not success:
                attempt += 1
                logging.info("Login attempt %d for %s.", attempt, email)
                success = self.gmail_login(email, password, profile_id)
                if not success and attempt < settings.login_retries:
                    logging.info("Retrying %s after short delay.", email)
                    time.sleep(5)

            result = {
                "email": email,
                "profile": profile_id,
                "status": "success" if success else "failed",
                "attempts": attempt,
            }
            results.append(result)
            logging.info("Result for %s: %s", email, result["status"])

        return results


def main() -> None:
    automation = MultiloginGmailAutomation()
    report = automation.run()
    logging.info("Automation finished. Summary:")
    for entry in report:
        logging.info(
            "Profile %s | %s | %s after %s attempt(s)",
            entry["profile"],
            entry["email"],
            entry["status"].upper(),
            entry["attempts"],
        )


if __name__ == "__main__":
    main()
