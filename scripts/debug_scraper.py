#!/usr/bin/env python3
"""Debug script to examine DFS AIP HTML structure."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel

console = Console()


def debug_aip_structure():
    """Debug the AIP HTML structure."""
    console.print(Panel.fit(" Debugging DFS AIP Structure", style="bold blue"))
    
    try:
        # Initialize scraper
        from src.scraper import AIPScraper
        scraper = AIPScraper()
        
        # Get the main page
        console.print("[yellow]Fetching main page...[/yellow]")
        html = scraper.get_aerodrome_list_page()
        
        console.print(f"[green] Successfully fetched page[/green]")
        console.print(f"Content length: {len(html)} characters")
        
        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")
        
        # Find all folder links
        folder_links = soup.find_all("a", class_="folder-link")
        console.print(f"\n[cyan]Found {len(folder_links)} folder links[/cyan]")
        
        # Show all folder links
        console.print("\n[bold]All folder links:[/bold]")
        for i, link in enumerate(folder_links):
            href = link.get("href")
            text = link.get_text(strip=True)
            console.print(f"  {i+1:2d}. {text} -> {href}")
        
        # Look for alphabetical sections specifically
        import re
        alpha_sections = []
        for link in folder_links:
            href = link.get("href")
            
            # Look for folder-name spans within the link
            folder_name_spans = link.find_all("span", class_="folder-name")
            if not folder_name_spans:
                continue
                
            # Get the first folder name (they're duplicated for different languages)
            text = folder_name_spans[0].get_text(strip=True)
            
            # Skip non-alphabetical sections (like "AD 0 Content", "AD 1 General Remarks", etc.)
            if not re.match(r'^[A-Z](-[A-Z])?$', text):
                continue
                
            # This is an alphabetical section
            if href and not any(s[0] == text for s in alpha_sections):
                alpha_sections.append((text, href))
        
        console.print(f"\n[cyan]Found {len(alpha_sections)} alphabetical sections[/cyan]")
        for text, href in alpha_sections:
            console.print(f"  - {text} -> {href}")
        
        # Test one of the sections
        if alpha_sections:
            test_section_name, test_section_url = alpha_sections[0]
            console.print(f"\n[bold]Testing section: {test_section_name}[/bold]")
            
            # Use the scraper's _make_request method for consistency
            full_url = f"{scraper.base_url}/BasicVFR/{scraper.current_date}/chapter/{test_section_url}"
            section_response = scraper._make_request(full_url)
            
            section_soup = BeautifulSoup(section_response.text, "html.parser")
            section_links = section_soup.find_all("a", href=True)
            
            console.print(f"Found {len(section_links)} links in section")
            
            # Show first 10 links
            console.print("\n[bold]First 10 links in section:[/bold]")
            for i, link in enumerate(section_links[:10]):
                href = link.get("href")
                text = link.get_text(strip=True)
                console.print(f"  {i+1:2d}. {text} -> {href}")
            
            # Look for aerodrome links
            aerodrome_links = []
            for link in section_links:
                href = link.get("href")
                text = link.get_text(strip=True)
                if "pages/" in href and len(text) > 3:
                    aerodrome_links.append((text, href))
            
            console.print(f"\n[cyan]Found {len(aerodrome_links)} potential aerodrome links[/cyan]")
            for text, href in aerodrome_links[:5]:
                console.print(f"  - {text} -> {href}")
        
        # Save HTML for inspection
        with open("debug_aip.html", "w", encoding="utf-8") as f:
            f.write(html)
        console.print(f"\n[green]Saved HTML to debug_aip.html for inspection[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    debug_aip_structure() 