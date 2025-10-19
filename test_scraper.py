#!/usr/bin/env python3
"""
Simple test script for the Google Maps scraper
"""

import sys
import os

# Add current directory to path to import our scraper
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test individual imports to identify issues"""
    print("🔍 Testing individual imports...")
    
    try:
        import selenium
        print("   ✅ selenium imported")
    except ImportError as e:
        print(f"   ❌ selenium import failed: {e}")
        return False
    
    try:
        import pandas
        print("   ✅ pandas imported")
    except ImportError as e:
        print(f"   ❌ pandas import failed: {e}")
        return False
    
    try:
        import openpyxl
        print("   ✅ openpyxl imported")
    except ImportError as e:
        print(f"   ❌ openpyxl import failed: {e}")
        return False
    
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        print("   ✅ webdriver_manager imported")
    except ImportError as e:
        print(f"   ❌ webdriver_manager import failed: {e}")
        return False
    
    # Test selenium-wire separately
    try:
        import seleniumwire
        print("   ✅ seleniumwire imported")
    except ImportError as e:
        print(f"   ❌ seleniumwire import failed: {e}")
        print("   💡 Try: pip install --upgrade selenium-wire")
        return False
    
    return True

# Test imports first
if not test_imports():
    print("\n❌ Some imports failed. Please install missing dependencies.")
    sys.exit(1)

try:
    from google_maps_scraper import normalize_proxy_for_seleniumwire
    print("✅ Successfully imported scraper functions")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure google_maps_scraper.py is in the same directory")
    sys.exit(1)

def test_basic_functionality():
    """Test basic scraper functionality without actually running Chrome"""
    print("\n🧪 Testing basic functionality...")
    
    # Test proxy normalization
    test_cases = [
        ("192.168.1.1:8080", "http://192.168.1.1:8080"),
        ("http://192.168.1.1:8080", "http://192.168.1.1:8080"),
        ("https://proxy.example.com:3128", "https://proxy.example.com:3128"),
        ("", None),
        (None, None)
    ]
    
    for input_proxy, expected in test_cases:
        result = normalize_proxy_for_seleniumwire(input_proxy)
        if result == expected:
            print(f"   ✅ Proxy normalization: '{input_proxy}' -> '{result}'")
        else:
            print(f"   ❌ Proxy normalization failed: '{input_proxy}' -> '{result}' (expected '{expected}')")
    
    print("   ✅ Basic functionality tests completed")

def test_config_files():
    """Test configuration file setup"""
    print("\n📁 Testing configuration files...")
    
    # Check if config directory exists
    if os.path.exists("config"):
        print("   ✅ Config directory exists")
    else:
        print("   ❌ Config directory missing")
        return
    
    # Check proxy file
    proxy_file = "config/proxies.txt"
    if os.path.exists(proxy_file):
        print("   ✅ Proxy file exists")
        with open(proxy_file, 'r') as f:
            lines = f.readlines()
            print(f"   📄 Proxy file has {len(lines)} lines")
    else:
        print("   ❌ Proxy file missing")

def test_output_directories():
    """Test output directory creation"""
    print("\n📂 Testing output directories...")
    
    # Check if debug directory is created
    if os.path.exists("debug"):
        print("   ✅ Debug directory exists")
    else:
        print("   ❌ Debug directory missing")

def main():
    print("🚀 Google Maps Scraper - Test Suite")
    print("=" * 50)
    
    test_basic_functionality()
    test_config_files()
    test_output_directories()
    
    print("\n" + "=" * 50)
    print("🏁 Test suite completed!")
    print("\n💡 To run the actual scraper:")
    print("   python3 google_maps_scraper.py")
    print("\n⚠️  Note: The actual scraper requires Chrome browser and internet connection")

if __name__ == "__main__":
    main()