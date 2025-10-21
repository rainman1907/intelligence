import sys
import csv
import re
import time
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


# -----------------------------
# Helpers (kept lightweight)
# -----------------------------

DEFAULT_WAIT_SECS = 6
SHORT_WAIT_SECS = 2.5

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def strip_pua_glyphs(text: str) -> str:
    """Remove Private Use Area glyphs such as the address pin symbol (e.g., \uf3c8).
    Keeps diacritics and normal characters intact.
    """
    if not text:
        return text
    return "".join(ch for ch in text if not (0xE000 <= ord(ch) <= 0xF8FF))


def clean_spaces(text: str) -> str:
    if not text:
        return text
    # Replace narrow no-break spaces and other odd spaces with regular space
    text = text.replace("\u202F", " ").replace("\u00A0", " ")
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip(" \t\n\r·|-")
    return text


def wait_for_any(driver, locators: List[tuple], timeout: float = DEFAULT_WAIT_SECS):
    """Try a list of locators until one is found. Returns the element or None."""
    end = time.time() + timeout
    last_exc = None
    while time.time() < end:
        for by, sel in locators:
            try:
                el = WebDriverWait(driver, SHORT_WAIT_SECS).until(
                    EC.presence_of_element_located((by, sel))
                )
                if el:
                    return el
            except Exception as e:  # noqa: BLE001
                last_exc = e
        time.sleep(0.05)
    if last_exc:
        raise last_exc
    return None


def find_first(driver, locators: List[tuple], timeout: float = SHORT_WAIT_SECS):
    for by, sel in locators:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, sel))
            )
        except TimeoutException:
            continue
    return None


def find_all(driver, locators: List[tuple], timeout: float = SHORT_WAIT_SECS):
    for by, sel in locators:
        try:
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, sel)))
            return driver.find_elements(by, sel)
        except TimeoutException:
            continue
    return []


# -----------------------------
# 1) Driver
# -----------------------------

def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,1200")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


# -----------------------------
# 2) Search
# -----------------------------

def search_places(driver: webdriver.Chrome, query: str, max_results: int = 5) -> List[webdriver.remote.webelement.WebElement]:
    driver.get("https://www.google.com/maps")

    # Search box
    search_box = WebDriverWait(driver, DEFAULT_WAIT_SECS).until(
        EC.presence_of_element_located((By.ID, "searchboxinput"))
    )
    search_box.clear()
    search_box.send_keys(query)
    search_box.send_keys(Keys.ENTER)

    # Wait for results list
    WebDriverWait(driver, DEFAULT_WAIT_SECS).until(
        EC.any_of(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']")),
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[aria-label*='Results for']")),
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='main'] a[href*='/maps/place/']")),
        )
    )

    # Try to collect result cards in the left panel. Use multiple fallbacks.
    cards = []
    card_locators = [
        (By.CSS_SELECTOR, "div[role='feed'] .Nv2PK"),  # primary card container
        (By.CSS_SELECTOR, "div[aria-label*='Results for'] .Nv2PK"),
        (By.CSS_SELECTOR, "div[role='main'] .Nv2PK"),
        (By.CSS_SELECTOR, "a[href*='/maps/place/']")  # fallback to direct links
    ]
    for by, sel in card_locators:
        try:
            WebDriverWait(driver, SHORT_WAIT_SECS).until(EC.presence_of_all_elements_located((by, sel)))
            cards = driver.find_elements(by, sel)
            if cards:
                break
        except TimeoutException:
            continue

    # Return up to max_results elements
    return cards[:max_results]


# -----------------------------
# 3) Extract Details
# -----------------------------

