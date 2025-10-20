import random
import time
from typing import List, Tuple

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import TIMEOUT, HUMAN_DELAY_RANGE, WEBSITE_URL


class FormFiller:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, TIMEOUT)

    def _human_delay(self):
        time.sleep(random.uniform(*HUMAN_DELAY_RANGE))

    def click_add_website(self) -> bool:
        candidates: List[Tuple[str, str]] = [
            ("xpath", "//span[contains(text(), 'Web sitesi ekle')]") ,
            ("xpath", "//button//*[contains(text(), 'Web sitesi ekle')]") ,
            ("xpath", "//span[contains(text(), 'Add website')]") ,
            ("xpath", "//button//*[contains(text(), 'Add website')]") ,
            ("xpath", "//div[@role='button']//span[contains(text(), 'Web sitesi') and contains(text(), 'ekle')]"),
            ("xpath", "//div[@role='button']//span[contains(text(), 'Add') and contains(text(), 'website')]") ,
        ]
        for kind, sel in candidates:
            try:
                el = self.wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                el.click()
                self._human_delay()
                return True
            except Exception:
                continue
        return False

    def fill_website_and_submit(self, website_url: str = WEBSITE_URL) -> bool:
        # Find an input that can accept a URL
        input_candidates: List[Tuple[str, str]] = [
            ("css", "input[type='url']"),
            ("xpath", "//input[@type='url']"),
            ("xpath", "//input[contains(@aria-label, 'Web sitesi')]"),
            ("xpath", "//input[contains(@aria-label, 'Website')]"),
            ("xpath", "//input[contains(@placeholder, 'Web sitesi') or contains(@placeholder,'Website')]")
        ]
        input_el = None
        for kind, sel in input_candidates:
            try:
                if kind == "css":
                    input_el = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                else:
                    input_el = self.wait.until(EC.visibility_of_element_located((By.XPATH, sel)))
                break
            except Exception:
                continue
        if input_el is None:
            return False
        input_el.clear()
        input_el.send_keys(website_url)
        self._human_delay()
        # Find and click submit button
        submit_candidates: List[Tuple[str, str]] = [
            ("xpath", "//button[.//span[contains(text(), 'Gönder')]]"),
            ("xpath", "//button[contains(., 'Gönder')]") ,
            ("xpath", "//button[.//span[contains(text(), 'Submit')]]"),
            ("xpath", "//button[contains(., 'Submit')]") ,
            ("xpath", "//button[.//span[contains(text(), 'Send')]]"),
            ("xpath", "//button[contains(., 'Send')]") ,
        ]
        for kind, sel in submit_candidates:
            try:
                btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                btn.click()
                self._human_delay()
                break
            except Exception:
                continue
        # Verify success message or close of dialog
        try:
            self.wait.until(EC.any_of(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Teşekkürler') or contains(text(), 'Thanks')]")),
                EC.invisibility_of_element_located((By.XPATH, "//button[.//span[contains(text(), 'Gönder')]]")),
            ))
            return True
        except TimeoutException:
            return False
