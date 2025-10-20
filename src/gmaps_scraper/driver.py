from __future__ import annotations

import os
from typing import Optional

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options as ChromeOptions


def _add_base_chrome_args(options: ChromeOptions, headless: bool, lang: str) -> None:
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--lang={lang}")
    if headless:
        # The new headless mode is less detectable
        options.add_argument("--headless=new")


def _apply_user_data_dir(options: ChromeOptions, user_data_dir: Optional[str]) -> None:
    if user_data_dir:
        os.makedirs(user_data_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")


def _apply_proxy(options: ChromeOptions, proxy: Optional[str]) -> None:
    if not proxy:
        return
    # Accepts forms like:
    # - host:port
    # - scheme://host:port
    # - user:pass@host:port
    # - scheme://user:pass@host:port
    # For authenticated proxies, --proxy-server works but Chrome may show auth dialogs.
    # This implementation supports host:port without embedded credentials.
    # If credentials are present, we'll still set proxy-server and rely on proxy IP auth.
    if "://" in proxy:
        proxy_server = proxy
    else:
        proxy_server = f"http://{proxy}"
    options.add_argument(f"--proxy-server={proxy_server}")


def create_driver(
    proxy: Optional[str] = None,
    headless: bool = True,
    user_data_dir: Optional[str] = None,
    lang: str = "en-US",
) -> uc.Chrome:
    """Create and return an undetected Chrome WebDriver instance."""
    options = uc.ChromeOptions()
    _add_base_chrome_args(options, headless=headless, lang=lang)
    _apply_user_data_dir(options, user_data_dir)
    _apply_proxy(options, proxy)

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(2)
    return driver
