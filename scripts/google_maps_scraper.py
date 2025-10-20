#!/usr/bin/env python3

import asyncio
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple

from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page


@dataclass
class Business:
    name: Optional[str] = None
    rating: Optional[float] = None
    category: Optional[str] = None  # Type/Category
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    hours: Optional[Dict[str, str]] = None
    reviews: Optional[Dict[str, Any]] = None  # {count: int, text: Optional[str]}
    profile_image: Optional[str] = None
    google_maps_url: Optional[str] = None


@dataclass
class Location:
    label: Optional[str]
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = 1000.0
    locale: Optional[str] = None
    timezone_id: Optional[str] = None


@dataclass
class ProxyConfig:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


SEARCH_URL = "https://www.google.com/maps"


def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip()


async def ensure_consent(page: Page) -> None:
    # Try to accept Google consent if shown
    try:
        # Common selectors for consent dialogs (vary by region)
        for selector in [
            'button:has-text("I agree")',
            'button:has-text("Accept all")',
            'button:has-text("Accept")',
            'button[aria-label="Accept all"]',
            '#introAgreeButton',
        ]:
            btn = page.locator(selector)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(500)
                break
    except Exception:
        pass


async def search_query(page: Page, query: str) -> None:
    await page.goto(SEARCH_URL, wait_until="domcontentloaded")
    await ensure_consent(page)

    search_box = page.locator("input[aria-label='Search Google Maps']")
    await search_box.fill(query)
    await search_box.press("Enter")

    # Wait for results to load; list items in left panel
    await page.wait_for_selector("[role='article']", timeout=20000)


async def open_first_result(page: Page) -> None:
    # Click the first result from the results list
    first = page.locator("[role='article']").first
    await first.click()
    # Wait for the place title to appear
    await page.wait_for_selector("h1.DUwDvf span", timeout=20000)


