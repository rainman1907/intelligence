# Google Maps Business Scraper

A comprehensive Python scraper for extracting detailed business information from Google Maps, including profile images, contact details, hours, and more.

## Features

- 🏢 **Complete Business Details**: Name, rating, type, address, phone, website
- 🖼️ **Profile Images**: Extracts business profile photos
- ⏰ **Operating Hours**: Full weekly schedule when available
- ⭐ **Reviews Count**: Number of customer reviews
- 🌐 **Proxy Support**: Rotate through multiple proxies for reliability
- 🔄 **Anti-Detection**: Advanced techniques to avoid bot detection
- 📊 **Multiple Output Formats**: Excel and CSV export
- 🛡️ **Error Handling**: Robust error recovery and partial result saving

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Chrome Browser** (if not already installed):
   - The scraper uses Chrome WebDriver which will be automatically managed
   - Make sure you have Google Chrome installed on your system

## Configuration

### Proxy Setup (Optional)

1. Edit `config/proxies.txt` to add your proxy servers:
   ```
   # Format: ip:port or username:password@ip:port
   192.168.1.1:8080
   user:pass@proxy.example.com:3128
   ```

2. Leave the file empty to run without proxies

### Search Queries

Edit the `queries` list in the `main()` function to customize your searches:

```python
queries = [
    "Restaurants in Manhattan, New York",
    "Coffee shops in Seattle, WA",
    "Hotels in Paris, France"
]
```

## Usage

### Basic Usage

Run the scraper with default settings:

```bash
python google_maps_scraper.py
```

### Custom Search Function

Use the convenience function for single searches:

```python
from google_maps_scraper import run_custom_search

# Search for coffee shops
results = run_custom_search(
    query="Coffee shops in Seattle", 
    max_results=10, 
    headless=True, 
    use_proxies=True
)

print(f"Found {len(results)} businesses")
for business in results:
    print(f"- {business['name']} | {business['rating']} | {business['phone']}")
```

### Configuration Options

Modify these variables in `main()`:

- `max_businesses_per_query`: Number of businesses to scrape per search (default: 5)
- `headless_mode`: Run browser in background (default: False)
- `queries`: List of search terms

## Output

The scraper generates two files:

1. **Excel file**: `google_maps_results_YYYYMMDD_HHMMSS.xlsx`
2. **CSV file**: `google_maps_results_YYYYMMDD_HHMMSS.csv`

### Output Columns

| Column | Description |
|--------|-------------|
| name | Business name |
| rating | Star rating (1-5) |
| type | Business category/type |
| address | Full address |
| phone | Phone number |
| website | Business website URL |
| hours | Operating hours (semicolon-separated) |
| reviews | Number of reviews |
| profile_image | URL to profile image |

## Advanced Features

### Multiple Selectors

The scraper uses multiple CSS/XPath selectors for each data field to increase reliability as Google Maps updates their interface.

### Anti-Detection

- Random user agents
- Randomized delays between actions
- Chrome automation detection bypass
- Proxy rotation support

### Error Recovery

- Automatic retry with different selectors
- Partial result saving on interruption
- Detailed error logging
- Graceful handling of missing elements

## Troubleshooting

### Common Issues

1. **No results found**:
   - Check your internet connection
   - Verify search queries are valid
   - Try running without proxies
   - Ensure Chrome browser is installed

2. **ChromeDriver errors**:
   - The script automatically downloads the correct ChromeDriver
   - Make sure you have the latest Chrome browser

3. **Proxy issues**:
   - Test proxies manually
   - Remove invalid proxies from config file
   - Run without proxies first to test basic functionality

4. **Rate limiting**:
   - Increase delays between requests
   - Use fewer concurrent requests
   - Rotate through more proxies

### Debug Mode

For debugging, screenshots are automatically saved to the `debug/` folder when errors occur.

## Legal Considerations

- This scraper is for educational and research purposes
- Respect Google's Terms of Service
- Use reasonable delays between requests
- Consider using official APIs when available
- Be mindful of rate limiting and IP blocking

## Dependencies

- `selenium-wire`: Web automation with proxy support
- `selenium`: Web browser automation
- `pandas`: Data manipulation and analysis
- `openpyxl`: Excel file support
- `webdriver-manager`: Automatic ChromeDriver management

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is provided as-is for educational purposes. Use responsibly and in accordance with applicable terms of service.