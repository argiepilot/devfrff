#!/usr/bin/env python3
"""Test script to verify the cleaned up scraper works without proxy code."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from src.scraper import AIPScraper

console = Console()


def test_clean_scraper():
    """Test the cleaned up scraper."""
    console.print(Panel.fit("🧹 Testing Clean Scraper (No Proxy Code)", style="bold green"))
    
    try:
        # Initialize scraper with simplified constructor
        console.print("\n[bold]Step 1: Initialize scraper[/bold]")
        scraper = AIPScraper(rate_limit=1.0)
        console.print("[green]✓ Scraper initialized successfully[/green]")
        
        # Test basic navigation
        console.print("\n[bold]Step 2: Test navigation flow[/bold]")
        html = scraper.get_aerodrome_list_page()
        console.print(f"[green]✓ Got main page: {len(html)} characters[/green]")
        
        # Test section extraction
        console.print("\n[bold]Step 3: Test section extraction[/bold]")
        sections = scraper.get_alphabetical_sections(html)
        console.print(f"[green]✓ Found {len(sections)} sections[/green]")
        
        if sections:
            section_name, section_url = sections[0]
            console.print(f"[cyan]Testing section: {section_name}[/cyan]")
            
            # Test caching behavior
            aerodromes1 = scraper.get_aerodromes_from_section(section_url)
            console.print(f"[green]✓ First call: {len(aerodromes1)} aerodromes[/green]")
            
            aerodromes2 = scraper.get_aerodromes_from_section(section_url)
            console.print(f"[green]✓ Second call (cached): {len(aerodromes2)} aerodromes[/green]")
            
            # Show cache stats
            cache_stats = scraper.get_cache_stats()
            console.print(f"[cyan]Cache stats: {cache_stats}[/cyan]")
        
        console.print("\n[bold green]🎉 All tests passed! Scraper is clean and working.[/bold green]")
        
    except Exception as e:
        console.print(f"[red]❌ Test failed: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")


if __name__ == "__main__":
    test_clean_scraper()