async def open_place_url(page: Page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    await ensure_consent(page)
    await page.wait_for_selector("h1.DUwDvf span", timeout=20000)


async def extract_hours(page: Page) -> Optional[Dict[str, str]]:
    # Expand hours panel if collapsed
    try:
        hours_button = page.locator("button[aria-label*='Hours'], button[aria-label*='Hours of operation']")
        if await hours_button.count() > 0:
            await hours_button.first.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass

    hours: Dict[str, str] = {}
    try:
        # Hours table rows
        rows = page.locator("table[role='table'] tr")
        row_count = await rows.count()
        if row_count == 0:
            # Alternative selector
            rows = page.locator("div[aria-label*='Hours'] div[role='row']")
            row_count = await rows.count()
        for i in range(row_count):
            row = rows.nth(i)
            day = await row.locator("td:nth-child(1)").inner_text() if await row.locator("td:nth-child(1)").count() else await row.locator("div[role='rowheader']").inner_text()
            hours_text = await row.locator("td:nth-child(2)").inner_text() if await row.locator("td:nth-child(2)").count() else await row.locator("div[role='gridcell']").inner_text()
            hours[normalize_whitespace(day)] = normalize_whitespace(hours_text)
        return hours if hours else None
    except Exception:
        return None


async def extract_reviews(page: Page) -> Optional[Dict[str, Any]]:
    try:
        # Review count and text snippet often near rating
        # Rating container
        rating_container = page.locator("div.F7nice")
        review_count = None
        if await rating_container.count() > 0:
            text = await rating_container.first.inner_text()
            m = re.search(r"(\d+[\,\.]?\d*)\s*reviews?", text, re.I)
            if m:
                try:
                    review_count = int(m.group(1).replace(",", "").replace(".", ""))
                except Exception:
                    pass
        # Alternatively, look for a link that includes reviews
        if review_count is None:
            reviews_link = page.locator("a:has-text('reviews')")
            if await reviews_link.count() > 0:
                txt = await reviews_link.first.inner_text()
                m = re.search(r"(\d+[\,\.]?\d*)", txt)
                if m:
                    review_count = int(m.group(1).replace(",", "").replace(".", ""))
        # Attempt to get the first review text preview
        review_snippet = None
        try:
            snippet_el = page.locator("div.MyEned")
            if await snippet_el.count() > 0:
                review_snippet = normalize_whitespace(await snippet_el.first.inner_text())
        except Exception:
            pass
        if review_count is None and review_snippet is None:
            return None
        return {"count": review_count, "text": review_snippet}
    except Exception:
        return None


async def extract_profile_image(page: Page) -> Optional[str]:
    try:
        img = page.locator("button[jsaction*='hero-header'] img, img[alt*='Photo']")
        if await img.count() == 0:
            img = page.locator("img[data-loaded-class]", has_text="Photos")
        if await img.count() > 0:
            src = await img.first.get_attribute("src")
            return src
    except Exception:
        pass
    return None


async def extract_business(page: Page) -> Business:
    # Wait for page elements
    await page.wait_for_selector("h1.DUwDvf span", timeout=20000)

    # Name
    name = None
    try:
        name = await page.locator("h1.DUwDvf span").first.inner_text()
    except Exception:
        pass

    # Rating
    rating = None
    try:
        rating_text = await page.locator("div.F7nice span[aria-hidden='true']").first.inner_text()
        rating = float(rating_text)
    except Exception:
        pass

    # Category / Type
    category = None
    try:
        category = await page.locator("button[aria-label*='Category'], span.DkEaL").first.inner_text()
    except Exception:
        # Alternative: located near name
        try:
            category = await page.locator("div[jsaction*='pane.rating.category']").first.inner_text()
        except Exception:
            pass
    category = normalize_whitespace(category)

    # Address
    address = None
    try:
        address_el = page.locator("button[data-item-id='address'], div[aria-label*='Address']")
        if await address_el.count() == 0:
            address_el = page.locator("button[aria-label*='Address']")
        if await address_el.count() > 0:
            address = await address_el.first.inner_text()
    except Exception:
        pass
    address = normalize_whitespace(address)

    # Phone
    phone = None
    try:
        phone_el = page.locator("button[data-item-id='phone:tel'], a[href^='tel:'], button[aria-label*='Phone']")
        if await phone_el.count() > 0:
            phone_text = await phone_el.first.inner_text()
            # Normalize phone by extracting digits and separators
            phone = normalize_whitespace(phone_text)
    except Exception:
        pass

    # Website
    website = None
    try:
        website_el = page.locator("a[data-item-id='authority'], a[aria-label*='Website']")
        if await website_el.count() > 0:
            website = await website_el.first.get_attribute("href")
    except Exception:
        pass

    # Hours
    hours = await extract_hours(page)

    # Reviews
    reviews = await extract_reviews(page)

    # Profile image
    profile_image = await extract_profile_image(page)

    # Current URL
    google_maps_url = page.url

    return Business(
        name=normalize_whitespace(name),
        rating=rating,
        category=category,
        address=address,
        phone=phone,
        website=website,
        hours=hours,
        reviews=reviews,
        profile_image=profile_image,
        google_maps_url=google_maps_url,
    )


async def scrape_single(
    query: Optional[str] = None,
    url: Optional[str] = None,
    headless: bool = True,
    location: Optional[Location] = None,
    proxy: Optional[ProxyConfig] = None,
) -> Business:
    if not query and not url:
        raise ValueError("Provide either a search query or a Google Maps place URL")

    async with async_playwright() as p:
        launch_kwargs: Dict[str, Any] = {"headless": headless}
        if proxy is not None:
            launch_kwargs["proxy"] = {
                "server": proxy.server,
                **({"username": proxy.username} if proxy.username else {}),
                **({"password": proxy.password} if proxy.password else {}),
            }
        browser = await p.chromium.launch(**launch_kwargs)

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1366, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "java_script_enabled": True,
            "locale": (location.locale if location and location.locale else "en-US"),
        }
        if location is not None:
            context_kwargs.update(
                {
                    "geolocation": {
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                        **(
                            {"accuracy": float(location.accuracy_m)}
                            if location.accuracy_m is not None
                            else {}
                        ),
                    },
                    "permissions": ["geolocation"],
                    **(
                        {"timezone_id": location.timezone_id}
                        if location.timezone_id
                        else {}
                    ),
                }
            )

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        if url:
            await open_place_url(page, url)
        else:
            await search_query(page, query)  # type: ignore[arg-type]
            await open_first_result(page)

        business = await extract_business(page)

        await context.close()
        await browser.close()
        return business


