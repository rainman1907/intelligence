#!/usr/bin/env python3
"""
Simple test script for the Google Maps scraper
"""

import sys
import os
from google_maps_scraper import GoogleMapsScraperSW

def test_scraper():
    """Test the scraper with a simple query"""
    print("🧪 Testing Google Maps Scraper")
    print("=" * 40)
    
    # Test configuration
    test_query = "Coffee shops in Seattle, WA"
    max_results = 3
    
    print(f"Query: {test_query}")
    print(f"Max results: {max_results}")
    print("-" * 40)
    
    # Initialize scraper (no proxies for testing)
    scraper = GoogleMapsScraperSW(proxies=[], headless=True)
    
    try:
        # Perform search
        results = scraper.search_businesses(test_query, max_businesses=max_results)
        
        if results:
            print(f"✅ Success! Found {len(results)} businesses:")
            print()
            
            for i, business in enumerate(results, 1):
                print(f"{i}. {business['name']}")
                print(f"   Rating: {business['rating']}")
                print(f"   Type: {business['type']}")
                print(f"   Address: {business['address']}")
                print(f"   Phone: {business['phone']}")
                print(f"   Website: {business['website']}")
                print()
            
            return True
        else:
            print("❌ No results found")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        scraper.close()

if __name__ == "__main__":
    success = test_scraper()
    sys.exit(0 if success else 1)