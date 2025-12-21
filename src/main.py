"""Main CLI module for Germany VFR Approach Charts for ForeFlight."""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pdf_generator import PDFGenerator
from scraper import AIPScraper

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


@app.command()
def info() -> None:
    """Display information about the tool."""
    console.print(
        Panel.fit(
            "Germany VFR Approach Charts for ForeFlight BYOP\n\n"
            "This tool scrapes VFR aerodrome charts from the DFS AIP site\n"
            "and generates PDF files suitable for ForeFlight BYOP content packs.\n\n"
            "Commands:\n"
            "• scrape: Extract chart information from DFS AIP\n"
            "• download: Download charts and generate PDFs\n"
            "• full-pipeline: Run complete workflow\n"
            "• process-realistic: Process like real user (immediate PDFs)\n"
            "• info: Show this information",
            style="bold blue",
        )
    )


if __name__ == "__main__":
    app()