def _csv_value(row: Dict[str, str], *keys: str) -> Optional[str]:
    for k in keys:
        if k in row and row[k] != "":
            return row[k]
    return None


def load_locations_csv(filepath: str) -> List[Location]:
    if not os.path.exists(filepath):
        return []
    locations: List[Location] = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat_str = _csv_value(row, "latitude", "lat")
                lon_str = _csv_value(row, "longitude", "lng", "lon")
                if lat_str is None or lon_str is None:
                    continue
                latitude = float(lat_str)
                longitude = float(lon_str)
                label = _csv_value(row, "label", "name", "city", "location")
                accuracy_m = _csv_value(row, "accuracy_m", "accuracy")
                locale = _csv_value(row, "locale", "lang")
                timezone_id = _csv_value(row, "timezone_id", "tz")
                locations.append(
                    Location(
                        label=label,
                        latitude=latitude,
                        longitude=longitude,
                        accuracy_m=float(accuracy_m) if accuracy_m else 1000.0,
                        locale=locale,
                        timezone_id=timezone_id,
                    )
                )
            except Exception:
                # Skip invalid rows
                continue
    return locations


def parse_proxy_line(line: str) -> Optional[ProxyConfig]:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    # Add default scheme if missing
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.port:
        return None
    server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    username = parsed.username
    password = parsed.password
    return ProxyConfig(server=server, username=username, password=password)


def load_proxies_file(filepath: str) -> List[ProxyConfig]:
    if not os.path.exists(filepath):
        return []
    proxies: List[ProxyConfig] = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            p = parse_proxy_line(line)
            if p is not None:
                proxies.append(p)
    return proxies


