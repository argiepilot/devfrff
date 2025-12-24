#!/usr/bin/env python3
"""Demo script to show the browser-like scraping behavior."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from src.scraper import AIPScraper

console = Console()


def demo_cache_scraper():
    """Demo the new browser-like scraping with limited scope."""
    console.print(Panel.fit(" Demo: Browser-Like Scraping with Caching", style="bold blue"))
    
    try:
        # Initialize scraper
        scraper = AIPScraper(rate_limit=1.0)  # Faster for demo
        
        # Get the main page to set up navigation
        console.print("\n[bold]Initial Setup: Getting section list[/bold]")
        html = scraper.get_aerodrome_list_page()
        sections = scraper.get_alphabetical_sections(html)
        
        if not sections:
            console.print("[red]No sections found![/red]")
            return
            
        # Demo with first 2 sections only (to keep it manageable)
        demo_sections = sections[:2]
        console.print(f"\n[cyan]Demo limited to {len(demo_sections)} sections for speed[/cyan]")
        
        all_charts = []
        total_aerodromes = 0
        
        # Process each section (simulating user clicking through sections)
        for section_name, section_url in demo_sections:
            console.print(f"\n[bold yellow] Processing section: {section_name}[/bold yellow]")
            
            # Get aerodromes in this section (with caching)
            aerodromes = scraper.get_aerodromes_from_section(section_url)
            console.print(f"[cyan]Found {len(aerodromes)} aerodromes in section {section_name}[/cyan]")
            total_aerodromes += len(aerodromes)
            
            if not aerodromes:
                console.print("[yellow]No aerodromes in this section, skipping...[/yellow]")
                continue
                
            # Demo: Process only first 3 airports per section
            demo_aerodromes = aerodromes[:3]
            console.print(f"[yellow]Demo: Processing only first {len(demo_aerodromes)} airports[/yellow]")
                
            # Process aerodromes in this section
            for i, (icao_code, aerodrome_name, page_url) in enumerate(demo_aerodromes, 1):
                console.print(f"\n[cyan]  {i}/{len(demo_aerodromes)}: Processing {icao_code} - {aerodrome_name}[/cyan]")
                
                try:
                    # Get aerodrome page (user clicks on airport)
                    aerodrome_html = scraper.get_aerodrome_page(page_url)
                    
                    # Extract chart information
                    charts = scraper.extract_chart_info(aerodrome_html, icao_code, aerodrome_name)
                    all_charts.extend(charts)
                    
                    console.print(f"    [green] {icao_code}: {len(charts)} charts found[/green]")
                    
                    # After processing airport, user would hit "back" to section
                    # Show that we would use cache for next airport in same section
                    if i < len(demo_aerodromes):
                        console.print(f"    [cyan] User hits 'back' - section page now cached[/cyan]")
                    
                except Exception as e:
                    console.print(f"    [red] {icao_code}: Error - {e}[/red]")
            
            # Show section summary
            console.print(f"[green] Section {section_name} completed: {len(demo_aerodromes)} airports processed[/green]")
        
        # Show final cache statistics
        cache_stats = scraper.get_cache_stats()
        console.print(f"\n[bold green] Demo Summary[/bold green]")
        console.print(f"[green]Sections processed: {len(demo_sections)}[/green]")
        console.print(f"[green]Airports processed: {sum(min(3, len(scraper.get_aerodromes_from_section(url))) for _, url in demo_sections)}[/green]")
        console.print(f"[green]Charts found: {len(all_charts)}[/green]")
        console.print(f"[green]Section pages cached: {cache_stats['cached_pages']}[/green]")
        console.print(f"[green]Cache size: {cache_stats['cache_size_kb']} KB[/green]")
        
        console.print(f"\n[bold cyan] Cache Benefit[/bold cyan]")
        console.print(f"[cyan]Without caching: Each airport would require fetching its section page[/cyan]")
        console.print(f"[cyan]With caching: Section pages are fetched once, reused for all airports in that section[/cyan]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    demo_cache_scraper()