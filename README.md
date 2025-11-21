# Google Maps Review & Photo Extraction System

This project delivers a high-performance, resumable Google Maps scraping pipeline tailored for very large US restaurant datasets (600k+ rows).

## Input Format Decision
- **Chosen format:** `.csv`
- **Why:** CSV streams efficiently, avoids Excel parsing overhead, works with incremental append-only writes, and reduces RAM spikes during multi-day runs. The original Excel workbook stays untouched; convert it to CSV once (or export a copy) and pass that file to the scraper.

## Components
- `scripts/scraper.py` – concurrent Selenium + undetected Chrome scraper with 9–10 threads, SOCKS5 proxy rotation, checkpointing, per-thread memory cleanup, and resume support via `result_reviews_photos.csv` + `checkpoints/state.json`.
- `scripts/merge_datasets.py` – merges the scraped reviews/photos back into the master dataset without overwriting existing fields.

## Features
- Random proxy per worker thread pulled from `proxies.txt` (`socks5://user:pass@ip:port` per line).
- Automatic retries with proxy swaps, graceful skip + logging after repeated failures.
- Output-only writes: 10 review columns (`Review_1` … `Review_10`) and 20 photo URL columns (`Photo_1` … `Photo_20`) stored in `result_reviews_photos.csv`.
- Resume behavior: on restart, processed `Row_ID`s are read from the output file, queued rows skip automatically, checkpoint JSON records progress, and threads pick up remaining work.
- Hard resource cleanup every N records (`--cleanup-interval`), closing Chrome, forcing GC, and killing orphaned Chrome/chromedriver processes older than 5 minutes.

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Scraper
```bash
python scripts/scraper.py \
  --input-file data/restaurants.csv \
  --proxies-file proxies.txt \
  --output-file result_reviews_photos.csv \
  --checkpoint-file checkpoints/state.json \
  --threads 10 \
  --cleanup-interval 150 \
  --headless
```

### Operational Notes
- Keep the original Excel file unchanged; feed the scraper a CSV export residing on fast local storage or an attached SSD.
- `Row_ID` equals the 1-based line number (excluding headers) from the input CSV. Do not shuffle or sort the source file between runs.
- Ensure `logs/scraper.log` is monitored; failures are recorded there along with proxy rotation events.
- If the process stops, rerun the same command; remaining rows continue automatically.

## Merge Script
After scraping:
```bash
python scripts/merge_datasets.py \
  --source-file data/restaurants.xlsx \
  --scraped-file result_reviews_photos.csv \
  --output-file data/restaurants_enriched.xlsx
```
- The script adds/uses a `Row_ID` column (creates it if absent) and performs a one-to-one merge, ensuring no data loss.

## Recommended Workflow
1. Export the restaurant workbook to CSV once.
2. Prepare `proxies.txt` with 150+ rotating SOCKS5 endpoints.
3. Launch the scraper on a server with Chrome/Chromium installed and enough bandwidth/CPU; supervise logs.
4. Periodically archive `result_reviews_photos.csv` and `checkpoints/state.json` for redundancy.
5. Use the merge script to produce a final enriched dataset when scraping completes.