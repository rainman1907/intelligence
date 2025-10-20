from __future__ import annotations

import json
import random
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


WAIT_SHORT = 8
WAIT_MED = 15
WAIT_LONG = 30


def _wait(driver: WebDriver, condition, timeout: int = WAIT_MED):
    return WebDriverWait(driver, timeout).until(condition)


def _sleep_jitter(min_s: float = 0.6, max_s: float = 1.8) -> None:
    time.sleep(random.uniform(min_s, max_s))


def go_to_maps_home(driver: WebDriver) -> None:
    # Force English UI to stabilize aria-labels and layout
    driver.get("https://www.google.com/maps?hl=en&gl=US")
    _sleep_jitter()


def perform_search(driver: WebDriver, query: str) -> None:
    # Navigate directly to the search results URL to avoid locale-dependent selectors
    q = quote_plus(query)
    driver.get(f"https://www.google.com/maps/search/{q}?hl=en&gl=US")
    # Wait for results feed or presence of place links as a fallback
    try:
        _wait(driver, EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]')), timeout=WAIT_LONG)
    except Exception:
        _wait(driver, EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/place/"]')),
              timeout=WAIT_LONG)


def _get_result_cards(driver: WebDriver):
    return driver.find_elements(By.CSS_SELECTOR, 'div[role="feed"] a[href*="/place/"]')


def collect_place_urls(driver: WebDriver, max_places: int = 20) -> List[str]:
    urls: List[str] = []
    seen = set()
    # Use the feed container if available, otherwise fall back to window scrolling
    try:
        container = _wait(driver, EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]')),
                          timeout=WAIT_MED)
        use_container_scroll = True
    except Exception:
        container = None
        use_container_scroll = False

    def scroll_once():
        if use_container_scroll and container is not None:
            driver.execute_script("arguments[0].scrollBy(0, arguments[0].scrollHeight);", container)
        else:
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")

    stagnant_rounds = 0
    while len(urls) < max_places and stagnant_rounds < 6:
        cards = _get_result_cards(driver)
        new = 0
        for c in cards:
            href = c.get_attribute("href")
            if not href:
                continue
            if "/place/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)
            new += 1
            if len(urls) >= max_places:
                break
        if new == 0:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        scroll_once()
        _sleep_jitter(0.4, 1.2)
    return urls[:max_places]


def _text_or_empty(driver: WebDriver, selectors: List[str]) -> str:
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            txt = el.text.strip()
            if txt:
                return txt
        except Exception:
            continue
    return ""


def _href_or_empty(driver: WebDriver, selectors: List[str]) -> str:
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            href = el.get_attribute("href") or ""
            if href:
                return href
        except Exception:
            continue
    return ""


def _img_src_or_empty(driver: WebDriver, selectors: List[str]) -> str:
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            src = el.get_attribute("src") or el.get_attribute("srcset") or ""
            if src:
                return src
        except Exception:
            continue
    return ""


def open_reviews_panel(driver: WebDriver) -> None:
    # Try multiple selectors to open the reviews list
    candidates = [
        'button[aria-label*="reviews"]',
        'a[aria-label*="reviews"]',
        'button[aria-label*="review"]',
        'a[href*="/reviews"]',
    ]
    for sel in candidates:
        try:
            el = _wait(driver, EC.element_to_be_clickable((By.CSS_SELECTOR, sel)), timeout=WAIT_SHORT)
            el.click()
            _sleep_jitter(0.6, 1.3)
            return
        except Exception:
            continue


def collect_latest_comments(driver: WebDriver, limit: int = 10) -> List[str]:
    comments: List[str] = []
    try:
        # Reviews list typically uses a scrollable container
        panel_candidates = driver.find_elements(By.CSS_SELECTOR, 'div[aria-label*="Reviews"], div[role="region"]')
        panel = panel_candidates[0] if panel_candidates else driver.find_element(By.TAG_NAME, "body")
    except Exception:
        panel = driver.find_element(By.TAG_NAME, "body")

    stagnant_rounds = 0
    while len(comments) < limit and stagnant_rounds < 6:
        review_text_elems = driver.find_elements(By.CSS_SELECTOR, 'div[class*="jftiEf"], div[data-review-id]')
        new = 0
        for rev in review_text_elems:
            try:
                # Common text selector for review content
                txt_el = rev.find_element(By.CSS_SELECTOR, 'span[class*="wiI7pd"], div[lang]')
                txt = txt_el.text.strip()
                if txt and txt not in comments:
                    comments.append(txt)
                    new += 1
                    if len(comments) >= limit:
                        break
            except Exception:
                continue
        if new == 0:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        panel.send_keys(Keys.END)
        _sleep_jitter(0.4, 1.1)
    return comments[:limit]


def extract_place_details(driver: WebDriver) -> Dict[str, str]:
    # Ensure details pane is visible
    _wait(driver, EC.presence_of_element_located((By.CSS_SELECTOR, "h1, h1 span")), timeout=WAIT_LONG)

    name = _text_or_empty(driver, ["h1 span", "h1"])

    rating = _text_or_empty(
        driver,
        [
            'span[aria-label*="stars"]',
            'div[role="img"][aria-label*="stars"]',
            'span[aria-live="polite"]',
        ],
    )

    reviews_text = _text_or_empty(
        driver,
        [
            'button[aria-label*="reviews"]',
            'a[aria-label*="reviews"]',
            'span[aria-label*="reviews"]',
        ],
    )

    category = _text_or_empty(driver, ["button[aria-label][jsaction][data-item-id]", "div[role='img']+span"])

    address = _text_or_empty(driver, ["button[data-item-id='address']", "div[data-item-id='address']"])
    phone = _text_or_empty(driver, ["button[data-item-id='phone']", "div[data-item-id='phone']"])
    website = _href_or_empty(driver, ["a[data-item-id='authority']", "a[aria-label*='Website']"])

    # Hours: try to expand hours if a button exists; otherwise, read visible table
    hours_text = ""
    try:
        btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label*='Hours'], button[aria-expanded]")
        btn.click()
        _sleep_jitter(0.5, 1.2)
    except Exception:
        pass
    # Extract whichever hours table/list is visible
    hours_text = _text_or_empty(
        driver,
        [
            "table[role='table']",
            "div[aria-label*='Add business hours']",
            "div[aria-label*='Hours']",
        ],
    )

    profile_image = _img_src_or_empty(
        driver,
        [
            "button[aria-label*='Open photo'] img",
            "button[aria-label*='Photo'] img",
            "img[src*='googleusercontent']",
        ],
    )

    # Reviews
    comments: List[str] = []
    try:
        open_reviews_panel(driver)
        comments = collect_latest_comments(driver, limit=10)
    except Exception:
        comments = []

    gm_url = driver.current_url

    return {
        "Name": name,
        "Rating": rating,
        "last_10_comments": json.dumps(comments, ensure_ascii=False),
        "Type/Category": category,
        "Address": address,
        "Phone": phone,
        "Website": website,
        "Working Hours": hours_text,
        "Review Count/Text": reviews_text,
        "profile_image": profile_image,
        "Google Maps URL": gm_url,
    }
