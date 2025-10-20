from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, List, Dict, Any

from selenium.webdriver.remote.webdriver import WebDriver


def _read_json_cookies(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text())
    # Accept either a list of cookies or an export object with a "cookies" key
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError("Cookie JSON must be a list or contain a 'cookies' list")
    cookies: List[Dict[str, Any]] = []
    for c in data:
        if not isinstance(c, dict):
            continue
        # Normalize keys
        cookies.append(
            {
                "name": c.get("name") or c.get("Name"),
                "value": c.get("value") or c.get("Value"),
                "domain": c.get("domain") or c.get("Domain") or ".google.com",
                "path": c.get("path") or c.get("Path") or "/",
                "secure": bool(c.get("secure") if c.get("secure") is not None else c.get("Secure")),
                "httpOnly": bool(c.get("httpOnly") if c.get("httpOnly") is not None else c.get("HttpOnly")),
                "expiry": c.get("expiry") or c.get("Expires"),
            }
        )
    return [c for c in cookies if c.get("name") and c.get("value")]


def _read_netscape_cookies(path: Path) -> List[Dict[str, Any]]:
    cookies: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line or line.strip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, flag, path_str, secure_str, expiry, name, value = parts[:7]
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain or ".google.com",
                "path": path_str or "/",
                "secure": secure_str.upper() == "TRUE",
                "expiry": int(expiry) if expiry and expiry.isdigit() else None,
            }
        )
    return cookies


def load_cookies_from_file(path_str: str) -> List[Dict[str, Any]]:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Cookies file not found: {path}")
    text = path.read_text()[:100].lstrip()
    if text.startswith("{") or text.startswith("["):
        return _read_json_cookies(path)
    return _read_netscape_cookies(path)


def inject_cookies(driver: WebDriver, cookies: Iterable[Dict[str, Any]]) -> None:
    # Navigate to base domain so Selenium can set cookies for it
    for base in ("https://www.google.com", "https://www.google.com/maps"):
        driver.get(base)
        time.sleep(1)
        for cookie in cookies:
            try:
                cookie_dict = {
                    k: v
                    for k, v in cookie.items()
                    if k in {"name", "value", "domain", "path", "expiry", "secure", "httpOnly"}
                }
                # Selenium expects no leading dot for domain
                if cookie_dict.get("domain", "").startswith("."):
                    cookie_dict["domain"] = cookie_dict["domain"][1:]
                driver.add_cookie(cookie_dict)
            except Exception:
                # Ignore cookies that fail to set; many Google cookies are host-bound
                continue
        driver.get(base)
        time.sleep(1)
