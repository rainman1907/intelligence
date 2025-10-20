import random
import time
from typing import List, Optional, Tuple

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import TIMEOUT, HUMAN_DELAY_RANGE


class MapsNavigator:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, TIMEOUT)

    def _human_delay(self):
        time.sleep(random.uniform(*HUMAN_DELAY_RANGE))

    def open_place(self, url: str):
        self.driver.get(url)
        self._human_delay()
        # Wait for place title or panel to appear
        try:
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'h1[aria-level="1"]')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="main"]')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[aria-label*="Yer ayrıntıları"]')),
                )
            )
        except TimeoutException:
            pass

    def click_suggest_edit(self) -> bool:
        # Try multiple selectors across locales
        candidates: List[Tuple[str, str]] = [
            ("xpath", "//button[.//span[contains(text(), 'Düzenleme önerin')]]"),
            ("xpath", "//button[contains(., 'Düzenleme önerin')]"),
            ("xpath", "//button[.//span[contains(text(), 'Suggest an edit')]]"),
            ("xpath", "//button[contains(., 'Suggest an edit')]"),
            ("css", "button[aria-label*='Düzenleme']"),
            ("css", "button[aria-label*='Suggest']"),
            ("xpath", "//div[@role='button' and .//span[contains(text(), 'Düzenleme')]]"),
            ("xpath", "//div[@role='button' and .//span[contains(text(), 'Suggest')]]"),
        ]
        for kind, sel in candidates:
            try:
                if kind == "css":
                    el = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                else:
                    el = self.wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                el.click()
                self._human_delay()
                return True
            except Exception:
                continue
        return False

    def click_details_edit_option(self) -> bool:
        # After Suggest an edit, we may need to choose 'Change name or other details'
        options: List[Tuple[str, str]] = [
            ("xpath", "//div[@role='menuitem']//span[contains(text(), 'Adı veya diğer ayrıntıları değiştir')]") ,
            ("xpath", "//div[@role='menuitem']//span[contains(text(), 'Name or other details')]") ,
            ("xpath", "//div[@role='menuitem']//span[contains(text(), 'Change name')]") ,
            ("xpath", "//button//span[contains(text(), 'Adı veya diğer')]"),
            ("xpath", "//button//span[contains(text(), 'Change name')]"),
        ]
        for kind, sel in options:
            try:
                el = self.wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                el.click()
                self._human_delay()
                return True
            except Exception:
                continue
        # Sometimes it opens directly without an intermediate menu
        return True

    def switch_to_edit_iframe_if_present(self) -> bool:
        self.driver.switch_to.default_content()
        self._human_delay()
        frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe")
        for idx, frame in enumerate(frames):
            try:
                self.driver.switch_to.frame(frame)
                # Look for a hint that we're in edit UI
                if self._is_edit_context():
                    return True
                self.driver.switch_to.default_content()
            except Exception:
                self.driver.switch_to.default_content()
                continue
        return False

    def _is_edit_context(self) -> bool:
        # Heuristics: presence of fields/buttons related to editing
        try:
            found = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Gönder')] | //*[contains(text(),'Submit')] | //*[contains(text(),'Send')] | //input[@type='url']")
            return len(found) > 0
        except Exception:
            return False
