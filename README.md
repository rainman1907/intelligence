# Google Maps Business Scraper

A powerful Python scraper for extracting detailed business information from Google Maps, including profile images, contact details, ratings, and more.

## Features

- 🔍 **Comprehensive Business Data**: Name, rating, type, address, phone, website, hours, reviews count
- 🖼️ **Profile Images**: Extracts business profile images
- 🌐 **Proxy Support**: Rotate through multiple proxies for large-scale scraping
- 🛡️ **Anti-Detection**: Advanced techniques to avoid detection
- 📊 **Excel Export**: Results saved to Excel format
- 🔄 **Error Handling**: Robust error handling and retry mechanisms
- 📝 **Detailed Logging**: Comprehensive logging for debugging

## Installation

1. **Clone or download the project files**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install ChromeDriver** (handled automatically by webdriver-manager)

## Project Structure

```
google-maps-scraper/
├── google_maps_scraper.py    # Main scraper implementation
├── test_scraper.py          # Simple test script
├── requirements.txt         # Python dependencies
├── config/
│   └── proxies.txt         # Proxy configuration (optional)
├── debug/                  # Debug screenshots (auto-created)
└── README.md              # This file
```

## Usage

### Basic Usage

```python
from google_maps_scraper import GoogleMapsScraperSW

# Initialize scraper
scraper = GoogleMapsScraperSW(headless=False)

# Search for businesses
results = scraper.search_businesses("Restaurants in New York", max_businesses=10)

# Process results
for business in results:
    print(f"Name: {business['name']}")
    print(f"Rating: {business['rating']}")
    print(f"Address: {business['address']}")
    print(f"Phone: {business['phone']}")
    print("---")

# Clean up
scraper.close()
```

### Using Proxies

1. **Add proxies to `config/proxies.txt`**:
   ```
   192.168.1.100:8080
   user:pass@proxy.example.com:3128
   203.0.113.1:8080
   ```

2. **Load and use proxies**:
   ```python
   # Load proxies from file
   proxies = []
   with open('config/proxies.txt', 'r') as f:
       proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]

   # Initialize scraper with proxies
   scraper = GoogleMapsScraperSW(proxies=proxies, headless=True)
   ```

### Running the Main Script

```bash
python google_maps_scraper.py
```

This will:
- Search for "Restaurants in Manhattan, New York"
- Extract details for up to 5 businesses
- Save results to `google_maps_results.xlsx`

### Running Tests

```bash
python test_scraper.py
```

## Configuration

### ScraperConfig Class

You can modify the configuration in `google_maps_scraper.py`:

```python
@dataclass
class ScraperConfig:
    debug_dir: str = "debug"           # Debug screenshots directory
    max_retries: int = 3               # Maximum retry attempts
    implicit_wait: int = 3             # Selenium implicit wait
    page_load_timeout: int = 20        # Page load timeout
    search_timeout: int = 12           # Search operation timeout
    detail_timeout: int = 8            # Detail extraction timeout
    scroll_pause: float = 1.0          # Pause after scrolling
    click_pause: float = 2.0           # Pause after clicking
```

### Proxy Format

Supported proxy formats in `config/proxies.txt`:
- `ip:port`
- `username:password@ip:port`
- `http://ip:port`
- `http://username:password@ip:port`

## Extracted Data Fields

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Business name | "Joe's Coffee Shop" |
| `rating` | Average rating | "4.5" |
| `type` | Business category | "Coffee shop" |
| `address` | Full address | "123 Main St, New York, NY 10001" |
| `phone` | Phone number | "(555) 123-4567" |
| `website` | Website URL | "https://joescoffee.com" |
| `hours` | Operating hours | "Mon: 7AM-9PM; Tue: 7AM-9PM..." |
| `reviews` | Number of reviews | "142" |
| `profile_image` | Profile image URL | "https://maps.googleapis.com/..." |

## Advanced Usage

### Custom Search Queries

```python
queries = [
    "Italian restaurants in Rome",
    "Hotels near Times Square",
    "Gas stations in Los Angeles",
    "Pharmacies in London"
]

all_results = []
scraper = GoogleMapsScraperSW(headless=True)

for query in queries:
    results = scraper.search_businesses(query, max_businesses=20)
    all_results.extend(results)
    
# Save all results
import pandas as pd
df = pd.DataFrame(all_results)
df.to_excel("all_businesses.xlsx", index=False)
```

### Error Handling

```python
import logging

# Enable detailed logging
logging.basicConfig(level=logging.INFO)

try:
    scraper = GoogleMapsScraperSW()
    results = scraper.search_businesses("Your query here")
    
    if not results:
        print("No results found - check logs for details")
        
except Exception as e:
    print(f"Scraping failed: {e}")
    # Check debug/ folder for screenshots
finally:
    scraper.close()
```

## Troubleshooting

### Common Issues

1. **ChromeDriver not found**
   - The script uses `webdriver-manager` to automatically download ChromeDriver
   - Ensure you have Chrome browser installed

2. **No results found**
   - Check your internet connection
   - Verify the search query is valid
   - Check debug screenshots in the `debug/` folder

3. **Proxy issues**
   - Verify proxy format in `config/proxies.txt`
   - Test proxies manually before using
   - Check proxy authentication credentials

4. **Rate limiting**
   - Use proxies to distribute requests
   - Add delays between requests
   - Use headless mode for better performance

### Debug Mode

Enable debug mode for troubleshooting:

```python
scraper = GoogleMapsScraperSW(headless=False)  # Show browser
```

Screenshots are automatically saved to the `debug/` folder when errors occur.

## Performance Tips

1. **Use headless mode** for better performance:
   ```python
   scraper = GoogleMapsScraperSW(headless=True)
   ```

2. **Optimize timeouts** for your network:
   ```python
   CONFIG.search_timeout = 15  # Increase for slow connections
   CONFIG.detail_timeout = 10
   ```

3. **Use proxy rotation** for large-scale scraping:
   ```python
   scraper = GoogleMapsScraperSW(proxies=proxy_list)
   ```

4. **Batch processing**:
   ```python
   # Process in smaller batches
   for i in range(0, len(queries), 10):
       batch = queries[i:i+10]
       # Process batch
   ```

## Legal Considerations

- Respect Google's Terms of Service
- Don't overload Google's servers with too many requests
- Use appropriate delays between requests
- Consider using official Google Places API for commercial use
- Be mindful of robots.txt and rate limiting

## Dependencies

- `selenium-wire`: Web automation with proxy support
- `selenium`: Web browser automation
- `pandas`: Data manipulation and analysis
- `openpyxl`: Excel file handling
- `webdriver-manager`: Automatic ChromeDriver management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is for educational purposes. Please ensure compliance with Google's Terms of Service and applicable laws in your jurisdiction.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review debug logs and screenshots
3. Verify your configuration
4. Test with a simple query first

---

**Note**: This scraper is designed for educational and research purposes. Always respect website terms of service and implement appropriate rate limiting.