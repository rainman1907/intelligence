import concurrent.futures
import glob
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import (
    WEBSITE_URL,
    TIMEOUT,
    RETRY_COUNT,
    HEADLESS,
    MAX_WORKERS,
    HUMAN_DELAY_RANGE,
    CHROME_ARGS,
    BROWSER_LANGUAGE,
)
from cookie_manager import CookieManager
from maps_navigator import MapsNavigator
from form_filler import FormFiller


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def _create_driver() -> webdriver.Chrome:
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    if BROWSER_LANGUAGE:
        opts.add_argument(f"--lang={BROWSER_LANGUAGE}")
    for arg in CHROME_ARGS:
        opts.add_argument(arg)
    # Stable window size
    opts.add_argument("--window-size=1366,900")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(max(30, TIMEOUT * 3))
    return driver


def _human_delay():
    time.sleep(random.uniform(*HUMAN_DELAY_RANGE))


@dataclass
class RunResult:
    account: str
    link: str
    success: bool
    error: Optional[str] = None


def process_link_with_account(account_file: str, maps_link: str) -> RunResult:
    account = os.path.splitext(os.path.basename(account_file))[0]
    driver = None
    try:
        driver = _create_driver()
        # Login with cookies
        logged_in = CookieManager.login_with_cookies(driver, account_file)
        if not logged_in:
            return RunResult(account, maps_link, False, "Oturum açılamadı (cookie geçersiz)")
        _human_delay()

        # Navigate to the place
        nav = MapsNavigator(driver)
        nav.open_place(maps_link)
        _human_delay()

        # Open suggest edit
        if not nav.click_suggest_edit():
            return RunResult(account, maps_link, False, "'Düzenleme önerin' bulunamadı")
        _human_delay()

        # Choose details edit option if needed
        nav.click_details_edit_option()
        _human_delay()

        # Switch to iframe if present
        nav.switch_to_edit_iframe_if_present()
        _human_delay()

        # Fill website and submit
        filler = FormFiller(driver)
        # Sometimes we must click 'Add website' first
        filler.click_add_website()
        _human_delay()

        ok = filler.fill_website_and_submit(WEBSITE_URL)
        if not ok:
            return RunResult(account, maps_link, False, "Form gönderimi başarısız")

        return RunResult(account, maps_link, True)
    except Exception as e:
        return RunResult(account, maps_link, False, str(e))
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


def process_account(account_file: str, links: List[str]) -> None:
    account = os.path.splitext(os.path.basename(account_file))[0]
    for link in links:
        # Retry mechanism per link
        last_error: Optional[str] = None
        for attempt in range(1, RETRY_COUNT + 1):
            result = process_link_with_account(account_file, link)
            if result.success:
                print(f"✅ {account} - {link} - Web sitesi başarıyla eklendi")
                break
            else:
                last_error = result.error or "Bilinmeyen hata"
                if attempt < RETRY_COUNT:
                    time.sleep(1.5 * attempt)
                else:
                    print(f"❌ {account} - {link} - Hata: {last_error}")



def read_maps_links(file_path: str) -> List[str]:
    if not os.path.exists(file_path):
        return []
    links: List[str] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            links.append(s)
    return links


def find_cookie_files(cookies_dir: str) -> List[str]:
    paths = sorted(glob.glob(os.path.join(cookies_dir, "*.json")))
    return paths


def main():
    cookies_dir = os.path.join(os.getcwd(), "cookies")
    links_file = os.path.join(os.getcwd(), "maps_links.txt")

    accounts = find_cookie_files(cookies_dir)
    links = read_maps_links(links_file)

    if not accounts:
        logging.error("'cookies/' klasöründe .json cookie dosyası bulunamadı")
        sys.exit(1)
    if not links:
        logging.error("'maps_links.txt' içinde işlenecek link bulunamadı")
        sys.exit(1)

    if MAX_WORKERS and MAX_WORKERS > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for account_file in accounts:
                futures.append(executor.submit(process_account, account_file, links))
            for fut in concurrent.futures.as_completed(futures):
                _ = fut.result()
    else:
        for account_file in accounts:
            process_account(account_file, links)


if __name__ == "__main__":
    main()
