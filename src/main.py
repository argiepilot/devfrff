"""Main CLI module for Germany VFR Approach Charts for ForeFlight."""

import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from byop_packager import (DEFAULT_PACKAGE_DIR_NAMES, BYOPPackager,
                           clean_package_directories, format_bytes,
                           resolve_package_directories)
from faa_scraper import FAAScraper
from mbtiles_converter import MBTilesConverter
from pdf_generator import PDFGenerator
from scraper import AIPScraper

console = Console()
app = typer.Typer(help="VFR Charts from Germany and the USA for ForeFlight BYOP")


def _dfs_pipeline(
    *,
    output_dir: str,
    limit: Optional[int],
    airport_pause: float,
    section_pause: float,
) -> Tuple[List[dict], Optional[str]]:
    """Scrape DFS aerodromes and write PDFs, with pauses between airports and sections."""
    console.print("\n[bold cyan]Processing DFS Charts...[/bold cyan]")
    console.print(
        "[yellow]Note: Delays are added between airports to mimic human browsing behavior "
        "and avoid overloading the server[/yellow]"
    )
    scraper = AIPScraper()
    pdf_generator = PDFGenerator(output_dir)
    charts = scraper.scrape_and_process_aerodromes(
        pdf_generator=pdf_generator,
        limit_aerodromes=limit,
        airport_pause=airport_pause,
        section_pause=section_pause,
    )
    current_date = getattr(scraper, "current_date", None)
    if current_date:
        pdf_generator.current_date = current_date
    if limit:
        console.print(f"[yellow]Limited to first {limit} aerodromes[/yellow]")
    return charts, current_date


@app.command()
def process_dfs(
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
        help="Testing only: process the first N aerodromes instead of the full catalog",
    ),
    airport_pause: float = typer.Option(
        5.0, "--airport-pause", help="Pause between airports in seconds"
    ),
    section_pause: float = typer.Option(
        15.0, "--section-pause", help="Pause between letter sections in seconds"
    ),
) -> None:
    """Process DFS (Germany) PDF charts into a BYOP package."""
    console.print(Panel.fit("DFS (Germany) PDF charts", style="bold blue"))

    try:
        packager = BYOPPackager(output_dir)
        packager.add_source("DFS")
        _charts, current_date = _dfs_pipeline(
            output_dir=output_dir,
            limit=limit,
            airport_pause=airport_pause,
            section_pause=section_pause,
        )
        if current_date:
            packager.set_version(current_date)
        else:
            packager.set_version(datetime.now().strftime("%Y%b%d").upper())

        manifest_path = packager.create_manifest()
        packager.display_summary()

        console.print(
            "\n[bold green]DFS processing completed successfully![/bold green]"
        )
        console.print(f"[green]BYOP content pack ready in: {output_dir}[/green]")
        if manifest_path:
            console.print(f"[green]Manifest created: {manifest_path}[/green]")

    except Exception as e:
        console.print(f"[red]Error during DFS processing: {e}[/red]")
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
                console.print(
                    f"[yellow]Could not clean up temp directory: {e}[/yellow]"
                )


def _prompt_process_all_sources() -> tuple[bool, bool, bool]:
    """Prompt y/n for sources when running process-all interactively (defaults to Yes)."""
    console.print("\n[bold cyan]Select sources to include:[/bold cyan]")
    include_dfs = Confirm.ask("  Include DFS (Germany) PDFs?", default=True)
    include_faa_sectional = Confirm.ask(
        "  Include FAA Sectional (MBTiles)?", default=True
    )
    include_faa_terminal = Confirm.ask(
        "  Include FAA Terminal Area (MBTiles)?", default=True
    )
    return include_dfs, include_faa_sectional, include_faa_terminal


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
        help="Testing only: process the first N charts instead of the full catalog",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help="Testing only: reduce max zoom to 9 (unless --max-zoom is provided)",
    ),
    min_zoom: int = typer.Option(6, "--min-zoom", help="Minimum zoom level"),
    max_zoom: Optional[int] = typer.Option(
        None, "--max-zoom", help="Maximum zoom level (default: 12, or 9 if --quick)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output with detailed progress information",
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
        f"[green]Processed:[/green] {len(charts_with_mbtiles)} FAA Sectional charts"
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
        help="Testing only: process the first N charts instead of the full catalog",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help="Testing only: reduce max zoom to 9 (unless --max-zoom is provided)",
    ),
    min_zoom: int = typer.Option(6, "--min-zoom", help="Minimum zoom level"),
    max_zoom: Optional[int] = typer.Option(
        None, "--max-zoom", help="Maximum zoom level (default: 12, or 9 if --quick)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output with detailed progress information",
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
        f"[green]Processed:[/green] {len(charts_with_mbtiles)} FAA Terminal Area charts"
    )


