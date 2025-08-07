#!/usr/bin/env python3
"""Test script to examine an actual aerodrome page."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()


def test_aerodrome_page():
    """Test accessing an actual aerodrome page."""
    console.print("🔍 Testing aerodrome page access...")
    
    try:
        # Use the scraper to dynamically get a test aerodrome page
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        from src.scraper import AIPScraper
        
        scraper = AIPScraper()
        console.print("Getting aerodrome list page...")
        html = scraper.get_aerodrome_list_page()
        
        # Find first aerodrome link
        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=True)
        
        test_url = None
        for link in links:
            href = link.get("href")
            text = link.get_text(strip=True)
            if "pages/" in href and len(text) >= 4:  # Likely an aerodrome code
                test_url = href
                console.print(f"Found test aerodrome: {text} -> {href}")
                break
        
        if not test_url:
            console.print("[red]No aerodrome links found[/red]")
            return
            
        # Test the aerodrome page
        response = scraper._make_request(test_url)
        
        console.print(f"[green]✓ Successfully fetched aerodrome page[/green]")
        console.print(f"Content length: {len(response.text)} characters")
        
        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find all links
        links = soup.find_all("a", href=True)
        console.print(f"\n[cyan]Found {len(links)} total links[/cyan]")
        
        # Show first 20 links
        console.print("\n[bold]First 20 links:[/bold]")
        for i, link in enumerate(links[:20]):
            href = link.get("href")
            text = link.get_text(strip=True)
            console.print(f"  {i+1:2d}. {text} -> {href}")
        
        # Look for links with "pages/" in href
        page_links = [link for link in links if "pages/" in link.get("href", "")]
        console.print(f"\n[cyan]Found {len(page_links)} links with 'pages/' in href[/cyan]")
        
        # Show page links
        console.print("\n[bold]Page links:[/bold]")
        for i, link in enumerate(page_links[:10]):
            href = link.get("href")
            text = link.get_text(strip=True)
            console.print(f"  {i+1:2d}. {text} -> {href}")
        
        # Save HTML for inspection
        with open("debug_aerodrome_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        console.print(f"\n[green]Saved HTML to debug_aerodrome_page.html[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    test_aerodrome_page() 