#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps Scraper - Enhanced Version with Full Business Details + Profile Images
"""

import os
import time
import random
import traceback
import pandas as pd
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------- Configuration ----------------------
@dataclass
class ScraperConfig:
    debug_dir: str = "debug"
    max_retries: int = 3
    implicit_wait: int = 3
    page_load_timeout: int = 20
    search_timeout: int = 12
    detail_timeout: int = 8
    scroll_pause: float = 1.0
    click_pause: float = 2.0

CONFIG = ScraperConfig()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create directories
os.makedirs(CONFIG.debug_dir, exist_ok=True)

# Anti-detection script
ANTI_DETECT_SCRIPT = r"""
Object.defineProperty(navigator, 'webdriver', {get: () => false});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'permissions', {
    query: () => Promise.resolve({state: 'granted'})
});
window.chrome = window.chrome || { runtime: {} };
delete navigator.__proto__.webdriver;
"""

# ---------------------- Utility Functions ----------------------
def normalize_proxy_for_seleniumwire(proxy_str: str) -> Optional[str]:
    """Normalize proxy string for selenium-wire"""
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()
    if "://" in proxy_str:
        return proxy_str
    return "http://" + proxy_str

def save_debug_screenshot(driver, prefix="debug"):
    """Save debug screenshot with timestamp"""
    timestamp = int(time.time())
    try:
        screenshot_path = os.path.join(CONFIG.debug_dir, f"{prefix}_{timestamp}.png")
        driver.save_screenshot(screenshot_path)
        logger.info(f"🖼 Screenshot saved: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        logger.warning(f"⚠️ Screenshot error: {e}")
        return None

def safe_get_text(element, default="N/A") -> str:
    """Safely get text from element"""
    try:
        text = element.text.strip()
        return text if text else default
    except Exception:
        return default

def safe_get_attribute(element, attribute: str, default="N/A") -> str:
    """Safely get attribute from element"""
    try:
        attr = element.get_attribute(attribute)
        return attr if attr else default
    except Exception:
        return default

# ---------------------- Search Helper Class ----------------------
class GoogleMapsSearchHelper:
    """Helper class for Google Maps search operations"""
    
    def __init__(self, driver, implicit_wait=CONFIG.implicit_wait):
        self.driver = driver
        self.wait = WebDriverWait(driver, CONFIG.search_timeout)
        try:
            self.driver.implicitly_wait(implicit_wait)
        except Exception:
            pass

    def _close_common_overlays(self) -> bool:
        """Close common overlays and popups"""
        overlay_selectors = [
            "//button[contains(text(), 'Keep using web')]",
            "//button[contains(text(), 'Continue')]",
            "//button[contains(text(), 'I agree')]",
            "//button[contains(text(), 'Accept all')]",
            "//button[contains(@aria-label, 'Close')]",
            "//div[contains(@class, 'VfPpkd-Bz112c-LgbsSe')]//button",
        ]
        
        for selector in overlay_selectors:
            try:
                button = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                button.click()
                time.sleep(0.5)
                logger.info(f"✅ Closed overlay: {selector}")
                return True
            except Exception:
                continue
        return False

    def _get_search_box(self, timeout=CONFIG.search_timeout):
        """Get the search input box"""
        search_selectors = [
            "//input[@id='searchboxinput']",
            "//input[@placeholder='Search Google Maps']",
            "//input[contains(@class, 'tactile-searchbox-input')]"
        ]
        
        for selector in search_selectors:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
                return element
            except Exception:
                continue
        
        raise TimeoutException("Could not find search box")

    def _wait_for_results(self, timeout=CONFIG.search_timeout) -> bool:
        """Wait for search results to appear"""
        business_selectors = [
            "//div[contains(@class, 'THOPZb')]",
            "//div[contains(@role, 'article')]",
            "//div[contains(@class, 'Nv2PK')]",
            "//div[contains(@jsaction, 'mouseover')]"
        ]
        
        end_time = time.time() + timeout
        while time.time() < end_time:
            for selector in business_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements and len(elements) > 0:
                        logger.info(f"✅ Found {len(elements)} results")
                        return True
                except Exception:
                    continue
            time.sleep(0.5)
        
        logger.warning("❌ No results found within timeout")
        return False

    def perform_search(self, query: str, wait_for_results_seconds=CONFIG.search_timeout) -> bool:
        """Perform search on Google Maps"""
        try:
            logger.info(f"🔍 Searching for: {query}")
            
            # Close any overlays first
            self._close_common_overlays()
            time.sleep(0.5)

            # Get search box and perform search
            search_box = self._get_search_box()
            
            # Clear and enter search query
            try:
                search_box.clear()
            except Exception:
                pass
            
            search_box.send_keys(query)
            time.sleep(1)
            search_box.send_keys(Keys.ENTER)

            # Wait for results
            success = self._wait_for_results(timeout=wait_for_results_seconds)
            if success:
                logger.info(f"✅ Search successful for: {query}")
            else:
                logger.error(f"❌ Search failed for: {query}")
                save_debug_screenshot(self.driver, "search_failed")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Search exception for '{query}': {e}")
            save_debug_screenshot(self.driver, "search_exception")
            return False

# ---------------------- Main Scraper Class ----------------------
class GoogleMapsScraperSW:
    """Enhanced Google Maps Scraper with selenium-wire support"""
    
    def __init__(self, proxies: List[str] = None, headless: bool = False):
        self.proxies = proxies or []
        self.headless = headless
        self.proxy_index = 0
        self.driver = None
        self.current_proxy = None
        self._initialize_driver()

    def _get_next_proxy(self) -> Optional[str]:
        """Get next proxy from the list"""
        if not self.proxies:
            return None
        proxy = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return proxy

    def _build_chrome_options(self):
        """Build Chrome options for the driver"""
        options = webdriver.ChromeOptions()
        
        # Anti-detection options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-default-apps")
        options.add_argument("--lang=en-US")
        options.add_argument("--window-size=1400,1000")
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # Random user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        ua = random.choice(user_agents)
        options.add_argument(f"--user-agent={ua}")
        
        return options

    def _create_driver(self, proxy_str: Optional[str] = None) -> bool:
        """Create a new driver instance"""
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

        chrome_options = self._build_chrome_options()
        seleniumwire_options = {}

        if proxy_str:
            normalized_proxy = normalize_proxy_for_seleniumwire(proxy_str)
            if normalized_proxy:
                seleniumwire_options['proxy'] = {
                    'http': normalized_proxy,
                    'https': normalized_proxy
                }
                self.current_proxy = normalized_proxy
                logger.info(f"🌐 Using proxy: {normalized_proxy}")
        else:
            self.current_proxy = None
            logger.info("🌐 Using direct connection")

        try:
            # Use webdriver-manager to handle ChromeDriver
            service = webdriver.chrome.service.Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(
                service=service,
                seleniumwire_options=seleniumwire_options,
                options=chrome_options
            )
            
            self.driver.set_page_load_timeout(CONFIG.page_load_timeout)
            
            # Execute anti-detection script
            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": ANTI_DETECT_SCRIPT}
                )
            except Exception as e:
                logger.warning(f"Could not execute anti-detection script: {e}")

            # Navigate to Google Maps
            self.driver.get("https://www.google.com/maps?hl=en")
            time.sleep(3)
            
            logger.info("✅ Driver created successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Driver creation failed: {e}")
            return False

    def _initialize_driver(self):
        """Initialize driver with proxy rotation"""
        if not self.proxies:
            self._create_driver(None)
            return

        # Try up to 3 proxies
        for attempt in range(min(3, len(self.proxies))):
            proxy = self._get_next_proxy()
            if self._create_driver(proxy):
                return
        
        logger.warning("❌ All proxies failed, trying direct connection")
        self._create_driver(None)

    def search_businesses(self, query: str, max_businesses: int = 10) -> List[Dict]:
        """Search for businesses and extract details"""
        if not self.driver:
            logger.error("❌ No driver available")
            return []

        try:
            logger.info(f"🔍 Searching for: {query}")
            helper = GoogleMapsSearchHelper(self.driver)
            
            if not helper.perform_search(query):
                return []
            
            return self._extract_business_details(max_businesses)
            
        except Exception as e:
            logger.error(f"❌ Search error for '{query}': {e}")
            save_debug_screenshot(self.driver, "search_error")
            return []

    def _extract_business_details(self, max_businesses: int = 10) -> List[Dict]:
        """Extract detailed business information"""
        businesses = []
        
        try:
            # Wait for business cards to load
            business_cards = WebDriverWait(self.driver, CONFIG.search_timeout).until(
                EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'THOPZb')]"))
            )
            
            logger.info(f"📊 Found {len(business_cards)} business cards")
            
            for i, card in enumerate(business_cards[:max_businesses]):
                try:
                    business_data = self._extract_single_business(card, i + 1)
                    if business_data:
                        businesses.append(business_data)
                        logger.info(f"✅ {i+1}. {business_data['name']} | {business_data['rating']} | {business_data['phone']}")
                    
                except Exception as e:
                    logger.error(f"❌ Error extracting business {i+1}: {e}")
                    continue

        except Exception as e:
            logger.error(f"❌ Extract error: {e}")
            save_debug_screenshot(self.driver, "extract_error")

        return businesses

    def _extract_single_business(self, card, index: int) -> Optional[Dict]:
        """Extract details from a single business card"""
        business_data = {
            'name': 'N/A',
            'rating': 'N/A',
            'type': 'N/A',
            'address': 'N/A',
            'phone': 'N/A',
            'website': 'N/A',
            'hours': 'N/A',
            'reviews': 'N/A',
            'profile_image': 'N/A'
        }

        try:
            # Extract basic info from card
            try:
                name_element = card.find_element(By.XPATH, ".//div[contains(@class, 'fontHeadlineSmall')]")
                business_data['name'] = safe_get_text(name_element)
            except NoSuchElementException:
                pass

            try:
                rating_element = card.find_element(By.XPATH, ".//span[contains(@class,'MW4etd')]")
                business_data['rating'] = safe_get_text(rating_element)
            except NoSuchElementException:
                pass

            # Click on the card to get detailed information
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", card)
                time.sleep(CONFIG.scroll_pause)
                card.click()
                time.sleep(CONFIG.click_pause)

                # Extract detailed information
                self._extract_detailed_info(business_data)

                # Go back to results
                self._go_back_to_results()

            except Exception as e:
                logger.warning(f"Could not get detailed info for business {index}: {e}")

        except Exception as e:
            logger.error(f"Error processing business {index}: {e}")
            return None

        return business_data

    def _extract_detailed_info(self, business_data: Dict):
        """Extract detailed information from business detail page"""
        wait = WebDriverWait(self.driver, CONFIG.detail_timeout)
        
        # Profile image
        try:
            img_selectors = [
                "//img[contains(@class,'n4Tz4d')]",
                "//img[contains(@class,'aoRNLd')]",
                "//img[contains(@class, 'Tya61d')]"
            ]
            for selector in img_selectors:
                try:
                    img_element = self.driver.find_element(By.XPATH, selector)
                    business_data['profile_image'] = safe_get_attribute(img_element, 'src')
                    break
                except NoSuchElementException:
                    continue
        except Exception:
            pass

        # Business type/category
        try:
            type_selectors = [
                "//button[contains(@jsaction,'category')]",
                "//span[contains(@class, 'YhemCb')]"
            ]
            for selector in type_selectors:
                try:
                    type_element = self.driver.find_element(By.XPATH, selector)
                    business_data['type'] = safe_get_text(type_element)
                    break
                except NoSuchElementException:
                    continue
        except Exception:
            pass

        # Address
        try:
            address_selectors = [
                "//button[@data-item-id='address']//div[contains(@class,'Io6YTe')]",
                "//div[contains(@data-item-id,'address')]//div[contains(@class,'Io6YTe')]",
                "//span[contains(text(),'Address')]/following-sibling::span"
            ]
            for selector in address_selectors:
                try:
                    address_element = self.driver.find_element(By.XPATH, selector)
                    business_data['address'] = safe_get_text(address_element)
                    break
                except NoSuchElementException:
                    continue
        except Exception:
            pass

        # Phone
        try:
            phone_selectors = [
                "//button[@data-item-id='phone']//div[contains(@class,'Io6YTe')]",
                "//div[contains(@data-item-id,'phone')]//div[contains(@class,'Io6YTe')]",
                "//span[contains(text(),'Phone')]/following-sibling::span"
            ]
            for selector in phone_selectors:
                try:
                    phone_element = self.driver.find_element(By.XPATH, selector)
                    business_data['phone'] = safe_get_text(phone_element)
                    break
                except NoSuchElementException:
                    continue
        except Exception:
            pass

        # Website
        try:
            website_selectors = [
                "//a[contains(@data-item-id,'authority')]",
                "//a[contains(@href,'http') and contains(@class,'CsEnBe')]"
            ]
            for selector in website_selectors:
                try:
                    website_element = self.driver.find_element(By.XPATH, selector)
                    business_data['website'] = safe_get_attribute(website_element, 'href')
                    break
                except NoSuchElementException:
                    continue
        except Exception:
            pass

        # Hours
        try:
            hours_elements = self.driver.find_elements(By.XPATH, "//table[contains(@class,'WgFkxc')]/tbody/tr")
            if hours_elements:
                hours_list = [safe_get_text(e) for e in hours_elements if safe_get_text(e) != 'N/A']
                business_data['hours'] = "; ".join(hours_list) if hours_list else 'N/A'
        except Exception:
            pass

        # Reviews count
        try:
            reviews_selectors = [
                "//button[contains(@aria-label,'reviews')]",
                "//span[contains(@aria-label,'reviews')]"
            ]
            for selector in reviews_selectors:
                try:
                    reviews_element = self.driver.find_element(By.XPATH, selector)
                    reviews_text = safe_get_text(reviews_element)
                    if reviews_text != 'N/A':
                        business_data['reviews'] = reviews_text.split()[0]
                        break
                except NoSuchElementException:
                    continue
        except Exception:
            pass

    def _go_back_to_results(self):
        """Navigate back to search results"""
        try:
            back_selectors = [
                "//button[contains(@aria-label,'Back')]",
                "//button[contains(@data-value,'Back')]"
            ]
            for selector in back_selectors:
                try:
                    back_button = self.driver.find_element(By.XPATH, selector)
                    back_button.click()
                    time.sleep(CONFIG.click_pause)
                    return
                except NoSuchElementException:
                    continue
            
            # Fallback: use ESC key
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(CONFIG.click_pause)
            
        except Exception as e:
            logger.warning(f"Could not go back to results: {e}")

    def close(self):
        """Close the driver"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver closed")
        except Exception as e:
            logger.warning(f"Error closing driver: {e}")

