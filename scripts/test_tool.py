#!/usr/bin/env python3
"""Test script to verify the tool works correctly."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_imports():
    """Test that all modules can be imported."""
    try:
        from scraper import AIPScraper
        from pdf_generator import PDFGenerator
        print("✓ All modules imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_scraper_init():
    """Test scraper initialization."""
    try:
        from scraper import AIPScraper
        scraper = AIPScraper()
        print("✓ Scraper initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Scraper initialization error: {e}")
        return False

def test_pdf_generator_init():
    """Test PDF generator initialization."""
    try:
        from pdf_generator import PDFGenerator
        generator = PDFGenerator("test_output")
        print("✓ PDF generator initialized successfully")
        return True
    except Exception as e:
        print(f"✗ PDF generator initialization error: {e}")
        return False

def test_url_building():
    """Test URL building functionality."""
    try:
        from scraper import AIPScraper
        scraper = AIPScraper()
        
        page_id = "51B96FC66F7767D88BE754F64116ABC3"
        chart_name = "EDFE Frankfurt-Egelsbach 5"
        
        expected_url = (
            "https://aip.dfs.de/basicVFR/print/AD/"
            "51B96FC66F7767D88BE754F64116ABC3/"
            "EDFE%20Frankfurt-Egelsbach%205"
        )
        
        result = scraper._build_print_url(page_id, chart_name)
        
        if result == expected_url:
            print("✓ URL building works correctly")
            return True
        else:
            print(f"✗ URL building failed. Expected: {expected_url}, Got: {result}")
            return False
            
    except Exception as e:
        print(f"✗ URL building error: {e}")
        return False

def main():
    """Run all tests."""
    print("Testing Germany VFR Approach Charts Tool...\n")
    
    tests = [
        test_imports,
        test_scraper_init,
        test_pdf_generator_init,
        test_url_building,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Tool is ready to use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 