"""Main CLI module for Germany VFR Approach Charts for ForeFlight."""

import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.prompt import Confirm
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pdf_generator import PDFGenerator
from scraper import AIPScraper
from faa_scraper import FAAScraper
from mbtiles_converter import MBTilesConverter
from byop_packager import BYOPPackager

console = Console()
app = typer.Typer(help="Germany VFR Approach Charts for ForeFlight BYOP")


@app.command()
def scrape(
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output JSON file for chart data"
    ),
    display_summary: bool = typer.Option(
        True, "--summary", "-s", help="Display summary of found charts"
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of aerodromes to process (for testing)",
    ),
) -> None:
    """Scrape aerodrome charts from DFS AIP site."""
    console.print(Panel.fit("🔍 Scraping DFS AIP VFR Charts", style="bold blue"))

    try:
        scraper = AIPScraper()
        charts = scraper.scrape_all_aerodromes(limit_aerodromes=limit)

        if limit:
            console.print(f"[yellow]Limited to first {limit} aerodromes[/yellow]")

        if display_summary:
            scraper.display_charts_summary(charts)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(charts, f, indent=2, ensure_ascii=False)
            console.print(f"[green]Chart data saved to: {output_file}[/green]")

        console.print(
            f"[bold green]✓ Scraping completed! Found {len(charts)} charts[/bold green]"
        )

    except Exception as e:
        console.print(f"[red]Error during scraping: {e}[/red]")
        sys.exit(1)


@app.command()
def download(
    charts_file: Path = typer.Argument(..., help="JSON file with chart data"),
    output_dir: str = typer.Option(
        "AIP Germany", "--output-dir", "-d", help="Output directory for PDFs"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Limit number of charts to process"
    ),
) -> None:
    """Download charts and generate PDFs for ForeFlight BYOP."""
    console.print(
        Panel.fit("📥 Downloading Charts & Generating PDFs", style="bold blue")
    )

    try:
        # Load chart data
        with open(charts_file, "r", encoding="utf-8") as f:
            charts = json.load(f)

        if limit:
            charts = charts[:limit]
            console.print(f"[yellow]Limited to {limit} charts[/yellow]")

        # Initialize components
        scraper = AIPScraper()
        pdf_generator = PDFGenerator(output_dir)

        # Download charts and generate PDFs
        charts_with_images = []

        with console.status("[bold green]Downloading chart images...") as status:
            for i, chart in enumerate(charts, 1):
                status.update(f"Downloading {i}/{len(charts)}: {chart['icao_code']}")

                # Build full referrer URL from the chart page URL
                # The page_url is relative like "../pages/ID.html", need to build the full URL
                if chart.get("page_url") and hasattr(scraper, "current_date"):
                    # Convert relative path to absolute
                    page_href = chart["page_url"].replace("../", "")
                    referrer_url = f"{scraper.base_url}/BasicVFR/{scraper.current_date}/{page_href}"
                else:
                    referrer_url = None
                image_data = scraper.download_chart_image(
                    chart["print_url"], referrer_url
                )
                if image_data:
                    charts_with_images.append((chart, image_data))
                    console.print(
                        f"[green]✓[/green] Downloaded: {chart['icao_code']} - {chart['chart_name']}"
                    )
                else:
                    console.print(
                        f"[red]✗[/red] Failed: {chart['icao_code']} - {chart['chart_name']}"
                    )

        # Generate PDFs
        if charts_with_images:
            pdf_generator.process_charts_batch(charts_with_images)

            # Create manifest.json (without current_date for download command)
            manifest_path = pdf_generator.create_manifest()

            # Display summary
            summary = pdf_generator.get_generated_files_summary()
            display_download_summary(summary, len(charts), len(charts_with_images))
            
            if manifest_path:
                console.print(f"[green]Manifest created: {manifest_path}[/green]")
        else:
            console.print("[red]No charts were successfully downloaded[/red]")

    except FileNotFoundError:
        console.print(f"[red]Chart data file not found: {charts_file}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error during download: {e}[/red]")
        sys.exit(1)