# ---------------------- Main Function ----------------------
def main():
    """Main function to run the scraper"""
    print("🚀 GOOGLE MAPS SCRAPER - ENHANCED VERSION")
    print("=" * 50)
    
    # Configuration
    proxy_file = "config/proxies.txt"
    output_file = "google_maps_results.xlsx"
    
    # Test query
    test_query = "Restaurants in Manhattan, New York"
    max_results = 5
    
    print(f"🎯 Test Query: {test_query}")
    print(f"📊 Max Results: {max_results}")
    print("-" * 50)

    # Load proxies
    proxies = []
    if os.path.exists(proxy_file):
        try:
            with open(proxy_file, 'r', encoding='utf-8') as f:
                proxies = [
                    line.strip() for line in f 
                    if line.strip() and not line.strip().startswith("#")
                ]
            logger.info(f"🔒 Loaded {len(proxies)} proxies")
        except Exception as e:
            logger.warning(f"Could not load proxies: {e}")
    else:
        logger.info("ℹ️ No proxy file found, using direct connection")

    # Initialize scraper
    scraper = GoogleMapsScraperSW(proxies=proxies, headless=False)
    all_results = []

    try:
        # Perform search
        logger.info(f"\n🔍 Starting search: {test_query}")
        results = scraper.search_businesses(test_query, max_businesses=max_results)
        
        if results:
            all_results.extend(results)
            logger.info(f"✅ Successfully scraped {len(results)} businesses")
            
            # Save to Excel
            df = pd.DataFrame(all_results)
            df.to_excel(output_file, index=False)
            
            print(f"\n🎉 SUCCESS! Results saved to: {output_file}")
            print(f"📊 Total businesses: {len(all_results)}")
            print(f"📈 Columns: {list(df.columns)}")
            print("\n📋 Sample data:")
            print(df.head(3).to_string())
            
        else:
            logger.error("❌ No results found")
            print("❌ No businesses were scraped")

    except KeyboardInterrupt:
        logger.info("🛑 Scraping interrupted by user")
    except Exception as e:
        logger.error(f"❌ Scraping error: {e}")
        traceback.print_exc()
    finally:
        scraper.close()
        print("\n👋 Scraping completed")

if __name__ == "__main__":
    main()