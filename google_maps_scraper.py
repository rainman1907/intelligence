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
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

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
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-plugins")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option('useAutomationExtension', False)
        if self.headless:
            opts.add_argument("--headless=new")
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(110,120)}.0.0.0 Safari/537.36"
        opts.add_argument(f"--user-agent={ua}")
        return opts

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
            # Use webdriver-manager to automatically handle ChromeDriver
            service = webdriver.chrome.service.Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, seleniumwire_options=seleniumwire_opts, options=chrome_opts)
            self.driver.set_page_load_timeout(30)

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

    # ---------------------- IMPROVED EXTRACTION FUNCTION ----------------------
    def extract_businesses_guncel(self, max_businesses=10):
        businesses = []
        try:
            # Multiple selectors for business cards to increase reliability
            business_selectors = [
                "//div[contains(@class, 'THOPZb')]",
                "//div[contains(@class, 'Nv2PK')]",
                "//div[@role='article']",
                "//div[contains(@jsaction, 'mouseover')]"
            ]
            
            business_cards = None
            for selector in business_selectors:
                try:
                    business_cards = WebDriverWait(self.driver, 8).until(
                        EC.presence_of_all_elements_located((By.XPATH, selector))
                    )
                    if business_cards and len(business_cards) > 0:
                        print(f"📊 Found: {len(business_cards)} businesses using selector: {selector}")
                        break
                except TimeoutException:
                    continue
            
            if not business_cards:
                print("❌ No business cards found with any selector")
                return []

            for i, card in enumerate(business_cards[:max_businesses]):
                try:
                    name = rating = business_type = address = phone = website = hours = reviews = profile_image = "N/A"

                    # Karttan temel bilgiler - multiple selectors for reliability
                    name_selectors = [
                        ".//div[contains(@class, 'fontHeadlineSmall')]",
                        ".//div[contains(@class, 'qBF1Pd')]",
                        ".//h3",
                        ".//a[contains(@class, 'hfpxzc')]"
                    ]
                    
                    for name_sel in name_selectors:
                        try:
                            name_elem = card.find_element(By.XPATH, name_sel)
                            name = name_elem.text or name_elem.get_attribute('aria-label') or "N/A"
                            if name and name != "N/A":
                                break
                        except:
                            continue
                    
                    rating_selectors = [
                        ".//span[contains(@class,'MW4etd')]",
                        ".//span[contains(@class,'yi40Hd')]",
                        ".//div[contains(@class,'F7nice')]"
                    ]
                    
                    for rating_sel in rating_selectors:
                        try:
                            rating = card.find_element(By.XPATH, rating_sel).text
                            if rating and rating != "N/A":
                                break
                        except:
                            continue

                    # Kartı tıkla -> detay sayfasına git
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", card)
                        card.click()
                        time.sleep(3)

                        # Profil resmi - multiple selectors
                        img_selectors = [
                            "//img[contains(@class,'n4Tz4d')]",
                            "//img[contains(@class,'aoRNLd')]", 
                            "//img[contains(@class,'YhP1fd')]",
                            "//div[contains(@class,'ZKCDEc')]//img",
                            "//img[contains(@src,'googleusercontent')]"
                        ]
                        
                        for img_sel in img_selectors:
                            try:
                                img_element = self.driver.find_element(By.XPATH, img_sel)
                                profile_image = img_element.get_attribute('src')
                                if profile_image and 'googleusercontent' in profile_image:
                                    break
                            except:
                                continue
                        
                        if not profile_image or profile_image == "N/A":
                            profile_image = "N/A"

                        # Tür/Kategori - multiple selectors
                        type_selectors = [
                            "//button[contains(@jsaction,'category')]",
                            "//div[contains(@class,'W4Efsd')]",
                            "//span[contains(@class,'YhemCb')]",
                            "//div[contains(@class,'fontBodyMedium')]"
                        ]
                        
                        for type_sel in type_selectors:
                            try:
                                type_elements = self.driver.find_elements(By.XPATH, type_sel)
                                if type_elements and type_elements[0].text.strip():
                                    business_type = type_elements[0].text.strip()
                                    break
                            except:
                                continue

                        # Adres - multiple selectors
                        address_selectors = [
                            "//button[@data-item-id='address']//div[contains(@class,'Io6YTe')]",
                            "//div[contains(@class,'W4Efsd')][2]",
                            "//div[contains(@class,'W4Efsd')][contains(text(),',')]",
                            "//span[contains(text(),'Address')]/following-sibling::span",
                            "//div[@data-item-id='address']",
                            "//div[contains(@class,'rogA2c')]"
                        ]
                        
                        for addr_sel in address_selectors:
                            try:
                                addr_elem = self.driver.find_element(By.XPATH, addr_sel)
                                address = addr_elem.text.strip()
                                if address and len(address) > 5:  # Basic validation
                                    break
                            except:
                                continue

                        # Telefon - multiple selectors
                        phone_selectors = [
                            "//button[@data-item-id='phone']//div[contains(@class,'Io6YTe')]",
                            "//button[contains(@aria-label,'phone')]//div[contains(@class,'Io6YTe')]",
                            "//span[contains(text(),'Phone')]/following-sibling::span",
                            "//div[@data-item-id='phone']",
                            "//a[starts-with(@href,'tel:')]"
                        ]
                        
                        for phone_sel in phone_selectors:
                            try:
                                phone_elem = self.driver.find_element(By.XPATH, phone_sel)
                                if phone_sel.endswith("tel:')]"): # For tel: links
                                    phone = phone_elem.get_attribute('href').replace('tel:', '')
                                else:
                                    phone = phone_elem.text.strip()
                                if phone and len(phone) > 5:  # Basic validation
                                    break
                            except:
                                continue

                        # Website - multiple selectors
                        website_selectors = [
                            "//a[contains(@data-item-id,'authority')]",
                            "//button[@data-item-id='authority']//div[contains(@class,'Io6YTe')]",
                            "//a[contains(@href,'http') and not contains(@href,'google')]",
                            "//div[@data-item-id='authority']"
                        ]
                        
                        for web_sel in website_selectors:
                            try:
                                web_elem = self.driver.find_element(By.XPATH, web_sel)
                                if web_elem.tag_name == 'a':
                                    website = web_elem.get_attribute('href')
                                else:
                                    website = web_elem.text.strip()
                                if website and website.startswith('http'):
                                    break
                            except:
                                continue

                        # Çalışma saatleri - multiple selectors
                        hours_selectors = [
                            "//table[contains(@class,'WgFkxc')]/tbody/tr",
                            "//div[contains(@class,'t39EBf')]",
                            "//div[contains(@aria-label,'Hours')]",
                            "//div[contains(@class,'OqCZI')]"
                        ]
                        
                        for hours_sel in hours_selectors:
                            try:
                                hours_elements = self.driver.find_elements(By.XPATH, hours_sel)
                                if hours_elements:
                                    hours_list = [e.text.strip() for e in hours_elements if e.text.strip()]
                                    if hours_list:
                                        hours = "; ".join(hours_list[:7])  # Limit to 7 days
                                        break
                            except:
                                continue

                        # Review sayısı - multiple selectors
                        reviews_selectors = [
                            "//button[contains(@aria-label,'reviews')]",
                            "//span[contains(@aria-label,'reviews')]",
                            "//div[contains(@class,'UY7F9')]",
                            "//span[contains(text(),'(') and contains(text(),')')]"
                        ]
                        
                        for rev_sel in reviews_selectors:
                            try:
                                reviews_element = self.driver.find_element(By.XPATH, rev_sel)
                                reviews_text = reviews_element.text or reviews_element.get_attribute('aria-label')
                                # Extract number from text like "(123)" or "123 reviews"
                                import re
                                numbers = re.findall(r'\d+', reviews_text)
                                if numbers:
                                    reviews = numbers[0]
                                    break
                            except:
                                continue

                        # Geri dön - multiple methods
                        back_methods = [
                            lambda: self.driver.find_element(By.XPATH, "//button[contains(@aria-label,'Back')]").click(),
                            lambda: self.driver.find_element(By.XPATH, "//button[contains(@data-value,'Back')]").click(),
                            lambda: self.driver.find_element(By.XPATH, "//button[contains(@class,'VfPpkd-icon-LgbsSe')]").click(),
                            lambda: self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE),
                            lambda: self.driver.back()
                        ]
                        
                        for method in back_methods:
                            try:
                                method()
                                time.sleep(1)
                                break
                            except:
                                continue

                        time.sleep(random.uniform(1.5, 3.0))  # Random delay

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

