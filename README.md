## Google Maps Scraper

This repository includes a Google Maps scraper that collects business details and profile images using Selenium Wire.

### Requirements
- Python 3.10+ installed
- Google Chrome installed
- ChromeDriver compatible with your Chrome version (Selenium Manager will try to download it automatically)

### Installation
If creating a virtual environment is unavailable in your system Python (ensurepip missing), you can install dependencies in user mode:

```bash
python3 -m pip install --user -r requirements.txt
```

Alternatively, if you prefer a virtual environment and your distro supports it:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Optional: Proxies
Add proxies to `config/proxies.txt` (one per line). Supported formats by Selenium Wire:

```text
http://host:port
http://user:password@host:port
socks5://host:port
socks5://user:password@host:port
```

### Running
The script opens Google Maps and scrapes a small sample by default. You can run headless via env var.

```bash
# Headed (default)
python3 scripts/gmaps_scraper.py

# Headless
HEADLESS=1 python3 scripts/gmaps_scraper.py
```

Output is saved to `FULL_DETAILS_TEST.xlsx` in the project root, and screenshots (if any) go to the `debug/` folder.

### Notes
- Scraping may be blocked by Google. Use residential/mobile proxies and rotate if needed.
- Respect robots and site terms. This code is for educational purposes.