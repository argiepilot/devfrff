"""Main CLI module for Germany VFR Approach Charts for ForeFlight."""

import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional

import typer
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


def _faa_pipeline(
    *,
    chart_type: str,
    output_dir: str,
    limit: Optional[int],
    min_zoom: int,
    max_zoom: int,
    verbose: bool,
    chart_type_label: str,
) -> List[dict]:
    """Run the FAA pipeline for a single chart type ("sectional" or "terminal")."""
    if chart_type not in {"sectional", "terminal"}:
        raise ValueError(f"Invalid FAA chart type: {chart_type}")

    faa_scraper = FAAScraper()
    mbtiles_converter = MBTilesConverter(
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        verbose=verbose,
    )

    # Create temporary directories
    temp_dir = Path(output_dir) / ".temp"
    download_dir = temp_dir / "downloads"
    extract_dir = temp_dir / "extracted"
    layers_dir = Path(output_dir) / "layers"

    try:
        charts = faa_scraper.scrape_charts(
            chart_types=[chart_type],
            limit=limit,
            verbose=verbose,
        )

        if not charts:
            console.print(f"[yellow]No {chart_type_label} charts found[/yellow]")
            return []

        charts_with_files = faa_scraper.download_and_extract_charts(
            charts,
            download_dir,
            extract_dir,
            verbose=verbose,
        )

        charts_with_mbtiles = mbtiles_converter.convert_batch(
            charts_with_files,
            layers_dir,
            chart_type_label=chart_type_label,
        )

        return charts_with_mbtiles
    finally:
        # Clean up temp directories
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                console.print(f"[yellow]Could not clean up temp directory: {e}[/yellow]")


@app.command()
def process_faa_sectional(
    output_dir: str = typer.Option(
        "VFR Charts Package",
        "--output-dir",
        "-d",
        help="Output directory for BYOP package",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of FAA charts to process (for testing)",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help="Faster run: reduce max zoom to 9 (unless --max-zoom is provided)",
    ),
    min_zoom: int = typer.Option(6, "--min-zoom", help="Minimum zoom level"),
    max_zoom: Optional[int] = typer.Option(
        None, "--max-zoom", help="Maximum zoom level (default: 12, or 9 if --quick)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose output with detailed progress information"
    ),
) -> None:
    """Process FAA Sectional charts into MBTiles (layers/)."""
    resolved_max_zoom = 9 if (quick and max_zoom is None) else (max_zoom or 12)

    console.print("\n[bold cyan]Processing FAA Sectional Charts...[/bold cyan]")
    charts_with_mbtiles = _faa_pipeline(
        chart_type="sectional",
        output_dir=output_dir,
        limit=limit,
        min_zoom=min_zoom,
        max_zoom=resolved_max_zoom,
        verbose=verbose,
        chart_type_label="Sectional charts",
    )
    console.print(
        f"[green]✓[/green] Processed {len(charts_with_mbtiles)} FAA Sectional charts"
    )


