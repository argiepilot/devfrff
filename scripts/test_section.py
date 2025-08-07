#!/usr/bin/env python3
"""Test script to examine a specific section page."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()


def test_e_f_section():
    """Test the E-F section page."""
    console.print("🔍 Testing E-F section page...")
    
    try:
        # Use the scraper to dynamically get the E-F section
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        from src.scraper import AIPScraper
        
        scraper = AIPScraper()
        console.print("Getting aerodrome list page...")
        html = scraper.get_aerodrome_list_page()
        
        # Find E-F section link
        soup = BeautifulSoup(html, "html.parser")
        folder_links = soup.find_all("a", class_="folder-link")
        
        ef_url = None
        for link in folder_links:
            text = link.get_text(strip=True)
            if text in ["E-F", "E - F"]:
                ef_url = link.get("href")
                console.print(f"Found E-F section: {ef_url}")
                break
        
        if not ef_url:
            console.print("[red]E-F section not found[/red]")
            return
            
        # Test the E-F section page
        response = scraper._make_request(ef_url)
        response.raise_for_status()
        
        console.print(f"[green]✓ Successfully fetched E-F section[/green]")
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
        
        # Look for Frankfurt specifically
        frankfurt_links = []
        for link in links:
            text = link.get_text(strip=True)
            if "Frankfurt" in text:
                href = link.get("href")
                frankfurt_links.append((text, href))
        
        console.print(f"\n[cyan]Found {len(frankfurt_links)} Frankfurt links[/cyan]")
        for text, href in frankfurt_links:
            console.print(f"  - {text} -> {href}")
        
        # Save HTML for inspection
        with open("debug_e_f_section.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        console.print(f"\n[green]Saved HTML to debug_e_f_section.html[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    test_e_f_section() 