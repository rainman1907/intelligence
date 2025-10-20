import json
import os
import random
import time
from typing import Any, Dict, List

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import TIMEOUT, HUMAN_DELAY_RANGE


class CookieManager:
    @staticmethod
    def _human_delay():
        time.sleep(random.uniform(*HUMAN_DELAY_RANGE))

    @staticmethod
    def load_cookies(cookie_file_path: str) -> List[Dict[str, Any]]:
        with open(cookie_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Handle both {"cookies": [...]} and [...] formats
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
            raise ValueError("Invalid cookie file format: expected list or {'cookies': [...]}.")
        return cookies

    @staticmethod
    def _normalize_cookie(raw: Dict[str, Any]) -> Dict[str, Any]:
        cookie: Dict[str, Any] = {
            "name": raw.get("name"),
            "value": raw.get("value"),
        }
        # Domain/path
        if raw.get("domain"):
            cookie["domain"] = raw["domain"]
        if raw.get("path"):
            cookie["path"] = raw["path"]
        # Expiry: ensure int
        expiry = raw.get("expiry") or raw.get("expirationDate")
        if expiry is not None:
            try:
                cookie["expiry"] = int(expiry)
            except Exception:
                pass
        # Flags
        if raw.get("secure") is not None:
            cookie["secure"] = bool(raw.get("secure"))
        if raw.get("httpOnly") is not None:
            cookie["httpOnly"] = bool(raw.get("httpOnly"))
        same_site = raw.get("sameSite") or raw.get("SameSite")
        if same_site:
            # Selenium expects 'Lax' | 'Strict' | 'None'
            ss = str(same_site).capitalize()
            if ss in ("Lax", "Strict", "None"):
                cookie["sameSite"] = ss
        return cookie

    @staticmethod
    def _url_for_domain(domain: str) -> str:
        d = domain.lstrip(".") if domain else "google.com"
        if "accounts.google.com" in d:
            return "https://accounts.google.com"
        if d.endswith("google.com"):
            return "https://www.google.com"
        return f"https://{d}"

    @staticmethod
    def apply_cookies(driver: WebDriver, cookies: List[Dict[str, Any]]):
        # Group cookies by domain for fewer navigations
        domain_to_cookies: Dict[str, List[Dict[str, Any]]] = {}
        for c in cookies:
            norm = CookieManager._normalize_cookie(c)
            domain = norm.get("domain") or ".google.com"
            domain_to_cookies.setdefault(domain, []).append(norm)

        for domain, group in domain_to_cookies.items():
            try:
                driver.get(CookieManager._url_for_domain(domain))
                CookieManager._human_delay()
            except Exception:
                # Continue; we'll still attempt to add cookies
                pass
            for ck in group:
                try:
                    # Selenium requires at least name/value; domain/path optional when on same domain
                    driver.add_cookie(ck)
                except Exception:
                    # Ignore cookies that fail to set; many Google cookies are protected
                    continue

    @staticmethod
    def is_logged_in(driver: WebDriver) -> bool:
        wait = WebDriverWait(driver, TIMEOUT)
        try:
            # Look for avatar/account button or absence of sign-in
            # Try common selectors across locales
            avatar_selectors = [
                (By.CSS_SELECTOR, 'a[aria-label*="Google Hesabı"]'),
                (By.CSS_SELECTOR, 'a[aria-label*="Google Account"]'),
                (By.CSS_SELECTOR, 'img[alt*="Hesap"]'),
                (By.CSS_SELECTOR, 'img[alt*="Account"]'),
            ]
            for by, sel in avatar_selectors:
                els = driver.find_elements(by, sel)
                if els:
                    return True
            # Check for sign-in presence; if visible, not logged in
            sign_in_texts = ["Oturum aç", "Oturum açın", "Sign in", "Sign In"]
            for txt in sign_in_texts:
                sign_in_candidates = driver.find_elements(By.XPATH, f"//*[contains(text(), '{txt}')]")
                if sign_in_candidates:
                    return False
            # Fallback: check cookie presence
            cookies = driver.get_cookies()
            names = {c.get("name") for c in cookies}
            # Presence of SID/HSID usually indicates signed-in session
            return any(n in names for n in ("SID", "HSID", "SSID"))
        except Exception:
            return False

    @staticmethod
    def login_with_cookies(driver: WebDriver, cookie_file_path: str) -> bool:
        cookies = CookieManager.load_cookies(cookie_file_path)
        # Prime base domain first
        driver.get("https://www.google.com")
        CookieManager._human_delay()
        CookieManager.apply_cookies(driver, cookies)
        # Now go to Maps
        driver.get("https://www.google.com/maps")
        CookieManager._human_delay()
        # Verify
        return CookieManager.is_logged_in(driver)
