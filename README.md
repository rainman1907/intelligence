# Google Maps – Latest Review & Photo Scraper

This workspace contains a headful Puppeteer + Stealth scraper that opens every Google Maps business URL from an Excel spreadsheet and backfills the newest review text/date plus the original photo URL (the `lh3.googleusercontent.com/p/...` asset).

## Prerequisites
- Node.js 18+ (needed because Puppeteer bundles a matching Chromium)
- An Excel file (`.xlsx`) with the following headers already in row 1:
  ```
  name | address | maps_url | phone | website | category | rating | review_count | latest_review | latest_review_date | latest_photo_url
  ```
- A desktop session (or Xvfb) so Chromium can run with `headless: false`

## Install Dependencies
```bash
npm install
```

## Usage
```bash
node google-maps-scraper.js /absolute/path/to/your-file.xlsx
```

If you omit the argument the script looks for `maps-input.xlsx` in the current directory.

### What the Script Does
- Launches Puppeteer with `puppeteer-extra` + Stealth in non-headless mode and randomized user agents.
- Opens each `maps_url`, handles cookie banners, and waits for the page to finish bootstrapping.
- Clicks **Photos**, parses the `APP_INITIALIZATION_STATE` payload to grab the true `lh3` photo URL (falls back to the DOM if needed), and removes Google’s sizing parameters.
- Clicks **Reviews**, sorts by *Newest*, scrolls gently, and captures the newest review text, timestamp (via the same JSON blob when available), and ISO date fallback from the DOM.
- Retries failed navigations/actions up to three times per row, logs progress, and keeps updating the same Excel file after each business so progress is never lost.

## Tips
- Keep a small row count when you first run the script to make sure your network/IP isn’t being throttled.
- If Google serves the EU consent iframe, the script will attempt to auto-dismiss it, but you can also manually accept it in the live browser window.
- Use a VPN or rotating proxies if you plan to scrape a large number of listings.