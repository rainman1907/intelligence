# intelligence

## Overview

This repo contains a production-focused Google Maps scraping pipeline tailored for very large U.S. restaurant datasets (≈600k rows). It delivers:

- `scraper.py`: multi-threaded, proxy-rotating Selenium scraper that collects the latest 10 reviews and 20 photo URLs per record.
- `merge_results.py`: lightweight merger that appends the scraped fields back onto the original dataset without touching the source file.
- `requirements.txt`: Python dependencies for a clean virtual environment.

## Input format decision

The system is built around **CSV** files rather than `.xlsx`. CSV reads/writes are streaming-friendly, avoid Excel overhead, and remain stable across hundreds of thousands of rows. Convert your Excel master sheet once (Excel ➜ Save As ➜ CSV UTF-8) and keep that CSV as the immutable input; the scripts never edit it.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Place your proxy list in `proxies.txt` (one entry per line, e.g. `socks5://user:pass@ip:port`).

## Running the scraper

```bash
python scraper.py \
  --input data/restaurants.csv \
  --output data/result_reviews_photos.csv \
  --checkpoint checkpoints/progress.json \
  --proxies proxies.txt \
  --id-column RestaurantID \
  --link-column "Google Maps Link" \
  --threads 9
```

Key behavior:

- 9–10 workers (configurable) each run their own headless Chrome with a random SOCKS5 proxy.
- Automatic resume: `result_reviews_photos.csv` + `checkpoints/progress.json` drive restart logic.
- Hard memory cleanups (Chrome restart, GC, orphan kill) every ~150 records keep the job stable for multi-day runs.
- Fault tolerance: each row retries with fresh proxies; failures are logged and skipped without halting the pipeline.

## Running the merge

```bash
python merge_results.py \
  --input data/restaurants.csv \
  --scraped data/result_reviews_photos.csv \
  --output data/final_merged.csv \
  --id-column RestaurantID
```

The merger copies the original dataset untouched, appends the review/photo columns (and status/error), and writes a new combined CSV.

## Outputs

- `result_reviews_photos.csv`: columns `Row_ID`, `Status`, `Error`, `Review_1`…`Review_10`, `Photo_1`…`Photo_20`.
- `final_merged.csv` (or your chosen name): all original columns plus the appended review/photo columns.

## Operational tips

- Keep `logs/` and `checkpoints/` on fast local storage; rotate or prune logs periodically.
- Run long jobs under a process manager (systemd, supervisord, or Kubernetes) so restarts are automatic.
- To change concurrency or headless mode, use `--threads` and `--headless/--no-headless`.