@app.command()
def full_pipeline(
    output_dir: str = typer.Option(
        "AIP Germany", "--output-dir", "-d", help="Output directory for PDFs"
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of aerodromes to process (for testing)",
    ),
    save_charts: bool = typer.Option(
        True, "--save-charts", help="Save chart data to JSON file"
    ),
) -> None:
    """Run complete pipeline: scrape, download, and generate PDFs."""
    console.print(
        Panel.fit(
            "🚀 Full Pipeline: Scrape → Download → Generate PDFs", style="bold blue"
        )
    )

    try:
        # Step 1: Scrape
        console.print("\n[bold cyan]Step 1: Scraping aerodrome charts...[/bold cyan]")
        scraper = AIPScraper()
        charts = scraper.scrape_all_aerodromes(limit_aerodromes=limit)

        if limit:
            console.print(f"[yellow]Limited to first {limit} aerodromes[/yellow]")

        # Save chart data if requested
        if save_charts:
            charts_file = Path("charts_data.json")
            with open(charts_file, "w", encoding="utf-8") as f:
                json.dump(charts, f, indent=2, ensure_ascii=False)
            console.print(f"[green]Chart data saved to: {charts_file}[/green]")

        # Step 2: Download and generate PDFs
        console.print(
            "\n[bold cyan]Step 2: Downloading charts and generating PDFs...[/bold cyan]"
        )
        pdf_generator = PDFGenerator(output_dir, current_date=scraper.current_date if hasattr(scraper, 'current_date') else None)

        charts_with_images = []
        with console.status("[bold green]Downloading chart images...") as status:
            for i, chart in enumerate(charts, 1):
                status.update(f"Downloading {i}/{len(charts)}: {chart['icao_code']}")

                # Build full referrer URL from the chart page URL
                # The page_url is relative like "../pages/ID.html", need to build the full URL
                if chart.get("page_url") and hasattr(scraper, "current_date"):
                    # Convert relative path to absolute
                    page_href = chart["page_url"].replace("../", "")
                    referrer_url = f"{scraper.base_url}/BasicVFR/{scraper.current_date}/{page_href}"
                else:
                    referrer_url = None
                image_data = scraper.download_chart_image(
                    chart["print_url"], referrer_url
                )
                if image_data:
                    charts_with_images.append((chart, image_data))
                    console.print(
                        f"[green]✓[/green] Downloaded: {chart['icao_code']} - {chart['chart_name']}"
                    )
                else:
                    console.print(
                        f"[red]✗[/red] Failed: {chart['icao_code']} - {chart['chart_name']}"
                    )

        # Generate PDFs
        if charts_with_images:
            pdf_generator.process_charts_batch(charts_with_images)

            # Create manifest.json
            manifest_path = pdf_generator.create_manifest()

            # Display final summary
            summary = pdf_generator.get_generated_files_summary()
            display_download_summary(summary, len(charts), len(charts_with_images))

            console.print(
                "\n[bold green]🎉 Pipeline completed successfully![/bold green]"
            )
            console.print(f"[green]BYOP content pack ready in: {output_dir}[/green]")
            if manifest_path:
                console.print(f"[green]Manifest created: {manifest_path}[/green]")
        else:
            console.print("[red]No charts were successfully processed[/red]")

    except Exception as e:
        console.print(f"[red]Error during pipeline: {e}[/red]")
        sys.exit(1)


def display_download_summary(
    summary: dict, total_charts: int, successful_downloads: int
) -> None:
    """Display a summary of the download and generation process."""
    table = Table(title="📊 Download & Generation Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Total charts found", str(total_charts))
    table.add_row("Successfully downloaded", str(successful_downloads))
    table.add_row("PDFs generated", str(summary["total_pdfs"]))
    table.add_row("Success rate", f"{(successful_downloads/total_charts*100):.1f}%")

    console.print(table)


@app.command()
def process_realistic(
    output_dir: str = typer.Option(
        "AIP Germany", "--output-dir", "-d", help="Output directory for PDFs"
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of aerodromes to process (for testing)",
    ),
    airport_pause: float = typer.Option(
        5.0, "--airport-pause", help="Pause between airports in seconds"
    ),
    section_pause: float = typer.Option(
        15.0, "--section-pause", help="Pause between letter sections in seconds"
    ),
) -> None:
    """Process aerodromes like a real user: airport → charts → PDFs → next airport."""
    console.print(
        Panel.fit(
            "🛩️ Realistic Processing: Airport → Charts → PDFs → Next Airport", 
            style="bold blue"
        )
    )

    try:
        # Initialize scraper and PDF generator
        scraper = AIPScraper()
        pdf_generator = PDFGenerator(output_dir)

        # Process aerodromes with immediate PDF generation
        charts = scraper.scrape_and_process_aerodromes(
            pdf_generator=pdf_generator,
            limit_aerodromes=limit,
            airport_pause=airport_pause,
            section_pause=section_pause
        )

        if limit:
            console.print(f"[yellow]Limited to first {limit} aerodromes[/yellow]")

        # Update PDF generator with current_date after scraper has extracted it
        if hasattr(scraper, 'current_date') and scraper.current_date:
            pdf_generator.current_date = scraper.current_date

        # Create manifest.json
        manifest_path = pdf_generator.create_manifest()

        # Display final summary
        summary = pdf_generator.get_generated_files_summary()
        display_download_summary(summary, len(charts), len(charts))

        console.print(
            "\n[bold green]🎉 Realistic processing completed successfully![/bold green]"
        )
        console.print(f"[green]BYOP content pack ready in: {output_dir}[/green]")
        if manifest_path:
            console.print(f"[green]Manifest created: {manifest_path}[/green]")

    except Exception as e:
        console.print(f"[red]Error during realistic processing: {e}[/red]")
        sys.exit(1)


