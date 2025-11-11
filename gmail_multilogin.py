import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
import undetected_chromedriver as uc
from requests import Response
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config


class CaptchaSolveError(Exception):
    """Raised when automated CAPTCHA solving fails."""


class LoginError(Exception):
    """Raised when the Gmail login flow fails."""


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("multilogin_gmail")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(config.LOG_DIR / "automation.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


@dataclass
class Account:
    email: str
    password: str


@dataclass
class ProxySettings:
    scheme: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    @property
    def selenium_proxy_argument(self) -> str:
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def requests_proxy_dict(self) -> Dict[str, str]:
        url = self.selenium_proxy_argument
        return {"http": url, "https": url}


class MultiloginGmailAutomation:
    def __init__(self) -> None:
        self.logger = setup_logger()
        self.accounts: List[Account] = self.load_accounts()
        self.proxy: ProxySettings = self.load_proxy()
        self.captcha_api_key: str = config.TWO_CAPTCHA_API_KEY
        self.profile_ids: List[str] = config.MULTILOGIN_PROFILE_IDS
        self.api_session = requests.Session()
        self.captcha_session = requests.Session()
        if self.proxy:
            self.captcha_session.proxies.update(self.proxy.requests_proxy_dict)
        self.results: List[Dict[str, str]] = []

    def load_accounts(self) -> List[Account]:
        accounts: List[Account] = []
        if not config.ACCOUNTS_FILE.exists():
            raise FileNotFoundError(f"accounts file missing at {config.ACCOUNTS_FILE}")

        with config.ACCOUNTS_FILE.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    email, password = line.split(":", 1)
                except ValueError as exc:
                    raise ValueError(f"Invalid account line: '{line}'") from exc

                if not email or not password:
                    raise ValueError(f"Incomplete account credentials in line: '{line}'")
                accounts.append(Account(email=email.strip(), password=password.strip()))

        if not accounts:
            raise ValueError("No accounts were loaded. Please populate accounts.txt.")
        return accounts

    def load_proxy(self) -> ProxySettings:
        if not config.PROXY_FILE.exists():
            raise FileNotFoundError(f"proxy file missing at {config.PROXY_FILE}")

        with config.PROXY_FILE.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) not in (2, 4):
                    raise ValueError(
                        "Proxy line must be 'host:port' or 'host:port:username:password'"
                    )
                host, port = parts[0], parts[1]
                try:
                    port_int = int(port)
                except ValueError as exc:
                    raise ValueError(f"Invalid proxy port in line: '{line}'") from exc

                username = parts[2] if len(parts) == 4 else None
                password = parts[3] if len(parts) == 4 else None
                proxy = ProxySettings(
                    scheme=self._resolve_proxy_scheme(),
                    host=host,
                    port=port_int,
                    username=username,
                    password=password,
                )
                self.logger.info("Loaded proxy configuration for %s:%s", host, port)
                return proxy

        raise ValueError("Proxy configuration file is empty.")

    @staticmethod
    def _resolve_proxy_scheme() -> str:
        scheme = config.PROXY_TYPE.lower()
        if scheme not in {"http", "https", "socks5"}:
            raise ValueError(
                f"Unsupported PROXY_TYPE '{config.PROXY_TYPE}'. "
                "Use one of http, https, socks5."
            )
        return scheme

    def _apply_proxy_to_profile(self, profile_id: str) -> None:
        payload = {
            "network": {
                "proxy": {
                    "type": self.proxy.scheme,
                    "host": self.proxy.host,
                    "port": self.proxy.port,
                }
            }
        }
        if self.proxy.username and self.proxy.password:
            payload["network"]["proxy"]["login"] = self.proxy.username
            payload["network"]["proxy"]["password"] = self.proxy.password

        url = f"{config.MULTILOGIN_API_BASE}/api/v2/profile/{profile_id}"
        try:
            response = self.api_session.patch(url, json=payload, timeout=30)
            response.raise_for_status()
            self.logger.info(
                "Applied proxy %s:%s to profile %s",
                self.proxy.host,
                self.proxy.port,
                profile_id,
            )
        except requests.RequestException as exc:
            self.logger.warning(
                "Failed to update proxy settings for profile %s via API: %s",
                profile_id,
                exc,
            )

    def start_multilogin_profile(self, profile_id: str) -> Dict[str, str]:
        self._apply_proxy_to_profile(profile_id)
        url = f"{config.MULTILOGIN_API_BASE}/api/v2/profile/start"
        payload = {"profileId": profile_id, "automation": {"type": "selenium"}}
        try:
            response = self.api_session.post(url, json=payload, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to start Multilogin profile {profile_id}") from exc

        data = response.json()
        if data.get("status") not in {"ok", "OK"}:
            raise RuntimeError(
                f"Multilogin returned error for profile {profile_id}: {data}"
            )

        value = data.get("value", {})
        automation = value.get("automation") or value
        debugger_address = (
            automation.get("debuggerAddress")
            or automation.get("wsEndpoint")
            or automation.get("webSocketDebuggerUrl")
        )
        if debugger_address and debugger_address.startswith("ws://"):
            # Convert websocket endpoint to host:port for Selenium attachment
            debugger_address = debugger_address.replace("ws://", "").split("/")[0]
        elif not debugger_address:
            host = automation.get("host") or "127.0.0.1"
            port = automation.get("port")
            if port:
                debugger_address = f"{host}:{port}"
        if not debugger_address:
            raise RuntimeError(
                f"Unable to determine debugger address for profile {profile_id}: {data}"
            )

        self.logger.info(
            "Started profile %s with debugger address %s", profile_id, debugger_address
        )
        return {
            "profile_id": profile_id,
            "debugger_address": debugger_address,
            "automation_id": automation.get("id"),
        }

    def stop_multilogin_profile(self, profile_id: str) -> None:
        url = f"{config.MULTILOGIN_API_BASE}/api/v2/profile/stop"
        payload = {"profileId": profile_id}
        try:
            response = self.api_session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            self.logger.info("Stopped Multilogin profile %s", profile_id)
        except requests.RequestException as exc:
            self.logger.warning(
                "Failed to stop Multilogin profile %s gracefully: %s", profile_id, exc
            )

    def connect_webdriver(self, debugger_address: str) -> WebDriver:
        chrome_options = uc.ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)
        driver = uc.Chrome(options=chrome_options, use_subprocess=False)
        driver.set_page_load_timeout(config.SELENIUM_WAIT_TIMEOUT)
        return driver

    def solve_captcha(self, site_key: str, url: str) -> str:
        if not self.captcha_api_key:
            raise CaptchaSolveError("2Captcha API key is not configured.")

        payload = {
            "key": self.captcha_api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": url,
            "json": 1,
        }
        response = self._post_with_retry(
            "http://2captcha.com/in.php", payload, session=self.captcha_session
        )
        if response.get("status") != 1:
            raise CaptchaSolveError(f"2Captcha error: {response.get('request')}")

        captcha_id = response["request"]
        self.logger.info("Submitted CAPTCHA to 2Captcha (ID: %s)", captcha_id)

        poll_params = {
            "key": self.captcha_api_key,
            "action": "get",
            "id": captcha_id,
            "json": 1,
        }
        deadline = time.time() + config.CAPTCHA_TIMEOUT
        while time.time() < deadline:
            time.sleep(config.CAPTCHA_POLL_INTERVAL)
            poll_response = self._get_with_retry(
                "http://2captcha.com/res.php", poll_params, session=self.captcha_session
            )
            if poll_response.get("status") == 1:
                token = poll_response["request"]
                self.logger.info("Captcha solved via 2Captcha (ID: %s)", captcha_id)
                return token
            if poll_response.get("request") != "CAPCHA_NOT_READY":
                raise CaptchaSolveError(f"2Captcha polling error: {poll_response}")

        raise CaptchaSolveError("Captcha solving timed out.")

    def _post_with_retry(
        self,
        url: str,
        data: Dict[str, str],
        session: requests.Session,
        max_attempts: int = 3,
    ) -> Dict[str, str]:
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp: Response = session.post(url, data=data, timeout=45)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                self.logger.warning(
                    "POST attempt %d to %s failed: %s", attempt, url, exc
                )
                time.sleep(2 * attempt)
        raise CaptchaSolveError(f"Failed to call {url}: {last_exc}")

    def _get_with_retry(
        self,
        url: str,
        params: Dict[str, str],
        session: requests.Session,
        max_attempts: int = 3,
    ) -> Dict[str, str]:
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp: Response = session.get(url, params=params, timeout=45)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                self.logger.warning(
                    "GET attempt %d to %s failed: %s", attempt, url, exc
                )
                time.sleep(2 * attempt)
        raise CaptchaSolveError(f"Failed to call {url}: {last_exc}")

    def _detect_recaptcha_sitekey(self, driver: WebDriver) -> Optional[str]:
        driver.switch_to.default_content()
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
        for frame in frames:
            src = frame.get_attribute("src")
            if not src:
                continue
            if "k=" in src:
                return src.split("k=")[1].split("&")[0]

        try:
            return driver.execute_script(
                """
                const el = document.querySelector('[data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : null;
                """
            )
        except WebDriverException:
            return None

    def handle_recaptcha(self, driver: WebDriver) -> bool:
        site_key = self._detect_recaptcha_sitekey(driver)
        if not site_key:
            return False
        self.logger.info("Detected reCAPTCHA on the page. Attempting to solve.")
        try:
            token = self.solve_captcha(site_key, driver.current_url)
            driver.execute_script(
                """
                function applyToken(token) {
                    const fields = document.querySelectorAll(
                        'textarea[name="g-recaptcha-response"], input[name="g-recaptcha-response"]'
                    );
                    if (fields.length === 0) {
                        const textarea = document.createElement('textarea');
                        textarea.name = 'g-recaptcha-response';
                        textarea.style.display = 'none';
                        document.body.appendChild(textarea);
                        fields.push(textarea);
                    }
                    fields.forEach(function(field){
                        field.value = token;
                        field.innerHTML = token;
                    });
                }
                applyToken(arguments[0]);
                """
            , token)
            driver.execute_script(
                "document.dispatchEvent(new Event('captchaSolved', {bubbles: true}));"
            )
            time.sleep(3)
            self.logger.info("Applied CAPTCHA solution token.")
            return True
        except CaptchaSolveError as exc:
            self.logger.warning(
                "Automated CAPTCHA solving failed: %s. Falling back to manual/audio solution.",
                exc,
            )
            self.prompt_manual_captcha(driver)
            return True

    def prompt_manual_captcha(self, driver: WebDriver) -> None:
        self.logger.info(
            "Attempting to trigger audio CAPTCHA as fallback. Complete manually if needed."
        )
        try:
            driver.switch_to.default_content()
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
            for frame in frames:
                driver.switch_to.frame(frame)
                try:
                    audio_button = driver.find_element(By.ID, "recaptcha-audio-button")
                    audio_button.click()
                    self.logger.info(
                        "Audio CAPTCHA triggered. Please complete it manually within %s seconds.",
                        config.MANUAL_CAPTCHA_TIMEOUT,
                    )
                    break
                except NoSuchElementException:
                    driver.switch_to.default_content()
                    continue
        except WebDriverException as exc:
            self.logger.debug("Could not trigger audio CAPTCHA: %s", exc)
        finally:
            driver.switch_to.default_content()

        deadline = time.time() + config.MANUAL_CAPTCHA_TIMEOUT
        while time.time() < deadline:
            if not self._detect_recaptcha_sitekey(driver):
                self.logger.info("CAPTCHA cleared manually.")
                return
            time.sleep(2)
        raise CaptchaSolveError("Manual CAPTCHA solving timed out.")

    def gmail_login(self, email: str, password: str, profile_id: str) -> Dict[str, str]:
        attempt = 0
        last_error: Optional[str] = None
        while attempt < config.RETRY_COUNT:
            attempt += 1
            driver: Optional[WebDriver] = None
            profile_context: Optional[Dict[str, str]] = None
            try:
                self.logger.info(
                    "Starting login for %s using profile %s (attempt %d)",
                    email,
                    profile_id,
                    attempt,
                )
                profile_context = self.start_multilogin_profile(profile_id)
                driver = self.connect_webdriver(profile_context["debugger_address"])
                success = self._perform_login_flow(driver, email, password)
                if success:
                    self.logger.info(
                        "Login successful for %s using profile %s", email, profile_id
                    )
                    return {
                        "email": email,
                        "profile_id": profile_id,
                        "status": "success",
                    }
            except (LoginError, CaptchaSolveError, WebDriverException, RuntimeError) as exc:
                last_error = str(exc)
                self.logger.error(
                    "Attempt %d failed for %s (%s): %s",
                    attempt,
                    email,
                    profile_id,
                    exc,
                )
                time.sleep(5 * attempt)
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                if profile_context:
                    self.stop_multilogin_profile(profile_id)

        return {
            "email": email,
            "profile_id": profile_id,
            "status": "failed",
            "error": last_error or "Unknown error",
        }

    def _perform_login_flow(
        self, driver: WebDriver, email: str, password: str
    ) -> bool:
        driver.get("https://accounts.google.com/signin/v2/identifier?service=mail")
        wait = WebDriverWait(driver, config.SELENIUM_WAIT_TIMEOUT)

        email_input = wait.until(
            EC.visibility_of_element_located((By.ID, "identifierId"))
        )
        email_input.clear()
        email_input.send_keys(email)
        driver.find_element(By.ID, "identifierNext").click()
        time.sleep(2)

        self.handle_recaptcha(driver)

        try:
            password_input = wait.until(
                EC.visibility_of_element_located((By.NAME, "Passwd"))
            )
        except TimeoutException:
            error_message = self._collect_error(driver)
            raise LoginError(f"Password step not reached: {error_message}")

        password_input.clear()
        password_input.send_keys(password)
        driver.find_element(By.ID, "passwordNext").click()
        time.sleep(3)

        self.handle_recaptcha(driver)

        try:
            wait.until(
                lambda d: any(
                    domain in d.current_url
                    for domain in ["mail.google.com", "myaccount.google.com"]
                )
            )
            return True
        except TimeoutException:
            error_message = self._collect_error(driver)
            raise LoginError(f"Gmail login failed: {error_message}")

    @staticmethod
    def _collect_error(driver: WebDriver) -> str:
        error_selectors = [
            "div.o6cuMc",
            "div[jsname='B34EJ']",
            "div[jsname='Xb9hP']",
        ]
        for selector in error_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if text:
                        return text
            except WebDriverException:
                continue
        return "Unknown error (check logs and browser state)."

    def run(self) -> List[Dict[str, str]]:
        if not self.profile_ids:
            raise ValueError(
                "No Multilogin profile IDs configured. "
                "Set MULTILOGIN_PROFILE_IDS in your environment."
            )

        if len(self.accounts) < len(self.profile_ids):
            self.logger.warning(
                "Fewer accounts (%d) than profiles (%d). "
                "Some profiles will not be used.",
                len(self.accounts),
                len(self.profile_ids),
            )

        pairs = list(zip(self.accounts, self.profile_ids))
        if len(self.accounts) > len(self.profile_ids):
            self.logger.warning(
                "More accounts (%d) than profiles (%d). Some accounts will be skipped.",
                len(self.accounts),
                len(self.profile_ids),
            )

        for account, profile_id in pairs:
            result = self.gmail_login(account.email, account.password, profile_id)
            self.results.append(result)
            self._store_intermediate_report()

        self._store_intermediate_report()
        return self.results

    def _store_intermediate_report(self) -> None:
        with config.REPORT_PATH.open("w", encoding="utf-8") as report_file:
            json.dump(self.results, report_file, indent=2)
        self.logger.info("Report updated at %s", config.REPORT_PATH)


def main() -> None:
    automation = MultiloginGmailAutomation()
    results = automation.run()
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] != "success"]

    print("=== Gmail Login Summary ===")
    print(f"Total profiles processed: {len(results)}")
    print(f"Successful logins: {len(successes)}")
    for success in successes:
        print(f"  - {success['email']} (profile {success['profile_id']})")

    if failures:
        print(f"Failed logins: {len(failures)}")
        for failure in failures:
            print(
                f"  - {failure['email']} (profile {failure['profile_id']}): {failure.get('error')}"
            )
    else:
        print("No failures detected.")


if __name__ == "__main__":
    main()