def extract_details(driver: webdriver.Chrome) -> Dict[str, str]:
    data = {
        "Name": "",
        "Category": "",
        "Rating": "",
        "Review Count": "",
        "Phone": "",
        "Website": "",
        "Address": "",
        "Working Hours": "",
        "Google Maps Link": driver.current_url,
    }

    # Name
    name_el = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "h1.DUwDvf"),
            (By.CSS_SELECTOR, "h1[role='heading']"),
        ],
        timeout=SHORT_WAIT_SECS,
    )
    if name_el:
        data["Name"] = clean_spaces(name_el.text)

    # Rating and Review Count
    rating_el = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "span[aria-label$='stars']"),
            (By.CSS_SELECTOR, "div[aria-label$='stars']"),
        ]
    )
    if rating_el:
        aria = rating_el.get_attribute("aria-label") or rating_el.text
        m = re.search(r"([0-9]+(?:\.[0-9])?)\s*stars", aria or "")
        if m:
            data["Rating"] = m.group(1)

    reviews_el = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "span[aria-label$='reviews']"),
            (By.CSS_SELECTOR, "button[jsaction*='pane.rating.reviews']"),
            (By.XPATH, "//span[contains(text(),'reviews') or contains(text(),'review')]"),
        ]
    )
    if reviews_el:
        txt = reviews_el.get_attribute("aria-label") or reviews_el.text
        m = re.search(r"([0-9,\.]+)\s*reviews?", txt or "", flags=re.I)
        if m:
            data["Review Count"] = m.group(1).replace(",", "")

    # Phone
    phone_el = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "button[data-item-id^='phone:']"),
            (By.CSS_SELECTOR, "a[href^='tel:']"),
            (By.XPATH, "//button[starts-with(@aria-label,'Phone:')]"),
        ]
    )
    if phone_el:
        txt = phone_el.get_attribute("aria-label") or phone_el.text
        # Normalize from aria-label like "Phone: +1 555-123-4567"
        txt = re.sub(r"^\s*Phone:\s*", "", txt or "", flags=re.I)
        data["Phone"] = clean_spaces(txt)

    # Website
    website_el = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "a[data-item-id='authority']"),
            (By.XPATH, "//a[starts-with(@aria-label,'Website:')]"),
            (By.XPATH, "//a[contains(@href,'http') and contains(@aria-label,'Website')]"),
        ]
    )
    if website_el:
        href = website_el.get_attribute("href") or ""
        data["Website"] = href.strip()

    # -------------- FIXED FIELDS --------------
    # Category (business type label)
    category_el = find_first(
        driver,
        [
            # Most stable observed
            (By.CSS_SELECTOR, "button[jsaction*='pane.rating.category']"),
            # Fallbacks around the header chip
            (By.CSS_SELECTOR, "button.DkEaL"),
            (By.XPATH, "//button[contains(@jsaction,'pane.rating.category')]"),
            # As a last resort, a span chip near rating/name
            (By.XPATH, "//div[contains(@class,'F7nice')]//span[normalize-space()][1]"),
        ]
    )
    if category_el:
        data["Category"] = clean_spaces(category_el.text)

    # Address (full, commas, no extra symbols)
    address_el = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "button[data-item-id='address']"),
            (By.XPATH, "//button[starts-with(@aria-label,'Address:')]"),
            (By.XPATH, "//button[@data-item-id='address']//div[normalize-space()]"),
        ]
    )
    if address_el:
        # Prefer aria-label for a clean value
        aria = address_el.get_attribute("aria-label") or ""
        addr = ""
        if aria.startswith("Address:"):
            addr = aria.split(":", 1)[1]
        else:
            addr = address_el.text
        addr = strip_pua_glyphs(addr)
        addr = clean_spaces(addr)
        # Remove leading words like "Copy address" if present
        addr = re.sub(r"^Copy address\s*", "", addr, flags=re.I)
        data["Address"] = addr

    # Working Hours (expand and collect 7 days)
    hours_button = find_first(
        driver,
        [
            # Primary control usually is a button with summary in aria-label
            (By.CSS_SELECTOR, "button[jsaction*='pane.hours']"),
            (By.CSS_SELECTOR, "button[aria-label*='Open']"),
            (By.CSS_SELECTOR, "button[aria-label*='Closed']"),
            (By.CSS_SELECTOR, "button[data-item-id='oh']"),
        ]
    )

    def parse_hours_from_aria(label: str) -> Optional[str]:
        if not label:
            return None
        label = clean_spaces(label)
        # Quick check for weekly content
        if any(day + ":" in label for day in DAY_NAMES):
            # Normalize separators to semicolon + space
            parts = []
            # Extract per-day segments robustly
            for day in DAY_NAMES:
                # Pattern captures "Day: ..." up to next Day or string end
                m = re.search(day + r":\s*([^;]+?)(?=(?:\s*(?:" + "|".join(DAY_NAMES) + r"))?:|$)", label)
                if m:
                    seg = f"{day}: {clean_spaces(m.group(1))}"
                    parts.append(seg)
            if parts:
                return "; ".join(parts)
        return None

    hours_text = ""
    if hours_button:
        # First try aria-label which often contains the full weekly schedule already
        aria = hours_button.get_attribute("aria-label") or ""
        parsed = parse_hours_from_aria(aria)
        if parsed:
            hours_text = parsed
        else:
            # Open the hours dialog
            try:
                driver.execute_script("arguments[0].click();", hours_button)
            except Exception:
                try:
                    hours_button.click()
                except (ElementClickInterceptedException, Exception):
                    pass

            # The dialog/panel with weekly hours
            dialog = find_first(
                driver,
                [
                    (By.CSS_SELECTOR, "div[role='dialog']"),
                    (By.CSS_SELECTOR, "div[aria-label*='Hours']"),
                    (By.XPATH, "//div[@role='dialog' or contains(@aria-label,'Hours')]"),
                ],
                timeout=DEFAULT_WAIT_SECS,
            )

            if dialog:
                # Strategy A: table rows
                rows = []
                try:
                    rows = dialog.find_elements(By.CSS_SELECTOR, "table tr")
                except Exception:
                    rows = []

                day_to_hours = {}
                if rows:
                    for tr in rows:
                        try:
                            tds = tr.find_elements(By.CSS_SELECTOR, "td")
                            if len(tds) >= 2:
                                day = clean_spaces(tds[0].text)
                                hrs = clean_spaces(tds[1].text)
                                if day in DAY_NAMES and hrs:
                                    day_to_hours[day] = hrs
                        except Exception:
                            continue
                else:
                    # Strategy B: generic row-like containers; search by day labels
                    for day in DAY_NAMES:
                        try:
                            # Find an element that exactly contains the day label
                            day_el = dialog.find_element(By.XPATH, f".//*[normalize-space(text())='{day}']")
                            # Try hours as next sibling within same row/container
                            hours_el = None
                            # 1) direct following sibling
                            try:
                                hours_el = day_el.find_element(By.XPATH, "following-sibling::*[normalize-space()][1]")
                            except NoSuchElementException:
                                hours_el = None
                            # 2) nearest ancestor row then the next text element
                            if not hours_el:
                                try:
                                    row = day_el.find_element(By.XPATH, "./ancestor::*[self::tr or @role='row' or contains(@class,'y0SKAd') or contains(@class,'G8aQO')][1]")
                                    cand = row.find_elements(By.XPATH, ".//*[normalize-space()][position()>1]")
                                    if cand:
                                        hours_el = cand[-1]
                                except Exception:
                                    hours_el = None
                            if hours_el:
                                hrs = clean_spaces(hours_el.text)
                                if hrs:
                                    day_to_hours[day] = hrs
                        except NoSuchElementException:
                            continue
                if day_to_hours:
                    hours_text = "; ".join(f"{d}: {day_to_hours.get(d, '').strip()}" for d in DAY_NAMES if d in day_to_hours)

    data["Working Hours"] = hours_text

    return data


