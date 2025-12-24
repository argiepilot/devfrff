#!/usr/bin/env python3
"""Test script for the new --limit functionality."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from src.scraper import AIPScraper

console = Console()


def test_limit_functionality():
    """Test the new limit functionality."""
    console.print(Panel.fit(" Testing Aerodrome Limit Functionality", style="bold blue"))
    
    try:
        # Test with limit of 5 aerodromes
        test_limit = 5
        console.print(f"\n[cyan]Testing with limit of {test_limit} aerodromes[/cyan]")
        
        # Initialize scraper
        scraper = AIPScraper(rate_limit=1.0)  # Faster for testing
        
        # Run scraper with limit
        charts = scraper.scrape_all_aerodromes(limit_aerodromes=test_limit)
        
        # Show results
        console.print(f"\n[bold green] Test Results[/bold green]")
        console.print(f"[green]Charts found: {len(charts)}[/green]")
        
        # Show unique aerodromes found
        unique_icao = set(chart.get('icao_code', 'Unknown') for chart in charts)
        console.print(f"[green]Unique aerodromes: {len(unique_icao)}[/green]")
        console.print(f"[cyan]ICAO codes: {', '.join(sorted(unique_icao))}[/cyan]")
        
        # Show cache stats
        cache_stats = scraper.get_cache_stats()
        console.print(f"[green]Section pages cached: {cache_stats['cached_pages']}[/green]")
        
        # Verify limit was respected
        if len(unique_icao) <= test_limit:
            console.print(f"[green] Limit respected: {len(unique_icao)} ≤ {test_limit} aerodromes[/green]")
        else:
            console.print(f"[red] Limit exceeded: {len(unique_icao)} > {test_limit} aerodromes[/red]")
        
        console.print(f"\n[bold cyan] Perfect for testing PDF generation![/bold cyan]")
        console.print(f"[cyan]Use: python -m src.main full-pipeline --limit {test_limit}[/cyan]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_limit_functionality()