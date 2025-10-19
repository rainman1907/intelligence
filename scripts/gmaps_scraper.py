#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps Scraper - Tüm Detaylar + Profil Resmi
"""

import os
import time
import random
import traceback
import pandas as pd

from seleniumwire import webdriver
from selenium.webdriver.common.By import By
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


def save_debug_dump(driver, prefix: str = "debug"):
    ts = int(time.time())
    try:
        screenshot = os.path.join(DEBUG_DIR, f"{prefix}_{ts}.png")
        driver.save_screenshot(screenshot)
        print("🖼 Screenshot:", screenshot)
    except Exception as e:
        print("⚠️ Screenshot error:", e)


# ---------------------- Search helper ----------------------
class GoogleMapsSearchHelper:
    def __init__(self, driver, implicit_wait: int = 3):
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
                btn = WebDriverWait(self.driver, 1.0).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                btn.click()
                time.sleep(0.4)
                break
            except Exception:
                continue

    def _get_search_box(self, timeout: int = 12):
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='searchboxinput']"))
            )
            return el
        except Exception as e:
            raise e

    def _wait_for_results(self, timeout: int = 12) -> bool:
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

    def perform_search(self, query: str, wait_for_results_seconds: int = 12) -> bool:
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
    def __init__(self, proxies=None, headless: bool = False):
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
        # Helpful in many CI/container environments
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        if self.headless:
            opts.add_argument("--headless=new")
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(100,150)}.0.0.0 Safari/537.36"
        )
        opts.add_argument(f"--user-agent={ua}")
        return opts

    def _start_driver(self, proxy_raw=None) -> bool:
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
            self.driver = webdriver.Chrome(
                seleniumwire_options=seleniumwire_opts, options=chrome_opts
            )
            self.driver.set_page_load_timeout(20)

            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": ANTI_DETECT_SCRIPT},
                )
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

    def search_businesses(self, query: str, max_businesses: int = 10):
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
    def extract_businesses_guncel(self, max_businesses: int = 10):
        businesses = []
        try:
            business_cards = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, "//div[contains(@class, 'THOPZb')]")
                )
            )
            print(f"📊 Found: {len(business_cards)} businesses")

            for i, card in enumerate(business_cards[:max_businesses]):
                try:
                    name = rating = business_type = address = phone = website = hours = reviews = profile_image = "N/A"

                    # Karttan temel bilgiler
                    try:
                        name = card.find_element(
                            By.XPATH, ".//div[contains(@class, 'fontHeadlineSmall')]"
                        ).text
                    except Exception:
                        pass
                    try:
                        rating = card.find_element(
                            By.XPATH, ".//span[contains(@class,'MW4etd')]"
                        ).text
                    except Exception:
                        pass

                    # Kartı tıkla -> detay sayfasına git
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView(true);", card
                        )
                        card.click()
                        time.sleep(3)

                        # Profil resmi
                        try:
                            img_element = self.driver.find_element(
                                By.XPATH,
                                "//img[contains(@class,'n4Tz4d') or contains(@class,'aoRNLd')]",
                            )
                            profile_image = img_element.get_attribute('src')
                        except Exception:
                            profile_image = "N/A"

                        # Tür/Kategori
                        try:
                            type_elements = self.driver.find_elements(
                                By.XPATH, "//button[contains(@jsaction,'category')]"
                            )
                            if type_elements:
                                business_type = type_elements[0].text
                        except Exception:
                            pass

                        # Adres
                        try:
                            address = self.driver.find_element(
                                By.XPATH,
                                "//button[@data-item-id='address']//div[contains(@class,'Io6YTe')]",
                            ).text
                        except Exception:
                            try:
                                address = self.driver.find_element(
                                    By.XPATH,
                                    "//span[contains(text(),'Address')]/following-sibling::span",
                                ).text
                            except Exception:
                                address = "N/A"

                        # Telefon
                        try:
                            phone = self.driver.find_element(
                                By.XPATH,
                                "//button[@data-item-id='phone']//div[contains(@class,'Io6YTe')]",
                            ).text
                        except Exception:
                            try:
                                phone = self.driver.find_element(
                                    By.XPATH,
                                    "//span[contains(text(),'Phone')]/following-sibling::span",
                                ).text
                            except Exception:
                                phone = "N/A"

                        # Website
                        try:
                            website_element = self.driver.find_element(
                                By.XPATH, "//a[contains(@data-item-id,'authority')]"
                            )
                            website = website_element.get_attribute('href')
                        except Exception:
                            website = "N/A"

                        # Çalışma saatleri
                        try:
                            hours_elements = self.driver.find_elements(
                                By.XPATH, "//table[contains(@class,'WgFkxc')]/tbody/tr"
                            )
                            if hours_elements:
                                hours_list = [e.text for e in hours_elements if e.text.strip()]
                                hours = "; ".join(hours_list)
                            else:
                                hours = "N/A"
                        except Exception:
                            hours = "N/A"

                        # Review sayısı
                        try:
                            reviews_element = self.driver.find_element(
                                By.XPATH, "//button[contains(@aria-label,'reviews')]"
                            )
                            reviews = reviews_element.text.split()[0]
                        except Exception:
                            reviews = "N/A"

                        # Geri dön
                        try:
                            back_button = self.driver.find_element(
                                By.XPATH, "//button[contains(@aria-label,'Back')]"
                            )
                            back_button.click()
                        except Exception:
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

                        time.sleep(2)

                    except Exception as e:
                        print(f"⚠️ Detay çekim hatası: {e}")

                    businesses.append(
                        {
                            'name': name,
                            'rating': rating,
                            'type': business_type,
                            'address': address,
                            'phone': phone,
                            'website': website,
                            'hours': hours,
                            'reviews': reviews,
                            'profile_image': profile_image,
                        }
                    )

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

    # Allow HEADLESS override via env var (default keeps original: False)
    headless_env = os.getenv("HEADLESS")
    headless = False
    if headless_env is not None:
        headless = headless_env == "1" or headless_env.lower() in {"true", "yes", "on"}

    scraper = GoogleMapsScraperSW(proxies=proxies, headless=headless)
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
            df_out = pd.DataFrame(all_results)
            output_file = "FULL_DETAILS_TEST.xlsx"
            df_out.to_excel(output_file, index=False)
            print(f"\n🎉 TEST BAŞARILI: {len(all_results)} işletme -> {output_file}")
            print("📊 Excel sütunları:", df_out.columns.tolist())
            print("📈 Örnek veri:")
            print(df_out.head(3))
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
