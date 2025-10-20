from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from rich.console import Console

from gmaps_scraper.driver import create_driver
from gmaps_scraper.proxies import parse_proxies_file, round_robin
from gmaps_scraper.scraper import (
    collect_place_urls,
    extract_place_details,
    go_to_maps_home,
    perform_search,
)


console = Console()


def read_queries(csv_path: str) -> List[str]:
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"Locations file not found: {csv_path}")
    queries: List[str] = []
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "query" not in reader.fieldnames:
            raise ValueError("locations.csv must have a 'query' column")
        for row in reader:
            q = (row.get("query") or "").strip()
            if q:
                queries.append(q)
    return queries


def write_results_csv(path: str, records: Iterable[Dict[str, str]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = list(records)
    if not rows:
        return
    fieldnames = [
        "Name",
        "Rating",
        "last_10_comments",
        "Type/Category",
        "Address",
        "Phone",
        "Website",
        "Working Hours",
        "Review Count/Text",
        "profile_image",
        "Google Maps URL",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Google Maps scraper (Selenium + undetected-chromedriver)")
    parser.add_argument("--locations", default="config/locations.csv", help="CSV file with a 'query' column")
    parser.add_argument("--proxies", default="config/proxies.txt", help="Text file with proxies (optional)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--max-places", type=int, default=20, help="Max places per query")
    parser.add_argument("--lang", default="en-US", help="Chrome UI language")
    parser.add_argument("--output", default=None, help="Output CSV path")

    args = parser.parse_args(argv)

    queries = read_queries(args.locations)
    proxies = parse_proxies_file(args.proxies)
    proxy_cycle = round_robin(proxies)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"output/maps_results_{ts}.csv"

    all_records: List[Dict[str, str]] = []

    console.print(f"[bold green]Loaded {len(queries)} queries[/bold green]")
    if proxies:
        console.print(f"[bold cyan]Using {len(proxies)} proxies (round-robin)[/bold cyan]")
    # Cookie/Gmail login removed — scraper runs without authentication

    for idx, query in enumerate(queries, start=1):
        proxy = next(proxy_cycle)
        proxy_raw = proxy.raw if proxy else None
        console.print(f"[bold]({idx}/{len(queries)})[/bold] Query: {query}  Proxy: {proxy_raw or 'none'}")

        driver = create_driver(proxy=proxy_raw, headless=args.headless, lang=args.lang)
        try:
            go_to_maps_home(driver)
            perform_search(driver, query)
            urls = collect_place_urls(driver, max_places=args.max_places)
            console.print(f"Found {len(urls)} place URLs")
            for i, url in enumerate(urls, start=1):
                console.print(f"  - [{i}/{len(urls)}] {url}")
                driver.get(url)
                time.sleep(1.0)
                record = extract_place_details(driver)
                all_records.append(record)
                # Be polite; small delay between places
                time.sleep(0.8)
        except Exception as e:
            console.print(f"[bold red]Error while processing query '{query}': {e}[/bold red]")
        finally:
            driver.quit()
            time.sleep(0.6)

    write_results_csv(output_path, all_records)
    console.print(f"[bold green]Saved {len(all_records)} rows to[/bold green] {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