# -----------------------------
# 4) Main
# -----------------------------

def main():
    # Usage: python final_en_v9_ultra_fix.py "pizza near boston" 5 output.csv
    query = sys.argv[1] if len(sys.argv) > 1 else "coffee near me"
    try:
        max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    except ValueError:
        max_results = 3
    out_csv = sys.argv[3] if len(sys.argv) > 3 else "output.csv"

    driver = create_driver()
    results: List[Dict[str, str]] = []

    try:
        cards = search_places(driver, query, max_results=max_results)
        for idx, card in enumerate(cards):
            t0 = time.time()
            # Click result card to open details
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            except Exception:
                pass
            try:
                driver.execute_script("arguments[0].click();", card)
            except Exception:
                try:
                    card.click()
                except Exception:
                    continue

            # Wait for place title to stabilize
            WebDriverWait(driver, DEFAULT_WAIT_SECS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1[role='heading']"))
            )

            details = extract_details(driver)
            results.append(details)

            # Performance guard: ~3s per place
            elapsed = time.time() - t0
            if elapsed < 2.2:
                time.sleep(2.2 - elapsed)

    finally:
        driver.quit()

    # Write CSV
    fieldnames = [
        "Name",
        "Category",
        "Rating",
        "Review Count",
        "Phone",
        "Website",
        "Address",
        "Working Hours",
        "Google Maps Link",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"Saved {len(results)} rows to {out_csv}")


if __name__ == "__main__":
    main()
