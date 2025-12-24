#!/usr/bin/env python3
"""Test script to demonstrate browser-like caching behavior."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from src.scraper import AIPScraper

console = Console()


def test_cache_behavior():
    """Test the new caching behavior."""
    console.print(Panel.fit(" Testing Browser-Like Caching Behavior", style="bold blue"))
    
    try:
        # Initialize scraper
        scraper = AIPScraper(rate_limit=1.0)  # Faster for testing
        
        # Get the main page to set up navigation
        console.print("\n[bold]Step 1: Initial navigation setup[/bold]")
        html = scraper.get_aerodrome_list_page()
        sections = scraper.get_alphabetical_sections(html)
        
        if not sections:
            console.print("[red]No sections found![/red]")
            return
            
        # Test with first few sections
        test_sections = sections[:3]  # Test with first 3 sections
        console.print(f"\n[cyan]Testing with {len(test_sections)} sections[/cyan]")
        
        for section_name, section_url in test_sections:
            console.print(f"\n[bold yellow]Testing section: {section_name}[/bold yellow]")
            
            # First access - should fetch from server
            console.print("[cyan]First access (should fetch from server):[/cyan]")
            aerodromes1 = scraper.get_aerodromes_from_section(section_url)
            console.print(f"Found {len(aerodromes1)} aerodromes")
            
            # Second access - should use cache
            console.print("[cyan]Second access (should use cache):[/cyan]")
            aerodromes2 = scraper.get_aerodromes_from_section(section_url)
            console.print(f"Found {len(aerodromes2)} aerodromes")
            
            # Verify they're the same
            if aerodromes1 == aerodromes2:
                console.print("[green] Cache working correctly - same results[/green]")
            else:
                console.print("[red] Cache issue - different results[/red]")
        
        # Show cache statistics
        cache_stats = scraper.get_cache_stats()
        console.print(f"\n[bold green] Cache Statistics[/bold green]")
        console.print(f"[green]Cached pages: {cache_stats['cached_pages']}[/green]")
        console.print(f"[green]Cache size: {cache_stats['cache_size_kb']} KB[/green]")
        
        # Show which pages are cached
        console.print(f"\n[bold]Cached section pages:[/bold]")
        for i, url in enumerate(scraper.page_cache.keys(), 1):
            console.print(f"  {i}. {url[:50]}...")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_cache_behavior()