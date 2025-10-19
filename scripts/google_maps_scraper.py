#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps Scraper - Tüm Detaylar + Profil Resmi
"""

import os
import sys
import time
import json
import random
import shutil
import zipfile
import traceback
from io import BytesIO
from urllib.request import urlopen
from typing import List, Dict
from openpyxl import Workbook

from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

# ---------------------- Config ----------------------
DEBUG_DIR = "debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

ANTI_DETECT_SCRIPT = r"""
Object.defineProperty(navigator, 'webdriver', {get: () => false});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = window.chrome || { runtime: {} };
"""

# ---------------------- Helpers ----------------------
def normalize_proxy_for_seleniumwire(s: str):
    if not s:
        return None
    s = s.strip()
    if "://" in s:
        return s
    return "http://" + s

def save_debug_dump(driver, prefix="debug"):
    ts = int(time.time())
    try:
        screenshot = os.path.join(DEBUG_DIR, f"{prefix}_{ts}.png")
        driver.save_screenshot(screenshot)
        print("🖼 Screenshot:", screenshot)
    except Exception as e:
        print("⚠️ Screenshot error:", e)


def write_excel(rows: List[Dict[str, str]], output_file: str) -> None:
    if not rows:
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "results"

    # Header from union of keys to be robust
    header_keys: List[str] = [
        "name",
        "rating",
        "type",
        "address",
        "phone",
        "website",
        "hours",
        "reviews",
        "profile_image",
    ]
    ws.append(header_keys)

    for row in rows:
        ws.append([row.get(k, "") for k in header_keys])

    wb.save(output_file)

# ---------------------- Search helper ----------------------
class GoogleMapsSearchHelper:
    def __init__(self, driver, implicit_wait=3):
        self.driver = driver
        try:
            self.driver.implicitly_wait(implicit_wait)
        except Exception:
            pass

    def _close_common_overlays(self):
        overlay_xpaths = [
            "//button[contains(., 'Keep using web')]",
            "//button[contains(., 'Continue')]",
            "//button[contains(., 'I agree')]",
        ]
        for xp in overlay_xpaths:
            try:
                btn = WebDriverWait(self.driver, 1.0).until(EC.element_to_be_clickable((By.XPATH, xp)))
                btn.click()
                time.sleep(0.4)
                break
            except Exception:
                continue

    def _get_search_box(self, timeout=12):
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='searchboxinput']"))
            )
            return el
        except Exception as e:
            raise e

    def _wait_for_results(self, timeout=12):
        business_selectors = [
            "//div[contains(@class, 'THOPZb')]",
            "//div[contains(@role, 'article')]",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for sel in business_selectors:
                try:
                    els = self.driver.find_elements(By.XPATH, sel)
                    if els and len(els) > 0:
                        return True
                except Exception:
                    continue
            time.sleep(0.5)
        return False

    def perform_search(self, query, wait_for_results_seconds=12):
        try:
            self._close_common_overlays()
            time.sleep(0.4)

            search_box = self._get_search_box(timeout=12)

            try:
                search_box.clear()
            except Exception:
                pass

            search_box.send_keys(query)
            time.sleep(1)

            search_box.send_keys(Keys.ENTER)

            got = self._wait_for_results(timeout=wait_for_results_seconds)
            if not got:
                print("❌ No results detected for:", query)
                return False
            print("✅ Search success for:", query)
            return True
        except Exception as e:
            print("❌ Search exception:", e)
            return False

# ---------------------- Scraper ----------------------
class GoogleMapsScraperSW:
    def __init__(self, proxies=None, headless=False):
        self.proxies = proxies or []
        self.headless = headless
        self.proxy_index = 0
        self.driver = None
        self._start_driver_with_rotation()

    def _get_next_proxy_raw(self):
        if not self.proxies:
            return None
        p = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return p

    def _build_chrome_options(self):
        opts = webdriver.ChromeOptions()
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-first-run")
        opts.add_argument("--lang=en-US")
        opts.add_argument("--window-size=1200,900")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--no-sandbox")
        if self.headless:
            opts.add_argument("--headless=new")
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(100,150)}.0.0.0 Safari/537.36"
        opts.add_argument(f"--user-agent={ua}")
        return opts

    def _download_chrome_for_testing(self) -> tuple[str, str]:
        base_dir = os.path.join(os.path.expanduser('~'), '.local', 'chrome-for-testing')
        chrome_dir = os.path.join(base_dir, 'chrome-linux64')
        driver_dir = os.path.join(base_dir, 'chromedriver-linux64')
        chrome_bin = os.path.join(chrome_dir, 'chrome')
        driver_bin = os.path.join(driver_dir, 'chromedriver')

        if os.path.isfile(chrome_bin) and os.path.isfile(driver_bin):
            return chrome_bin, driver_bin

        os.makedirs(base_dir, exist_ok=True)
        urls = {
            'chrome': 'https://storage.googleapis.com/chrome-for-testing-public/latest-stable/linux64/chrome-linux64.zip',
            'driver': 'https://storage.googleapis.com/chrome-for-testing-public/latest-stable/linux64/chromedriver-linux64.zip',
        }

        try:
            # Download and extract Chrome
            with urlopen(urls['chrome']) as resp:
                data = resp.read()
            with zipfile.ZipFile(BytesIO(data)) as zf:
                zf.extractall(base_dir)
            # Download and extract chromedriver
            with urlopen(urls['driver']) as resp:
                data = resp.read()
            with zipfile.ZipFile(BytesIO(data)) as zf:
                zf.extractall(base_dir)

            # Ensure executables
            try:
                os.chmod(chrome_bin, 0o755)
            except Exception:
                pass
            try:
                os.chmod(driver_bin, 0o755)
            except Exception:
                pass

            return chrome_bin, driver_bin
        except Exception as e:
            raise RuntimeError(f"Chrome download failed: {e}")

    def _resolve_browser_binaries(self) -> tuple[str | None, str | None]:
        # Allow overriding via env
        chrome_env = os.getenv('CHROME_BINARY')
        driver_env = os.getenv('CHROMEDRIVER_BINARY')
        if chrome_env and driver_env and os.path.isfile(chrome_env) and os.path.isfile(driver_env):
            return chrome_env, driver_env

        # Try bundled chrome-for-testing
        try:
            chrome_bin, driver_bin = self._download_chrome_for_testing()
            return chrome_bin, driver_bin
        except Exception as e:
            print(f"⚠️ Could not provision Chrome for Testing: {e}")
            return None, None

    def _start_driver(self, proxy_raw=None):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

        chrome_opts = self._build_chrome_options()
        seleniumwire_opts = {}

        if proxy_raw:
            p = normalize_proxy_for_seleniumwire(proxy_raw)
            seleniumwire_opts['proxy'] = {'http': p, 'https': p}
            print(f"🌐 Proxy: {p}")
        else:
            print("🌐 Direct connection")

        try:
            chrome_bin, driver_bin = self._resolve_browser_binaries()
            if chrome_bin:
                chrome_opts.binary_location = chrome_bin
            service = ChromeService(executable_path=driver_bin) if driver_bin else None

            if service is not None:
                self.driver = webdriver.Chrome(service=service, seleniumwire_options=seleniumwire_opts, options=chrome_opts)
            else:
                # Fallback to Selenium Manager to resolve driver
                self.driver = webdriver.Chrome(seleniumwire_options=seleniumwire_opts, options=chrome_opts)
            self.driver.set_page_load_timeout(20)

            try:
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": ANTI_DETECT_SCRIPT})
            except Exception:
                pass

            try:
                self.driver.get("https://www.google.com/maps?hl=en")
                time.sleep(3)
                return True
            except Exception:
                return False

        except Exception as e:
            print("❌ Driver start failed:", e)
            return False

    def _start_driver_with_rotation(self):
        if not self.proxies:
            self._start_driver(None)
            return

        for _ in range(min(3, len(self.proxies))):
            proxy_raw = self._get_next_proxy_raw()
            if self._start_driver(proxy_raw):
                return
        print("❌ No working proxies")

    def search_businesses(self, query, max_businesses=10):
        if not self.driver:
            print("❌ No driver")
            return []

        try:
            print(f"🔍 Searching: {query}")
            helper = GoogleMapsSearchHelper(self.driver)
            ok = helper.perform_search(query)
            if not ok:
                return []
            return self.extract_businesses_guncel(max_businesses)
        except Exception as e:
            print("❌ Search error:", e)
            return []

    # ---------------------- GÜNCELLENMİŞ FONKSİYON ----------------------
    def extract_businesses_guncel(self, max_businesses=10):
        businesses = []
        try:
            business_cards = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'THOPZb')]"))
            )
            print(f"📊 Found: {len(business_cards)} businesses")

            for i, card in enumerate(business_cards[:max_businesses]):
                try:
                    name = rating = business_type = address = phone = website = hours = reviews = profile_image = "N/A"

                    # Karttan temel bilgiler
                    try:
                        name = card.find_element(By.XPATH, ".//div[contains(@class, 'fontHeadlineSmall')]").text
                    except:
                        pass
                    try:
                        rating = card.find_element(By.XPATH, ".//span[contains(@class,'MW4etd')]").text
                    except:
                        pass

                    # Kartı tıkla -> detay sayfasına git
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", card)
                        card.click()
                        time.sleep(3)

                        # Profil resmi
                        try:
                            img_element = self.driver.find_element(By.XPATH, "//img[contains(@class,'n4Tz4d') or contains(@class,'aoRNLd')]")
                            profile_image = img_element.get_attribute('src')
                        except:
                            profile_image = "N/A"

                        # Tür/Kategori
                        try:
                            type_elements = self.driver.find_elements(By.XPATH, "//button[contains(@jsaction,'category')]")
                            if type_elements:
                                business_type = type_elements[0].text
                        except:
                            pass

                        # Adres
                        try:
                            address = self.driver.find_element(By.XPATH, "//button[@data-item-id='address']//div[contains(@class,'Io6YTe')]").text
                        except:
                            try:
                                address = self.driver.find_element(By.XPATH, "//span[contains(text(),'Address')]/following-sibling::span").text
                            except:
                                address = "N/A"

                        # Telefon
                        try:
                            phone = self.driver.find_element(By.XPATH, "//button[@data-item-id='phone']//div[contains(@class,'Io6YTe')]").text
                        except:
                            try:
                                phone = self.driver.find_element(By.XPATH, "//span[contains(text(),'Phone')]/following-sibling::span").text
                            except:
                                phone = "N/A"

                        # Website
                        try:
                            website_element = self.driver.find_element(By.XPATH, "//a[contains(@data-item-id,'authority')]")
                            website = website_element.get_attribute('href')
                        except:
                            website = "N/A"

                        # Çalışma saatleri
                        try:
                            hours_elements = self.driver.find_elements(By.XPATH, "//table[contains(@class,'WgFkxc')]/tbody/tr")
                            if hours_elements:
                                hours_list = [e.text for e in hours_elements if e.text.strip()]
                                hours = "; ".join(hours_list)
                            else:
                                hours = "N/A"
                        except:
                            hours = "N/A"

                        # Review sayısı
                        try:
                            reviews_element = self.driver.find_element(By.XPATH, "//button[contains(@aria-label,'reviews')]")
                            reviews = reviews_element.text.split()[0]
                        except:
                            reviews = "N/A"

                        # Geri dön
                        try:
                            back_button = self.driver.find_element(By.XPATH, "//button[contains(@aria-label,'Back')]")
                            back_button.click()
                        except:
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

                        time.sleep(2)

                    except Exception as e:
                        print(f"⚠️ Detay çekim hatası: {e}")

                    businesses.append({
                        'name': name,
                        'rating': rating,
                        'type': business_type,
                        'address': address,
                        'phone': phone,
                        'website': website,
                        'hours': hours,
                        'reviews': reviews,
                        'profile_image': profile_image
                    })

                    print(f"✅ {i+1}. {name} | {rating} | {phone} | {address}")

                except Exception as e:
                    print(f"❌ Business {i+1} error: {e}")
                    continue

        except Exception as e:
            print("❌ Extract error:", e)

        return businesses

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

# ---------------------- MAIN ----------------------
def main():
    print("🚀 GOOGLE MAPS SCRAPER - TÜM DETAYLAR + PROFİL RESMİ")
    proxy_file = "config/proxies.txt"

    # MANUEL SORGULAMA
    manhattan_query = "Restaurants in Manhattan, New York"

    print(f"🎯 TEK LOKASYON TEST: Manhattan")
    print(f"📍 Lokasyon: {manhattan_query}")

    # Load proxies
    proxies = []
    if os.path.exists(proxy_file):
        with open(proxy_file, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        print(f"🔒 Proxies: {len(proxies)}")
    else:
        print("ℹ️ No proxies file")

    # Headless default unless HEADLESS=0
    headless_env = os.getenv("HEADLESS", "1") != "0"
    scraper = GoogleMapsScraperSW(proxies=proxies, headless=headless_env)
    all_results = []

    try:
        # MANUEL SORGULAMA
        print(f"\n🎯 1/1 - {manhattan_query}")
        results = scraper.search_businesses(manhattan_query, max_businesses=3)
        if results:
            all_results.extend(results)
            print(f"✅ Added: {len(results)} (Total: {len(all_results)})")
        else:
            print("❌ No results")

        # Save results
        if all_results:
            output_file = "FULL_DETAILS_TEST.xlsx"
            write_excel(all_results, output_file)
            print(f"\n🎉 TEST BAŞARILI: {len(all_results)} işletme -> {output_file}")
            print("📈 Örnek veri:")
            for example in all_results[:3]:
                print(example)
        else:
            print("\n❌ No businesses collected")

    except KeyboardInterrupt:
        print("🛑 Interrupted")
    except Exception as e:
        print("❌ Test error:", e)
        traceback.print_exc()
    finally:
        scraper.close()
        print("\n👋 Test finished")

if __name__ == "__main__":
    main()
