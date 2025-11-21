#!/usr/bin/env python3
"""
High-performance Google Maps scraper with concurrency, proxy rotation, checkpointing,
and memory hygiene suitable for multi-day executions over very large datasets.
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import logging
import os
import queue
import random
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import psutil
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


REVIEW_COLUMNS = [f"Review_{i}" for i in range(1, 11)]
PHOTO_COLUMNS = [f"Photo_{i}" for i in range(1, 21)]


@dataclass
class ScraperConfig:
    input_path: Path
    output_path: Path
    proxies_path: Path
    checkpoint_path: Path
    thread_count: int = 9
    cleanup_interval: int = 150
    max_review_count: int = 10
    max_photo_count: int = 20
    headless: bool = True
    per_row_retry: int = 4
    page_load_timeout: int = 45
    scroll_pause: float = 1.0


class ProxyPool:
    def __init__(self, proxy_file: Path) -> None:
        if not proxy_file.exists():
            raise FileNotFoundError(f"Proxy file not found: {proxy_file}")
        with proxy_file.open("r", encoding="utf-8") as handle:
            self._proxies = [line.strip() for line in handle if line.strip()]
        if not self._proxies:
            raise ValueError("Proxy list is empty.")
        self._lock = threading.Lock()

    def pick(self) -> str:
        with self._lock:
            return random.choice(self._proxies)


class ProgressTracker:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"processed_rows": 0, "last_update": time.time()})

    def _write(self, payload: Dict) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        tmp_path.replace(self.path)

    def update(self, processed_rows: int) -> None:
        with self._lock:
            self._write({"processed_rows": processed_rows, "last_update": time.time()})

    def snapshot(self) -> Dict:
        if not self.path.exists():
            return {"processed_rows": 0, "last_update": None}
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


class OutputWriter:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not self.output_path.exists():
            with self.output_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Row_ID"] + REVIEW_COLUMNS + PHOTO_COLUMNS)

    def append_row(self, row_id: int, reviews: Sequence[str], photos: Sequence[str]) -> None:
        review_cells = list(reviews)[: len(REVIEW_COLUMNS)]
        photo_cells = list(photos)[: len(PHOTO_COLUMNS)]
        review_cells += [""] * (len(REVIEW_COLUMNS) - len(review_cells))
        photo_cells += [""] * (len(PHOTO_COLUMNS) - len(photo_cells))
        with self._lock:
            with self.output_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([row_id] + review_cells + photo_cells)

    def existing_row_ids(self) -> set:
        if not self.output_path.exists():
            return set()
        ids: set = set()
        with self.output_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for record in reader:
                try:
                    ids.add(int(record["Row_ID"]))
                except (ValueError, KeyError):
                    continue
        return ids


class GracefulShutdown:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)

    def _handle(self, signum, frame) -> None:  # type: ignore[override]
        logging.warning("Received signal %s – requesting shutdown...", signum)
        self.stop_event.set()


class GoogleMapsScraper:
    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self.proxy_pool = ProxyPool(config.proxies_path)
        self.output = OutputWriter(config.output_path)
        self.progress = ProgressTracker(config.checkpoint_path)
        self.shutdown = GracefulShutdown()
        self.row_queue: "queue.Queue[Optional[Tuple[int, Dict[str, str]]]]" = queue.Queue(
            maxsize=config.thread_count * 4
        )
        self.completed_rows: Set[int] = self.output.existing_row_ids()
        self.processed_counter = len(self.completed_rows)
        self.counter_lock = threading.Lock()

    def run(self) -> None:
        logging.info("Starting scraper with %s threads.", self.config.thread_count)
        workers = [
            threading.Thread(
                target=self._worker,
                name=f"worker-{idx+1}",
                daemon=True,
            )
            for idx in range(self.config.thread_count)
        ]
        for worker in workers:
            worker.start()

        try:
            for row_id, record in self._iter_rows():
                if self.shutdown.stop_event.is_set():
                    break
                self.row_queue.put((row_id, record))
        finally:
            for _ in workers:
                self.row_queue.put(None)
            for worker in workers:
                worker.join()
            logging.info("All workers exited.")

    def _iter_rows(self) -> Iterable[Tuple[int, Dict[str, str]]]:
        processed_ids = set(self.completed_rows)
        logging.info("Skipping %s rows already present in %s", len(processed_ids), self.config.output_path.name)
        with self.config.input_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for idx, row in enumerate(reader, start=1):
                if idx in processed_ids:
                    continue
                yield idx, row

    def _worker(self) -> None:
        thread_name = threading.current_thread().name
        driver: Optional[Chrome] = None
        tasks_since_cleanup = 0
        proxy = None

        while not self.shutdown.stop_event.is_set():
            try:
                payload = self.row_queue.get(timeout=1)
            except queue.Empty:
                continue

            if payload is None:
                self.row_queue.task_done()
                break

            row_id, record = payload

            try:
                if driver is None:
                    proxy = self.proxy_pool.pick()
                    driver = self._init_driver(proxy)
                success = self._process_row(driver, row_id, record)
                if not success:
                    logging.error("[%s] Failed to process row %s after retries.", thread_name, row_id)
            except Exception as exc:  # pylint: disable=broad-except
                logging.exception("[%s] Unhandled error on row %s: %s", thread_name, row_id, exc)
                driver = self._recycle_driver(driver)
            finally:
                tasks_since_cleanup += 1
                self.row_queue.task_done()
                if tasks_since_cleanup >= self.config.cleanup_interval:
                    logging.info("[%s] Cleanup threshold reached (%s tasks).", thread_name, tasks_since_cleanup)
                    driver = self._recycle_driver(driver)
                    tasks_since_cleanup = 0

        self._recycle_driver(driver)

    def _init_driver(self, proxy: Optional[str]) -> Chrome:
        chrome_options: Options = uc.ChromeOptions()
        chrome_options.headless = self.config.headless
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--lang=en-US")
        if proxy:
            chrome_options.add_argument(f"--proxy-server={proxy}")
        driver = uc.Chrome(options=chrome_options)
        driver.set_page_load_timeout(self.config.page_load_timeout)
        return driver

    def _recycle_driver(self, driver: Optional[Chrome]) -> Optional[Chrome]:
        if driver:
            try:
                driver.quit()
            except WebDriverException:
                pass
        self._memory_health_check()
        return None

    def _process_row(self, driver: Chrome, row_id: int, record: Dict[str, str]) -> bool:
        url = record.get("Google Maps Link")
        if not url:
            logging.warning("Row %s missing Google Maps Link.", row_id)
            return True

        for attempt in range(1, self.config.per_row_retry + 1):
            try:
                driver.get(url)
                reviews = self._extract_reviews(driver)
                photos = self._extract_photos(driver)
                self.output.append_row(row_id, reviews, photos)
                self._mark_completed(row_id)
                return True
            except TimeoutException as exc:
                logging.warning("Timeout on row %s attempt %s: %s", row_id, attempt, exc)
            except WebDriverException as exc:
                logging.warning("WebDriver error row %s attempt %s: %s", row_id, attempt, exc)
            time.sleep(2 * attempt)
            driver = self._recycle_driver(driver)
            proxy = self.proxy_pool.pick()
            driver = self._init_driver(proxy)

        return False

    def _extract_reviews(self, driver: Chrome) -> List[str]:
        reviews: List[str] = []
        try:
            review_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[jsaction*='reviews']"))
            )
            review_button.click()
            time.sleep(self.config.scroll_pause)
            self._scroll_panel(driver, panel_selector='div[role="main"]')
            review_cards = driver.find_elements(By.CSS_SELECTOR, 'div[jscontroller="MUTyvc"]')
            for card in review_cards:
                try:
                    text = card.find_element(By.CSS_SELECTOR, 'span[jscontroller="M633pe"]').text.strip()
                except Exception:
                    text = card.text.strip()
                if text:
                    reviews.append(text)
                if len(reviews) >= self.config.max_review_count:
                    break
        except Exception as exc:
            logging.debug("Review extraction fallback: %s", exc)
        return reviews

    def _extract_photos(self, driver: Chrome) -> List[str]:
        photos: List[str] = []
        try:
            photo_button = driver.find_element(By.CSS_SELECTOR, "button[aria-label*='Photos']")
            photo_button.click()
            time.sleep(self.config.scroll_pause)
            self._scroll_panel(driver, panel_selector='div[role="feed"]')
            image_elems = driver.find_elements(By.CSS_SELECTOR, "img")
            for elem in image_elems:
                src = elem.get_attribute("src")
                if src and "googleusercontent" in src:
                    photos.append(src)
                if len(photos) >= self.config.max_photo_count:
                    break
        except Exception as exc:
            logging.debug("Photo extraction fallback: %s", exc)
        return photos

    def _scroll_panel(self, driver: Chrome, panel_selector: str) -> None:
        try:
            panel = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, panel_selector)))
        except TimeoutException:
            return
        last_height = 0
        for _ in range(20):
            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", panel)
            time.sleep(self.config.scroll_pause)
            new_height = driver.execute_script("return arguments[0].scrollHeight;", panel)
            if new_height == last_height:
                break
            last_height = new_height

    def _mark_completed(self, row_id: int) -> None:
        with self.counter_lock:
            self.completed_rows.add(row_id)
            self.processed_counter += 1
            if self.processed_counter % 25 == 0:
                self.progress.update(self.processed_counter)

    @staticmethod
    def _memory_health_check() -> None:
        gc.collect()
        me = psutil.Process(os.getpid())
        rss_mb = me.memory_info().rss / (1024 * 1024)
        logging.debug("Current RSS: %.2f MB", rss_mb)
        now = time.time()
        for child in me.children(recursive=True):
            try:
                if child.name().lower() in {"chrome", "chromedriver"} and now - child.create_time() > 300:
                    logging.debug("Killing stale process %s (%s)", child.name(), child.pid)
                    child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Maps review and photo scraper.")
    parser.add_argument("--input-file", required=True, help="Path to source CSV file.")
    parser.add_argument("--output-file", default="result_reviews_photos.csv", help="Path for scraper output CSV.")
    parser.add_argument("--proxies-file", required=True, help="Path to SOCKS5 proxy list.")
    parser.add_argument("--checkpoint-file", default="checkpoints/state.json", help="Checkpoint json path.")
    parser.add_argument("--threads", type=int, default=9, help="Number of concurrent worker threads.")
    parser.add_argument("--cleanup-interval", type=int, default=150, help="Rows per driver cleanup.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Disable headless mode.")
    parser.set_defaults(headless=True)
    return parser.parse_args()


def setup_logging() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "scraper.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def main() -> None:
    args = parse_args()
    setup_logging()
    config = ScraperConfig(
        input_path=Path(args.input_file),
        output_path=Path(args.output_file),
        proxies_path=Path(args.proxies_file),
        checkpoint_path=Path(args.checkpoint_file),
        thread_count=args.threads,
        cleanup_interval=args.cleanup_interval,
        headless=args.headless,
    )
    scraper = GoogleMapsScraper(config)
    scraper.run()


if __name__ == "__main__":
    main()
