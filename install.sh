#!/bin/bash

echo "🚀 Google Maps Scraper - Installation Script"
echo "=============================================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "❌ pip is not installed. Please install pip first."
    exit 1
fi

echo "✅ pip found"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p debug
mkdir -p config

# Check if Chrome is installed (basic check)
if command -v google-chrome &> /dev/null || command -v chromium-browser &> /dev/null || command -v chrome &> /dev/null; then
    echo "✅ Chrome browser detected"
else
    echo "⚠️  Chrome browser not detected. Please install Google Chrome:"
    echo "   - Ubuntu/Debian: sudo apt install google-chrome-stable"
    echo "   - CentOS/RHEL: sudo yum install google-chrome-stable"
    echo "   - macOS: Download from https://www.google.com/chrome/"
    echo "   - Windows: Download from https://www.google.com/chrome/"
fi

# Run test
echo "🧪 Running tests..."
python3 test_scraper.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Installation completed successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "   1. (Optional) Add proxies to config/proxies.txt"
    echo "   2. Run the scraper: python3 google_maps_scraper.py"
    echo "   3. Or try examples: python3 example_usage.py"
    echo ""
    echo "📚 Documentation: See README.md for detailed usage instructions"
else
    echo "❌ Tests failed. Please check the error messages above."
    exit 1
fi