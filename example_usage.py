#!/usr/bin/env python3
"""
Example usage of the Google Maps scraper
"""

import os
import sys
from google_maps_scraper import run_custom_search, GoogleMapsScraperSW

def example_1_simple_search():
    """Example 1: Simple search using the convenience function"""
    print("📍 Example 1: Simple search for coffee shops")
    print("-" * 50)
    
    results = run_custom_search(
        query="Coffee shops in Seattle, WA",
        max_results=3,
        headless=True,  # Run in background
        use_proxies=False  # Don't use proxies for this example
    )
    
    if results:
        print(f"✅ Found {len(results)} coffee shops:")
        for i, business in enumerate(results, 1):
            print(f"  {i}. {business['name']}")
            print(f"     Rating: {business['rating']}")
            print(f"     Address: {business['address']}")
            print(f"     Phone: {business['phone']}")
            print()
    else:
        print("❌ No results found")

def example_2_multiple_searches():
    """Example 2: Multiple searches with custom configuration"""
    print("📍 Example 2: Multiple searches")
    print("-" * 50)
    
    # List of searches to perform
    searches = [
        "Pizza restaurants in New York, NY",
        "Gyms in Los Angeles, CA"
    ]
    
    # Initialize scraper once for multiple searches
    scraper = GoogleMapsScraperSW(proxies=[], headless=True)
    all_results = []
    
    try:
        for query in searches:
            print(f"🔍 Searching: {query}")
            results = scraper.search_businesses(query, max_businesses=2)
            
            if results:
                all_results.extend(results)
                print(f"   ✅ Found {len(results)} businesses")
            else:
                print(f"   ❌ No results for: {query}")
        
        print(f"\n📊 Total results: {len(all_results)}")
        
        # Save results to file
        if all_results:
            import pandas as pd
            df = pd.DataFrame(all_results)
            output_file = "example_results.xlsx"
            df.to_excel(output_file, index=False)
            print(f"💾 Results saved to: {output_file}")
            
    finally:
        scraper.close()

def example_3_with_proxies():
    """Example 3: Using proxies (if configured)"""
    print("📍 Example 3: Search with proxy configuration")
    print("-" * 50)
    
    proxy_file = "config/proxies.txt"
    
    # Check if proxies are configured
    proxies = []
    if os.path.exists(proxy_file):
        with open(proxy_file, 'r') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    
    if proxies:
        print(f"🌐 Using {len(proxies)} configured proxies")
        scraper = GoogleMapsScraperSW(proxies=proxies, headless=True)
    else:
        print("ℹ️  No proxies configured, using direct connection")
        scraper = GoogleMapsScraperSW(proxies=[], headless=True)
    
    try:
        results = scraper.search_businesses("Hotels in Miami, FL", max_businesses=2)
        
        if results:
            print(f"✅ Found {len(results)} hotels:")
            for business in results:
                print(f"  • {business['name']} - {business['rating']} stars")
        else:
            print("❌ No results found")
            
    finally:
        scraper.close()

def main():
    """Run all examples"""
    print("🚀 Google Maps Scraper - Usage Examples")
    print("=" * 60)
    print()
    
    # Check if Chrome is available (basic check)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        # Try to create a Chrome options object
        options = Options()
        options.add_argument("--headless")
        print("✅ Chrome WebDriver support detected")
        
    except Exception as e:
        print(f"⚠️  Chrome WebDriver issue: {e}")
        print("   Make sure Chrome browser is installed")
        return
    
    print("\n" + "=" * 60)
    
    try:
        # Run examples
        example_1_simple_search()
        print("\n" + "=" * 60)
        
        example_2_multiple_searches()
        print("\n" + "=" * 60)
        
        example_3_with_proxies()
        
    except KeyboardInterrupt:
        print("\n🛑 Examples interrupted by user")
    except Exception as e:
        print(f"\n❌ Example error: {e}")
        print("💡 Make sure you have a stable internet connection")
        print("💡 Try running with headless=False to see what's happening")
    
    print("\n" + "=" * 60)
    print("🏁 Examples completed!")
    print("\n💡 Tips:")
    print("   - Modify queries in the examples to test different searches")
    print("   - Set headless=False to see the browser in action")
    print("   - Add proxies to config/proxies.txt for proxy rotation")
    print("   - Check the generated Excel files for full results")

if __name__ == "__main__":
    main()