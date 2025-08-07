#!/usr/bin/env python3
"""Example script demonstrating how to use the VFR charts tool programmatically."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scraper import AIPScraper
from pdf_generator import PDFGenerator


def example_scrape_only():
    """Example: Scrape chart information only."""
    print("🔍 Example: Scraping chart information...")
    
    scraper = AIPScraper()
    charts = scraper.scrape_all_aerodromes()
    
    print(f"Found {len(charts)} charts")
    
    # Display first few charts
    for i, chart in enumerate(charts[:5]):
        print(f"  {i+1}. {chart['icao_code']} - {chart['chart_name']}")
    
    return charts


def example_download_single_chart():
    """Example: Download and convert a single chart."""
    print("\n📥 Example: Downloading a single chart...")
    
    # Example chart data (you would get this from scraping)
    chart_info = {
        "icao_code": "EDFE",
        "aerodrome_name": "Frankfurt-Egelsbach",
        "chart_name": "Frankfurt-Egelsbach 5",
        "page_id": "51B96FC66F7767D88BE754F64116ABC3",
        "print_url": "https://aip.dfs.de/basicVFR/print/AD/51B96FC66F7767D88BE754F64116ABC3/EDFE%20Frankfurt-Egelsbach%205"
    }
    
    scraper = AIPScraper()
    pdf_generator = PDFGenerator("example_output")
    
    # Download the chart image
    print("Downloading chart image...")
    image_data = scraper.download_chart_image(chart_info["print_url"])
    
    if image_data:
        print(f"Downloaded {len(image_data)} bytes")
        
        # Generate PDF
        print("Generating PDF...")
        pdf_path = pdf_generator.process_chart(chart_info, image_data)
        
        if pdf_path:
            print(f"✓ Generated PDF: {pdf_path}")
        else:
            print("✗ Failed to generate PDF")
    else:
        print("✗ Failed to download chart image")


def example_batch_processing():
    """Example: Process multiple charts in batch."""
    print("\n🚀 Example: Batch processing...")
    
    # This would typically come from scraping
    example_charts = [
        {
            "icao_code": "EDFE",
            "chart_name": "Aerodrome Chart",
            "print_url": "https://aip.dfs.de/basicVFR/print/AD/51B96FC66F7767D88BE754F64116ABC3/EDFE%20Frankfurt-Egelsbach%205"
        },
        {
            "icao_code": "EDDF", 
            "chart_name": "Approach Chart",
            "print_url": "https://aip.dfs.de/basicVFR/print/AD/example2/EDDF%20Approach"
        }
    ]
    
    scraper = AIPScraper()
    pdf_generator = PDFGenerator("example_batch_output")
    
    charts_with_images = []
    
    for chart in example_charts:
        print(f"Processing {chart['icao_code']}...")
        image_data = scraper.download_chart_image(chart["print_url"])
        
        if image_data:
            charts_with_images.append((chart, image_data))
            print(f"  ✓ Downloaded {chart['icao_code']}")
        else:
            print(f"  ✗ Failed to download {chart['icao_code']}")
    
    if charts_with_images:
        print(f"\nGenerating {len(charts_with_images)} PDFs...")
        successful_pdfs = pdf_generator.process_charts_batch(charts_with_images)
        print(f"✓ Generated {len(successful_pdfs)} PDF files")


def main():
    """Run examples."""
    print("Germany VFR Approach Charts Tool - Examples\n")
    print("=" * 50)
    
    try:
        # Example 1: Scrape only
        example_scrape_only()
        
        # Example 2: Single chart download
        example_download_single_chart()
        
        # Example 3: Batch processing
        example_batch_processing()
        
        print("\n" + "=" * 50)
        print("✅ Examples completed successfully!")
        print("\nTo run the full tool:")
        print("  python scripts/run.py full-pipeline")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 