@app.command()
def process_faa_terminal(
    output_dir: str = typer.Option(
        "VFR Charts Package",
        "--output-dir",
        "-d",
        help="Output directory for BYOP package",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of FAA charts to process (for testing)",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help="Faster run: reduce max zoom to 9 (unless --max-zoom is provided)",
    ),
    min_zoom: int = typer.Option(6, "--min-zoom", help="Minimum zoom level"),
    max_zoom: Optional[int] = typer.Option(
        None, "--max-zoom", help="Maximum zoom level (default: 12, or 9 if --quick)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose output with detailed progress information"
    ),
) -> None:
    """Process FAA Terminal Area charts into MBTiles (layers/)."""
    resolved_max_zoom = 9 if (quick and max_zoom is None) else (max_zoom or 12)

    console.print("\n[bold cyan]Processing FAA Terminal Area Charts...[/bold cyan]")
    charts_with_mbtiles = _faa_pipeline(
        chart_type="terminal",
        output_dir=output_dir,
        limit=limit,
        min_zoom=min_zoom,
        max_zoom=resolved_max_zoom,
        verbose=verbose,
        chart_type_label="Terminal charts",
    )
    console.print(
        f"[green]✓[/green] Processed {len(charts_with_mbtiles)} FAA Terminal Area charts"
    )


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
    include_dfs: bool = typer.Option(
        True, "--dfs/--no-dfs", help="Include DFS (Germany) PDF charts"
    ),
    include_faa_sectional: bool = typer.Option(
        True,
        "--faa-sectional/--no-faa-sectional",
        help="Include FAA Sectional charts (MBTiles)",
    ),
    include_faa_terminal: bool = typer.Option(
        True,
        "--faa-terminal/--no-faa-terminal",
        help="Include FAA Terminal Area charts (MBTiles)",
    ),
    faa_quick: bool = typer.Option(
        False,
        "--faa-quick",
        help="Faster FAA conversions: reduce max zoom to 9 (unless --faa-max-zoom is set)",
    ),
    faa_min_zoom: int = typer.Option(6, "--faa-min-zoom", help="FAA min zoom level"),
    faa_max_zoom: Optional[int] = typer.Option(
        None,
        "--faa-max-zoom",
        help="FAA max zoom level (default: 12, or 9 if --faa-quick)",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose output with detailed progress information"
    ),
) -> None:
    """Process all chart sources into a unified BYOP package (DFS + FAA by default)."""
    console.print("[bold cyan]Processing selected chart sources into unified BYOP package...[/bold cyan]")

    if not (include_dfs or include_faa_sectional or include_faa_terminal):
        raise typer.BadParameter("Nothing selected. Enable at least one source.")

    selected_sources: List[str] = []
    if include_dfs:
        selected_sources.append("DFS")
    if include_faa_sectional:
        selected_sources.append("FAA Sectional")
    if include_faa_terminal:
        selected_sources.append("FAA Terminal")

    console.print(f"\n[green]Selected sources: {', '.join(selected_sources)}[/green]")

    try:
        # Initialize packager
        packager = BYOPPackager(output_dir)
        for source in selected_sources:
            packager.add_source(source)

        # Process DFS charts
        if include_dfs:
            console.print("\n[bold cyan]Processing DFS Charts...[/bold cyan]")
            console.print(
                "[yellow]ℹ️  Note: Delays are added between airports to mimic human browsing behavior "
                "and avoid overloading the server[/yellow]"
            )
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
        if include_faa_sectional:
            resolved_max_zoom = 9 if (faa_quick and faa_max_zoom is None) else (faa_max_zoom or 12)
            console.print("\n[bold cyan]Processing FAA Sectional Charts...[/bold cyan]")
            charts_with_mbtiles = _faa_pipeline(
                chart_type="sectional",
                output_dir=output_dir,
                limit=limit_faa,
                min_zoom=faa_min_zoom,
                max_zoom=resolved_max_zoom,
                verbose=verbose,
                chart_type_label="Sectional charts",
            )
            console.print(
                f"[green]✓[/green] Processed {len(charts_with_mbtiles)} FAA Sectional charts"
            )

        # Process FAA Terminal Area charts
        if include_faa_terminal:
            resolved_max_zoom = 9 if (faa_quick and faa_max_zoom is None) else (faa_max_zoom or 12)
            console.print("\n[bold cyan]Processing FAA Terminal Area Charts...[/bold cyan]")
            charts_with_mbtiles = _faa_pipeline(
                chart_type="terminal",
                output_dir=output_dir,
                limit=limit_faa,
                min_zoom=faa_min_zoom,
                max_zoom=resolved_max_zoom,
                verbose=verbose,
                chart_type_label="Terminal charts",
            )
            console.print(
                f"[green]✓[/green] Processed {len(charts_with_mbtiles)} FAA Terminal Area charts"
            )

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
            "• process-all: Process DFS + FAA into unified package (defaults to all)\n"
            "• process-faa-sectional: Build only FAA sectional MBTiles\n"
            "• process-faa-terminal: Build only FAA terminal MBTiles\n"
            "• info: Show this information",
            style="bold blue",
        )
    )


if __name__ == "__main__":
    app()