@app.command()
def process_all(
    output_dir: str = typer.Option(
        "VFR Charts Package",
        "--output-dir",
        "-d",
        help="Output directory for BYOP package",
    ),
    limit_dfs: Optional[int] = typer.Option(
        None,
        "--limit-dfs",
        help="Testing only: process the first N DFS aerodromes instead of the full catalog",
    ),
    limit_faa: Optional[int] = typer.Option(
        None,
        "--limit-faa",
        help="Testing only: process the first N FAA charts per type instead of the full catalog",
    ),
    airport_pause: float = typer.Option(
        5.0, "--airport-pause", help="Pause between DFS airports in seconds"
    ),
    section_pause: float = typer.Option(
        15.0, "--section-pause", help="Pause between DFS letter sections in seconds"
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Ask y/n questions for which sources to include (defaults to Yes)",
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
        help="Testing only: reduce FAA max zoom to 9 (unless --faa-max-zoom is set)",
    ),
    faa_min_zoom: int = typer.Option(6, "--faa-min-zoom", help="FAA min zoom level"),
    faa_max_zoom: Optional[int] = typer.Option(
        None,
        "--faa-max-zoom",
        help="FAA max zoom level (default: 12, or 9 if --faa-quick)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output with detailed progress information",
    ),
) -> None:
    """Process all chart sources into a unified BYOP package (DFS + FAA by default)."""
    console.print(
        "[bold cyan]Processing selected chart sources into unified BYOP package...[/bold cyan]"
    )

    if interactive:
        include_dfs, include_faa_sectional, include_faa_terminal = (
            _prompt_process_all_sources()
        )

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

        if include_dfs:
            dfs_charts, current_date = _dfs_pipeline(
                output_dir=output_dir,
                limit=limit_dfs,
                airport_pause=airport_pause,
                section_pause=section_pause,
            )
            if current_date:
                packager.set_version(current_date)
            console.print(f"[green]Processed:[/green] {len(dfs_charts)} DFS charts")

        # Process FAA Sectional charts
        if include_faa_sectional:
            resolved_max_zoom = (
                9 if (faa_quick and faa_max_zoom is None) else (faa_max_zoom or 12)
            )
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
                f"[green]Processed:[/green] {len(charts_with_mbtiles)} FAA Sectional charts"
            )

        # Process FAA Terminal Area charts
        if include_faa_terminal:
            resolved_max_zoom = (
                9 if (faa_quick and faa_max_zoom is None) else (faa_max_zoom or 12)
            )
            console.print(
                "\n[bold cyan]Processing FAA Terminal Area Charts...[/bold cyan]"
            )
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
                f"[green]Processed:[/green] {len(charts_with_mbtiles)} FAA Terminal Area charts"
            )

        # Set version if not set (e.g., if only FAA charts were processed)
        if not packager.version:
            packager.set_version(datetime.now().strftime("%Y%b%d").upper())

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
def clean(
    directories: Optional[List[str]] = typer.Argument(
        None,
        help=(
            "Package directories or zip files to remove. Defaults to "
            f"{', '.join(repr(name) for name in DEFAULT_PACKAGE_DIR_NAMES)} "
            "and their sibling .zip files."
        ),
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without deleting"
    ),
) -> None:
    """Remove generated BYOP packages to free disk space after install."""
    console.print(Panel.fit(" Clean generated BYOP packages", style="bold blue"))

    names = directories if directories else None
    package_dirs = resolve_package_directories(names)

    # Preview with dry_run so we can confirm before deleting.
    preview = clean_package_directories(package_dirs, dry_run=True)
    removable = [result for result in preview if result.skipped_reason is None]
    skipped = [result for result in preview if result.skipped_reason is not None]

    if skipped:
        for result in skipped:
            console.print(
                f"[yellow]Skipping {result.path}: {result.skipped_reason}[/yellow]"
            )

    if not removable:
        console.print("[yellow]No generated BYOP packages found to remove.[/yellow]")
        return

    table = Table(title="Items to remove")
    table.add_column("Path", style="cyan")
    table.add_column("Size", style="green", justify="right")
    total_bytes = 0
    for result in removable:
        table.add_row(str(result.path), format_bytes(result.size_bytes))
        total_bytes += result.size_bytes
    console.print(table)
    console.print(f"[bold]Total:[/bold] {format_bytes(total_bytes)}")

    if dry_run:
        console.print("[yellow]Dry run: nothing was deleted.[/yellow]")
        return

    if not yes:
        if not sys.stdin.isatty():
            console.print(
                "[red]Refusing to delete without --yes in non-interactive mode.[/red]"
            )
            raise typer.Exit(1)
        if not Confirm.ask(
            "Delete these files and directories? This cannot be undone.",
            default=False,
        ):
            console.print("[yellow]Cancelled. Nothing was deleted.[/yellow]")
            raise typer.Exit(0)

    results = clean_package_directories(
        [result.path for result in removable], dry_run=False
    )
    freed_bytes = 0
    failed = False
    for result in results:
        if result.removed:
            console.print(
                f"[green]Removed:[/green] {result.path} "
                f"({format_bytes(result.size_bytes)})"
            )
            freed_bytes += result.size_bytes
        else:
            failed = True
            reason = result.skipped_reason or "unknown error"
            console.print(f"[red]Failed to remove {result.path}: {reason}[/red]")

    if freed_bytes:
        console.print(f"\n[bold green]Freed {format_bytes(freed_bytes)}[/bold green]")

    if failed:
        raise typer.Exit(1)


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
            "• process-all: DFS + FAA into one package (default when you omit a command)\n"
            "• process-dfs: DFS (Germany) PDFs only\n"
            "• process-faa-sectional: FAA sectional MBTiles only\n"
            "• process-faa-terminal: FAA terminal MBTiles only\n"
            "• clean: Remove generated BYOP packages to free disk space\n"
            "• info: Show this information",
            style="bold blue",
        )
    )


if __name__ == "__main__":
    app()
