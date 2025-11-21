#!/usr/bin/env python3
"""
High-performance Google Maps scraper with proxy rotation, threading,
resumable checkpoints, and memory hygiene tuned for very large datasets.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import logging
import queue
import random
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import psutil
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# --------------------------------------------------------------------------------------
# Configuration dataclasses
# --------------------------------------------------------------------------------------


@dataclass
class ScraperConfig:
    input_path: Path
    output_path: Path
    checkpoint_path: Path
    proxy_file: Path
    log_dir: Path
    id_column: Optional[str]
    link_column: str
    max_workers: int = 9
    review_count: int = 10
    photo_count: int = 20
    max_retries: int = 3
    task_queue_size: int = 64
    driver_refresh_min: int = 100
    driver_refresh_max: int = 200
    cleanup_threshold: int = 150
    page_load_timeout: int = 35
    wait_timeout: int = 25
    scroll_pause: float = 1.2
    headless: bool = True

    def __post_init__(self) -> None:
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_path}")
        if not self.proxy_file.exists():
            raise FileNotFoundError(f"Proxy file not found: {self.proxy_file}")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------------------
# Utility helpers
# --------------------------------------------------------------------------------------


class GracefulKiller:
    """Handles OS signals to stop threads gracefully."""

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        signal.signal(signal.SIGINT, self._request_stop)
        signal.signal(signal.SIGTERM, self._request_stop)

    def _request_stop(self, signum, frame) -> None:  # type: ignore[override]
        logging.warning("Received signal %s, requesting shutdown...", signum)
        self.stop_event.set()


class ProxyPool:
    def __init__(self, proxy_file: Path) -> None:
        with proxy_file.open("r", encoding="utf-8") as handle:
            self._proxies = [line.strip() for line in handle if line.strip()]
        if not self._proxies:
            raise RuntimeError("Proxy list is empty.")
        self._lock = threading.Lock()

    def pick(self) -> str:
        with self._lock:
            return random.choice(self._proxies)


class ProgressTracker:
    def __init__(self, checkpoint_path: Path) -> None:
        self.path = checkpoint_path
        self.lock = threading.Lock()
        self.state = {
            "processed": 0,
            "last_row_id": None,
            "last_updated": None,
        }
        if self.path.exists():
            try:
                self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                logging.warning("Checkpoint file is corrupted, starting fresh.")

    def mark(self, row_id: str) -> None:
        with self.lock:
            self.state["processed"] = int(self.state.get("processed", 0)) + 1
            self.state["last_row_id"] = row_id
            self.state["last_updated"] = datetime.utcnow().isoformat()
            tmp_path = self.path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            tmp_path.replace(self.path)


class MemoryJanitor:
    """Executes periodic memory cleanup to prevent Chrome leaks."""

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold
        self._counter = 0
        self._lock = threading.Lock()

    def maybe_cleanup(self) -> None:
        with self._lock:
            self._counter += 1
            if self._counter < self.threshold:
                return
            self._counter = 0
        logging.info("Running hard memory cleanup.")
        gc.collect()
        self._kill_orphan_chromes()

    @staticmethod
    def _kill_orphan_chromes() -> None:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.name() in {"chrome", "chrome.exe"} and "--type=renderer" in " ".join(
                    proc.cmdline()
                ):
                    continue
                if proc.name() in {"chromedriver", "chromedriver.exe"} and not proc.children():
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


@dataclass
class RowTask:
    row_id: str
    google_maps_link: str
    payload: Dict[str, str] = field(default_factory=dict)


@dataclass
class RowResult:
    row_id: str
    reviews: List[str]
    photos: List[str]
    status: str
    error: Optional[str] = None

    def as_csv_row(self, review_cols: int, photo_cols: int) -> List[str]:
        review_cells = self._pad(self.reviews, review_cols)
        photo_cells = self._pad(self.photos, photo_cols)
        return [self.row_id, self.status, self.error or ""] + review_cells + photo_cells

    @staticmethod
    def _pad(items: List[str], target: int) -> List[str]:
        padded = items[:target]
        if len(padded) < target:
            padded.extend([""] * (target - len(padded)))
        return padded


# --------------------------------------------------------------------------------------
# Selenium driver/session management
# --------------------------------------------------------------------------------------


def build_driver(proxy: str, config: ScraperConfig) -> webdriver.Chrome:
    chrome_options = Options()
    if config.headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_argument(f"--proxy-server={proxy}")
    prefs = {"profile.default_content_setting_values.geolocation": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(config.page_load_timeout)
    return driver


class WorkerContext:
    def __init__(self, config: ScraperConfig, proxy_pool: ProxyPool) -> None:
        self.config = config
        self.proxy_pool = proxy_pool
        self.driver: Optional[webdriver.Chrome] = None
        self.current_proxy = None
        self.records_since_boot = 0
        self.refresh_target = self._next_refresh_target()
        self._init_driver()

    def _init_driver(self) -> None:
        self.current_proxy = self.proxy_pool.pick()
        logging.info("Starting Chrome with proxy %s", self.current_proxy)
        self.driver = build_driver(self.current_proxy, self.config)
        self.records_since_boot = 0

    def _next_refresh_target(self) -> int:
        return random.randint(self.config.driver_refresh_min, self.config.driver_refresh_max)

    def ensure_driver(self) -> webdriver.Chrome:
        if self.driver is None:
            self._init_driver()
        return self.driver

    def register_record(self) -> None:
        self.records_since_boot += 1
        if self.records_since_boot >= self.refresh_target:
            logging.info("Refreshing Chrome session after %s records.", self.records_since_boot)
            self.restart_driver(force_new_proxy=True)
            self.refresh_target = self._next_refresh_target()

    def restart_driver(self, force_new_proxy: bool = True) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:  # noqa: BLE001
                pass
        if force_new_proxy:
            self.current_proxy = self.proxy_pool.pick()
        self.driver = build_driver(self.current_proxy, self.config)
        self.records_since_boot = 0

    def teardown(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:  # noqa: BLE001
                pass
            self.driver = None


# --------------------------------------------------------------------------------------
# Scraping logic
# --------------------------------------------------------------------------------------


def scrape_row(task: RowTask, ctx: WorkerContext, config: ScraperConfig) -> RowResult:
    driver = ctx.ensure_driver()
    attempt = 0
    last_error = None
    while attempt < config.max_retries:
        try:
            driver.get(task.google_maps_link)
            reviews = extract_reviews(driver, config)
            photos = extract_photos(driver, config)
            ctx.register_record()
            return RowResult(task.row_id, reviews, photos, status="success")
        except (TimeoutException, WebDriverException, NoSuchElementException) as exc:
            last_error = str(exc)
            logging.warning(
                "Row %s attempt %s failed (%s). Rotating driver/proxy.",
                task.row_id,
                attempt + 1,
                exc.__class__.__name__,
            )
            ctx.restart_driver(force_new_proxy=True)
            attempt += 1
            time.sleep(2 + attempt)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logging.exception("Unexpected error on row %s", task.row_id)
            ctx.restart_driver(force_new_proxy=True)
            attempt += 1
            time.sleep(2)
    return RowResult(task.row_id, [], [], status="failed", error=last_error)


def extract_reviews(driver: webdriver.Chrome, config: ScraperConfig) -> List[str]:
    wait = WebDriverWait(driver, config.wait_timeout)
    try:
        more_reviews_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[jsaction*='pane.rating.moreReviews']")
            )
        )
        driver.execute_script("arguments[0].click();", more_reviews_button)
    except TimeoutException:
        logging.debug("Reviews button not found; continuing without explicit click.")

    reviews: List[str] = []
    scroll_parent = None
    try:
        scroll_parent = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.m6QErb.DxyBCb"))
        )
    except TimeoutException:
        logging.warning("Review scroll container not found.")

    last_height = 0
    stable_scrolls = 0
    while len(reviews) < config.review_count and stable_scrolls < 6:
        review_cards = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf.fontBodyMedium")
        for card in review_cards:
            body = card.find_elements(By.CSS_SELECTOR, "span.wiI7pd")
            if not body:
                continue
            text = body[0].text.strip()
            if text and text not in reviews:
                reviews.append(text)
                if len(reviews) >= config.review_count:
                    break
        if len(reviews) >= config.review_count or scroll_parent is None:
            break
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_parent)
        new_height = driver.execute_script("return arguments[0].scrollHeight;", scroll_parent)
        if new_height == last_height:
            stable_scrolls += 1
        else:
            stable_scrolls = 0
        last_height = new_height
        time.sleep(config.scroll_pause)

    return reviews[: config.review_count]


def extract_photos(driver: webdriver.Chrome, config: ScraperConfig) -> List[str]:
    wait = WebDriverWait(driver, config.wait_timeout)
    photos: List[str] = []
    gallery_opened = False
    selectors = [
        "button[jsaction*='pane.media.lightbox']",
        "button[jsaction*='pane.media.photo']",
    ]
    for selector in selectors:
        try:
            button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            driver.execute_script("arguments[0].click();", button)
            gallery_opened = True
            break
        except TimeoutException:
            continue
    if gallery_opened:
        time.sleep(1.5)
        photos = _scrape_gallery_images(driver, config)
        _close_gallery(driver)
    if len(photos) < config.photo_count:
        fallback = driver.find_elements(By.CSS_SELECTOR, "img[src*='googleusercontent']")
        for img in fallback:
            src = img.get_attribute("src")
            if src and src.startswith("http"):
                photos.append(src)
                if len(photos) >= config.photo_count:
                    break
    deduped = []
    for url in photos:
        if url not in deduped:
            deduped.append(url)
        if len(deduped) >= config.photo_count:
            break
    return deduped


def _scrape_gallery_images(driver: webdriver.Chrome, config: ScraperConfig) -> List[str]:
    wait = WebDriverWait(driver, config.wait_timeout)
    images: List[str] = []
    try:
        grid = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.UaQhfb.eY4mx div.vzX5Ic"))
        )
    except TimeoutException:
        logging.warning("Photo grid not available.")
        return images

    scrolls = 0
    while len(images) < config.photo_count and scrolls < 10:
        thumbs = grid.find_elements(By.CSS_SELECTOR, "img")
        for thumb in thumbs:
            src = thumb.get_attribute("src")
            if src and "googleusercontent" in src and src not in images:
                images.append(src)
                if len(images) >= config.photo_count:
                    break
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", grid)
        scrolls += 1
        time.sleep(0.7)
    return images


def _close_gallery(driver: webdriver.Chrome) -> None:
    try:
        close_button = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Close']")
        driver.execute_script("arguments[0].click();", close_button)
    except NoSuchElementException:
        driver.execute_script("window.history.go(-1);")
        time.sleep(1)


# --------------------------------------------------------------------------------------
# Core orchestration
# --------------------------------------------------------------------------------------


def load_completed_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    completed: set[str] = set()
    with output_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "Row_ID" not in reader.fieldnames:
            return set()
        for row in reader:
            completed.add(row["Row_ID"])
    logging.info("Loaded %s already-processed rows.", len(completed))
    return completed


def ensure_output_header(output_path: Path, review_count: int, photo_count: int) -> None:
    if output_path.exists() and output_path.stat().st_size > 0:
        return
    header = ["Row_ID", "Status", "Error"]
    header += [f"Review_{i+1}" for i in range(review_count)]
    header += [f"Photo_{i+1}" for i in range(photo_count)]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)


def read_input_rows(
    config: ScraperConfig, completed_ids: set[str]
) -> Iterable[RowTask]:
    with config.input_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if config.link_column not in reader.fieldnames:
            raise KeyError(
                f"Missing required column '{config.link_column}' in {config.input_path}"
            )
        for idx, row in enumerate(reader, start=1):
            row_id = (
                row.get(config.id_column).strip()
                if config.id_column and row.get(config.id_column)
                else str(idx)
            )
            if row_id in completed_ids:
                continue
            link = row.get(config.link_column, "").strip()
            if not link:
                logging.warning("Row %s missing Google Maps link; skipping.", row_id)
                continue
            yield RowTask(row_id=row_id, google_maps_link=link, payload=row)


def run_scraper(config: ScraperConfig) -> None:
    logging.info("Loading completed IDs...")
    completed_ids = load_completed_ids(config.output_path)
    ensure_output_header(config.output_path, config.review_count, config.photo_count)
    tracker = ProgressTracker(config.checkpoint_path)
    proxy_pool = ProxyPool(config.proxy_file)
    janitor = MemoryJanitor(config.cleanup_threshold)
    killer = GracefulKiller()

    tasks = queue.Queue(maxsize=config.task_queue_size)
    results = queue.Queue()
    producer_done = threading.Event()
    workers_done = threading.Event()

    def producer() -> None:
        try:
            for task in read_input_rows(config, completed_ids):
                while not killer.stop_event.is_set():
                    try:
                        tasks.put(task, timeout=1)
                        break
                    except queue.Full:
                        if killer.stop_event.is_set():
                            break
                        continue
                if killer.stop_event.is_set():
                    break
        finally:
            producer_done.set()

    def worker_thread(worker_id: int) -> None:
        ctx = WorkerContext(config, proxy_pool)
        try:
            while not killer.stop_event.is_set():
                try:
                    task = tasks.get(timeout=1)
                except queue.Empty:
                    if producer_done.is_set():
                        break
                    continue
                try:
                    result = scrape_row(task, ctx, config)
                    results.put(result)
                except Exception as exc:  # noqa: BLE001
                    logging.exception("Worker %s crashed on row %s", worker_id, task.row_id)
                    results.put(RowResult(task.row_id, [], [], "failed", str(exc)))
                finally:
                    tasks.task_done()
        finally:
            ctx.teardown()

    def result_writer() -> None:
        with config.output_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            while True:
                if killer.stop_event.is_set() and results.empty() and workers_done.is_set():
                    break
                try:
                    result: RowResult = results.get(timeout=1)
                except queue.Empty:
                    if workers_done.is_set() and results.empty():
                        break
                    continue
                writer.writerow(result.as_csv_row(config.review_count, config.photo_count))
                handle.flush()
                completed_ids.add(result.row_id)
                tracker.mark(result.row_id)
                janitor.maybe_cleanup()

    threads: List[threading.Thread] = []
    producer_thread = threading.Thread(target=producer, name="producer", daemon=True)
    producer_thread.start()

    writer_thread = threading.Thread(target=result_writer, name="writer", daemon=True)
    writer_thread.start()

    for idx in range(config.max_workers):
        thread = threading.Thread(
            target=worker_thread,
            name=f"worker-{idx+1}",
            args=(idx + 1,),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    try:
        while any(thread.is_alive() for thread in threads):
            if killer.stop_event.is_set():
                break
            time.sleep(1)
        for thread in threads:
            thread.join()
    finally:
        workers_done.set()
        writer_thread.join()
        producer_thread.join()
        logging.info("Scraper finished. Processed %s rows.", len(completed_ids))


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def parse_args() -> ScraperConfig:
    parser = argparse.ArgumentParser(
        description="Resumable Google Maps scraper for large restaurant datasets."
    )
    parser.add_argument("--input", required=True, help="Path to source CSV file.")
    parser.add_argument("--output", default="result_reviews_photos.csv", help="Output CSV path.")
    parser.add_argument(
        "--checkpoint", default="checkpoints/progress.json", help="Checkpoint JSON path."
    )
    parser.add_argument("--proxies", required=True, help="Path to proxies.txt file.")
    parser.add_argument("--log-dir", default="logs", help="Directory for log files.")
    parser.add_argument("--id-column", default=None, help="Column containing the unique ID.")
    parser.add_argument(
        "--link-column", default="Google Maps Link", help="Column containing the Google Maps link."
    )
    parser.add_argument("--threads", type=int, default=9, help="Number of worker threads.")
    parser.add_argument(
        "--headless", action=argparse.BooleanOptionalAction, default=True, help="Run headless mode."
    )
    args = parser.parse_args()
    config = ScraperConfig(
        input_path=Path(args.input).expanduser().resolve(),
        output_path=Path(args.output).expanduser().resolve(),
        checkpoint_path=Path(args.checkpoint).expanduser().resolve(),
        proxy_file=Path(args.proxies).expanduser().resolve(),
        log_dir=Path(args.log_dir).expanduser().resolve(),
        id_column=args.id_column,
        link_column=args.link_column,
        max_workers=args.threads,
        headless=args.headless,
    )
    return config


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    logfile = log_dir / f"scraper_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(threadName)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(logfile, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.info("Logging to %s", logfile)


def main() -> None:
    config = parse_args()
    setup_logging(config.log_dir)
    logging.info("Starting scraper with %s threads.", config.max_workers)
    logging.info("Input file: %s", config.input_path)
    run_scraper(config)


if __name__ == "__main__":
    main()