# ---------------------- ENHANCED MAIN FUNCTION ----------------------
def main():
    print("🚀 GOOGLE MAPS SCRAPER - ENHANCED VERSION WITH FULL DETAILS + PROFILE IMAGES")
    print("=" * 80)
    
    proxy_file = "config/proxies.txt"
    
    # Configuration options
    queries = [
        "Restaurants in Manhattan, New York",
        # Add more queries here as needed
    ]
    
    max_businesses_per_query = 5
    headless_mode = False  # Set to True for headless browsing
    
    print(f"🎯 CONFIGURATION:")
    print(f"   - Queries: {len(queries)}")
    print(f"   - Max businesses per query: {max_businesses_per_query}")
    print(f"   - Headless mode: {headless_mode}")
    print(f"   - Proxy file: {proxy_file}")
    print()

    # Load proxies
    proxies = []
    if os.path.exists(proxy_file):
        with open(proxy_file, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        print(f"🔒 Loaded {len(proxies)} proxies")
    else:
        print("ℹ️ No proxies file found - using direct connection")

    # Initialize scraper
    scraper = GoogleMapsScraperSW(proxies=proxies, headless=headless_mode)
    all_results = []
    
    start_time = time.time()

    try:
        for i, query in enumerate(queries, 1):
            print(f"\n🔍 {i}/{len(queries)} - Processing: {query}")
            print("-" * 60)
            
            results = scraper.search_businesses(query, max_businesses=max_businesses_per_query)
            
            if results:
                all_results.extend(results)
                print(f"✅ Successfully scraped {len(results)} businesses")
                print(f"📊 Total collected so far: {len(all_results)}")
                
                # Show sample of collected data
                for j, business in enumerate(results[:2], 1):
                    print(f"   {j}. {business['name']} | Rating: {business['rating']} | Phone: {business['phone']}")
                    
            else:
                print("❌ No results found for this query")
            
            # Add delay between queries to avoid rate limiting
            if i < len(queries):
                delay = random.uniform(3, 7)
                print(f"⏳ Waiting {delay:.1f}s before next query...")
                time.sleep(delay)

        # Save results
        if all_results:
            # Create timestamped filename
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"google_maps_results_{timestamp}.xlsx"
            
            df_out = pd.DataFrame(all_results)
            df_out.to_excel(output_file, index=False)
            
            # Also save as CSV for easier access
            csv_file = output_file.replace('.xlsx', '.csv')
            df_out.to_csv(csv_file, index=False, encoding='utf-8')
            
            elapsed_time = time.time() - start_time
            
            print(f"\n🎉 SCRAPING COMPLETED SUCCESSFULLY!")
            print(f"   - Total businesses collected: {len(all_results)}")
            print(f"   - Time elapsed: {elapsed_time:.1f} seconds")
            print(f"   - Excel file: {output_file}")
            print(f"   - CSV file: {csv_file}")
            print(f"\n📊 DATA SUMMARY:")
            print(f"   - Columns: {', '.join(df_out.columns.tolist())}")
            print(f"\n📈 SAMPLE DATA:")
            print(df_out.head(3).to_string(index=False))
            
            # Data quality report
            print(f"\n📉 DATA QUALITY REPORT:")
            for col in df_out.columns:
                non_na_count = df_out[df_out[col] != 'N/A'].shape[0]
                percentage = (non_na_count / len(df_out)) * 100
                print(f"   - {col}: {non_na_count}/{len(df_out)} ({percentage:.1f}%) have data")
                
        else:
            print("\n❌ No businesses were collected")
            print("   - Check your internet connection")
            print("   - Verify the search queries are valid")
            print("   - Try running without proxies")

    except KeyboardInterrupt:
        print("\n🛑 Scraping interrupted by user")
        if all_results:
            # Save partial results
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"google_maps_partial_{timestamp}.xlsx"
            pd.DataFrame(all_results).to_excel(output_file, index=False)
            print(f"   - Partial results saved to: {output_file}")
    except Exception as e:
        print(f"\n❌ Scraping error: {e}")
        print("\nFull error details:")
        traceback.print_exc()
        
        if all_results:
            # Save partial results even on error
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"google_maps_error_{timestamp}.xlsx"
            pd.DataFrame(all_results).to_excel(output_file, index=False)
            print(f"\n💾 Partial results saved to: {output_file}")
    finally:
        scraper.close()
        print("\n👋 Scraper closed. Goodbye!")


def run_custom_search(query, max_results=10, headless=True, use_proxies=True):
    """
    Convenience function to run a single custom search
    
    Args:
        query (str): Search query for Google Maps
        max_results (int): Maximum number of businesses to scrape
        headless (bool): Run browser in headless mode
        use_proxies (bool): Use proxies if available
    
    Returns:
        list: List of scraped business data
    """
    print(f"🔍 Running custom search: {query}")
    
    proxies = []
    if use_proxies and os.path.exists("config/proxies.txt"):
        with open("config/proxies.txt", 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    
    scraper = GoogleMapsScraperSW(proxies=proxies, headless=headless)
    
    try:
        results = scraper.search_businesses(query, max_businesses=max_results)
        return results
    finally:
        scraper.close()

if __name__ == "__main__":
    # Example usage:
    # main()  # Run the main scraper with predefined queries
    
    # Or run a custom search:
    # results = run_custom_search("Coffee shops in Seattle", max_results=5, headless=False)
    # print(f"Found {len(results)} results")
    
    main()