def prompt_source_selection() -> List[str]:
    """Prompt user to select chart sources.

    Returns:
        List of selected source names
    """
    console.print("\n[bold cyan]Select chart sources to process:[/bold cyan]")
    
    selected_sources = []
    
    # DFS
    if Confirm.ask("  Include DFS (Germany) charts?", default=True):
        selected_sources.append("DFS")
    
    # FAA Sectional
    if Confirm.ask("  Include FAA Sectional charts?", default=False):
        selected_sources.append("FAA Sectional")
    
    # FAA Terminal Area
    if Confirm.ask("  Include FAA Terminal Area charts?", default=False):
        selected_sources.append("FAA Terminal")
    
    if not selected_sources:
        console.print("[yellow]No sources selected. Exiting.[/yellow]")
        sys.exit(0)
    
    return selected_sources


@app.command()
def process_all(
    output_dir: str = typer.Option(
        "VFR Charts Package", "--output-dir", "-d", help="Output directory for BYOP package"
    ),
    limit_dfs: Optional[int] = typer.Option(
        None, "--limit-dfs", help="Limit number of DFS aerodromes to process"
    ),
    limit_faa: Optional[int] = typer.Option(
        None, "--limit-faa", help="Limit number of FAA charts per type to process"
    ),
    airport_pause: float = typer.Option(
        5.0, "--airport-pause", help="Pause between DFS airports in seconds"
    ),
    section_pause: float = typer.Option(
        15.0, "--section-pause", help="Pause between DFS letter sections in seconds"
    ),
    test_terminal: bool = typer.Option(
        False, "--test-terminal", help="Test mode: process only first Terminal Area chart"
    ),
    test_terminal_quick: bool = typer.Option(
        False,
        "--test-terminal-quick",
        help="Test mode: first Terminal Area chart with reduced zoom levels",
    ),
) -> None:
    """Process selected chart sources into unified BYOP package."""
    console.print("[bold cyan]Processing selected chart sources into unified BYOP package...[/bold cyan]")

    # Prompt for source selection (skip if a test terminal mode is active)
    if test_terminal and test_terminal_quick:
        raise typer.BadParameter("Use only one of --test-terminal or --test-terminal-quick")

    if test_terminal or test_terminal_quick:
        selected_sources = ["FAA Terminal"]
        console.print("[yellow]TEST MODE: Only processing Terminal Area charts[/yellow]")
        if test_terminal_quick:
            console.print("[yellow]QUICK MODE: Using reduced zoom levels for faster conversion[/yellow]")
    else:
        selected_sources = prompt_source_selection()
    
    console.print(f"\n[green]Selected sources: {', '.join(selected_sources)}[/green]")

    try:
        # Initialize packager
        packager = BYOPPackager(output_dir)
        for source in selected_sources:
            packager.add_source(source)

        # Process DFS charts
        if "DFS" in selected_sources:
            console.print("\n[bold cyan]Processing DFS Charts...[/bold cyan]")
            dfs_scraper = AIPScraper()
            dfs_pdf_generator = PDFGenerator(output_dir)
            
            # Process aerodromes
            dfs_charts = dfs_scraper.scrape_and_process_aerodromes(
                pdf_generator=dfs_pdf_generator,
                limit_aerodromes=limit_dfs,
                airport_pause=airport_pause,
                section_pause=section_pause
            )
            
            # Update PDF generator with current_date
            if hasattr(dfs_scraper, 'current_date') and dfs_scraper.current_date:
                dfs_pdf_generator.current_date = dfs_scraper.current_date
                packager.set_version(dfs_scraper.current_date)
            
            console.print(f"[green]✓[/green] Processed {len(dfs_charts)} DFS charts")

        # Process FAA Sectional charts
        if "FAA Sectional" in selected_sources:
            console.print("\n[bold cyan]Processing FAA Sectional Charts...[/bold cyan]")
            faa_scraper = FAAScraper()
            mbtiles_converter = MBTilesConverter()
            
            # Create temporary directories
            temp_dir = Path(output_dir) / ".temp"
            download_dir = temp_dir / "downloads"
            extract_dir = temp_dir / "extracted"
            layers_dir = Path(output_dir) / "layers"
            
            try:
                # Scrape charts
                sectional_charts = faa_scraper.scrape_charts(
                    chart_types=["sectional"],
                    limit=limit_faa
                )
                
                if not sectional_charts:
                    console.print("[yellow]No Sectional charts found[/yellow]")
                else:
                    # Download and extract
                    charts_with_files = faa_scraper.download_and_extract_charts(
                        sectional_charts,
                        download_dir,
                        extract_dir
                    )
                    
                    # Convert to mbtiles
                    charts_with_mbtiles = mbtiles_converter.convert_batch(
                        charts_with_files,
                        layers_dir
                    )
                    
                    console.print(f"[green]✓[/green] Processed {len(charts_with_mbtiles)} FAA Sectional charts")
            finally:
                # Clean up temp directories
                if temp_dir.exists():
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception as e:
                        console.print(f"[yellow]Could not clean up temp directory: {e}[/yellow]")

        # Process FAA Terminal Area charts
        if "FAA Terminal" in selected_sources or test_terminal or test_terminal_quick:
            console.print("\n[bold cyan]Processing FAA Terminal Area Charts...[/bold cyan]")
            if test_terminal:
                console.print("[yellow]TEST MODE: Processing only first Terminal Area chart[/yellow]")
            if test_terminal_quick:
                console.print("[yellow]TEST QUICK MODE: First Terminal chart at reduced zoom[/yellow]")
            faa_scraper = FAAScraper()
            if test_terminal_quick:
                # Lower max zoom to speed up test conversions
                mbtiles_converter = MBTilesConverter(min_zoom=6, max_zoom=10)
            else:
                mbtiles_converter = MBTilesConverter()
            
            # Create temporary directories
            temp_dir = Path(output_dir) / ".temp"
            download_dir = temp_dir / "downloads"
            extract_dir = temp_dir / "extracted"
            layers_dir = Path(output_dir) / "layers"
            
            try:
                # Scrape charts
                terminal_charts = faa_scraper.scrape_charts(
                    chart_types=["terminal"],
                    limit=1 if (test_terminal or test_terminal_quick) else limit_faa
                )
                
                if not terminal_charts:
                    console.print("[yellow]No Terminal Area charts found[/yellow]")
                else:
                    # Download and extract
                    charts_with_files = faa_scraper.download_and_extract_charts(
                        terminal_charts,
                        download_dir,
                        extract_dir
                    )
                    
                    # Convert to mbtiles
                    charts_with_mbtiles = mbtiles_converter.convert_batch(
                        charts_with_files,
                        layers_dir
                    )
                    
                    console.print(f"[green]✓[/green] Processed {len(charts_with_mbtiles)} FAA Terminal Area charts")
            finally:
                # Clean up temp directories
                if temp_dir.exists():
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception as e:
                        console.print(f"[yellow]Could not clean up temp directory: {e}[/yellow]")

        # Set version if not set (e.g., if only FAA charts were processed)
        if not packager.version:
            from datetime import datetime
            current_date = datetime.now().strftime("%Y%b%d").upper()
            packager.set_version(current_date)
        
        # Create unified manifest
        console.print("\n[bold cyan]Creating unified BYOP package...[/bold cyan]")
        manifest_path = packager.create_manifest()
        
        # Display summary
        packager.display_summary()

        console.print(
            "\n[bold green]Unified processing completed successfully![/bold green]"
        )
        console.print(f"[green]BYOP content pack ready in: {output_dir}[/green]")
        if manifest_path:
            console.print(f"[green]Manifest created: {manifest_path}[/green]")

    except Exception as e:
        console.print(f"[red]Error during unified processing: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
        sys.exit(1)


@app.command()
def info() -> None:
    """Display information about the tool."""
    console.print(
        Panel.fit(
            "VFR Charts for ForeFlight BYOP\n\n"
            "This tool scrapes VFR charts from multiple sources:\n"
            "• DFS AIP (Germany) - PDF charts\n"
            "• FAA Sectional Charts - mbtiles format\n"
            "• FAA Terminal Area Charts - mbtiles format\n\n"
            "Commands:\n"
            "• scrape: Extract chart information from DFS AIP\n"
            "• download: Download charts and generate PDFs\n"
            "• full-pipeline: Run complete DFS workflow\n"
            "• process-realistic: Process DFS like real user\n"
            "• process-all: Process selected sources into unified package\n"
            "• info: Show this information",
            style="bold blue",
        )
    )


if __name__ == "__main__":
    app()