def to_csv_rows(biz_list: List[Business]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for b in biz_list:
        rows.append(
            {
                "Name": b.name,
                "Rating": b.rating,
                "Type/Category": b.category,
                "Address": b.address,
                "Phone": b.phone,
                "Website": b.website,
                "Working Hours": json.dumps(b.hours or {}),
                "Review Count": (b.reviews or {}).get("count"),
                "Review Text": (b.reviews or {}).get("text"),
                "Profile Image URL": b.profile_image,
                "Google Maps URL": b.google_maps_url,
            }
        )
    return rows


def write_output(biz_list: List[Business], output: Optional[str], fmt: str) -> None:
    if fmt == "json":
        data = [asdict(b) for b in biz_list]
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            print(text)
        return

    if fmt == "csv":
        import csv

        rows = to_csv_rows(biz_list)
        fieldnames = list(rows[0].keys()) if rows else [
            "Name",
            "Rating",
            "Type/Category",
            "Address",
            "Phone",
            "Website",
            "Working Hours",
            "Review Count",
            "Review Text",
            "Profile Image URL",
            "Google Maps URL",
        ]
        if output:
            with open(output, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return

    raise ValueError("Unsupported output format. Use 'json' or 'csv'.")


def build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape Google Maps business details (single place or batch by locations/proxies)"
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--query", type=str, help="Search query, e.g., 'coffee shop in Seattle'")
    grp.add_argument("--url", type=str, help="Direct Google Maps place URL")

    parser.add_argument("--output", type=str, default=None, help="Output file path (omit to print)")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--timeout", type=int, default=60, help="Overall timeout seconds")
    parser.add_argument(
        "--locations-file",
        type=str,
        default="config/locations.csv",
        help=(
            "CSV with columns: name/label, latitude/lat, longitude/lng, "
            "[accuracy_m, locale, timezone_id]"
        ),
    )
    parser.add_argument(
        "--proxies-file",
        type=str,
        default="config/proxies.txt",
        help=(
            "Text file with one proxy per line. Formats: "
            "host:port, http://host:port, http://user:pass@host:port, socks5://host:port"
        ),
    )
    parser.add_argument(
        "--ignore-locations",
        action="store_true",
        help="Ignore locations file even if present",
    )
    parser.add_argument(
        "--ignore-proxies",
        action="store_true",
        help="Ignore proxies file even if present",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    async def run_single() -> List[Business]:
        business = await asyncio.wait_for(
            scrape_single(
                query=args.query,
                url=args.url,
                headless=not args.headed,
            ),
            timeout=args.timeout,
        )
        return [business]

    async def run_batch() -> List[Business]:
        locations = (
            []
            if args.ignore_locations
            else load_locations_csv(args.locations_file)  # type: ignore[arg-type]
        )
        proxies = (
            []
            if args.ignore_proxies
            else load_proxies_file(args.proxies_file)  # type: ignore[arg-type]
        )

        # If there are no locations and no proxies, fall back to single
        if not locations and not proxies:
            return await run_single()

        results: List[Business] = []
        headless = not args.headed

        async with async_playwright() as p:
            browser_no_proxy = None
            if not proxies:
                browser_no_proxy = await p.chromium.launch(headless=headless)

            # Build an iteration plan: if locations exist, iterate them; otherwise single run using only proxy
            iterations: List[Tuple[Optional[Location], Optional[ProxyConfig]]] = []
            if locations:
                for i, loc in enumerate(locations):
                    proxy = proxies[i % len(proxies)] if proxies else None
                    iterations.append((loc, proxy))
            else:
                # No locations, but proxies exist -> run once with first proxy
                iterations.append((None, proxies[0]))

            for loc, proxy in iterations:
                try:
                    if proxy is not None:
                        # Launch per-proxy
                        launch_kwargs: Dict[str, Any] = {
                            "headless": headless,
                            "proxy": {
                                "server": proxy.server,
                                **(
                                    {"username": proxy.username}
                                    if proxy.username
                                    else {}
                                ),
                                **(
                                    {"password": proxy.password}
                                    if proxy.password
                                    else {}
                                ),
                            },
                        }
                        browser = await p.chromium.launch(**launch_kwargs)
                    else:
                        # Reuse shared browser without proxy
                        assert browser_no_proxy is not None
                        browser = browser_no_proxy

                    context_kwargs: Dict[str, Any] = {
                        "viewport": {"width": 1366, "height": 900},
                        "user_agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "java_script_enabled": True,
                        "locale": (loc.locale if loc and loc.locale else "en-US"),
                    }
                    if loc is not None:
                        context_kwargs.update(
                            {
                                "geolocation": {
                                    "latitude": loc.latitude,
                                    "longitude": loc.longitude,
                                    **(
                                        {"accuracy": float(loc.accuracy_m)}
                                        if loc.accuracy_m is not None
                                        else {}
                                    ),
                                },
                                "permissions": ["geolocation"],
                                **(
                                    {"timezone_id": loc.timezone_id}
                                    if loc.timezone_id
                                    else {}
                                ),
                            }
                        )

                    context = await browser.new_context(**context_kwargs)
                    page = await context.new_page()

                    async def do_one():
                        if args.url:
                            await open_place_url(page, args.url)
                        else:
                            await search_query(page, args.query)  # type: ignore[arg-type]
                            await open_first_result(page)
                        return await extract_business(page)

                    business = await asyncio.wait_for(do_one(), timeout=args.timeout)
                    results.append(business)
                except Exception as e:
                    print(
                        f"Run failed for location={getattr(loc, 'label', None)} proxy={getattr(proxy, 'server', None)}: {e}",
                        file=sys.stderr,
                    )
                finally:
                    try:
                        await context.close()  # type: ignore[has-type]
                    except Exception:
                        pass
                    if proxy is not None:
                        try:
                            await browser.close()  # type: ignore[has-type]
                        except Exception:
                            pass

            if browser_no_proxy is not None:
                try:
                    await browser_no_proxy.close()
                except Exception:
                    pass

        return results

    try:
        # Prefer batch if files are present (and not ignored)
        results = asyncio.run(run_batch())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    write_output(results, output=args.output, fmt=args.format)


if __name__ == "__main__":
    main()
