"""Web scraper for FAA VFR Raster Charts."""

import re
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class FAAScraper:
    """Scraper for FAA VFR Raster Charts."""

    def __init__(self, base_url: str = "https://www.faa.gov", rate_limit: float = 1.0):
        """Initialize the FAA scraper.

        Args:
            base_url: Base URL for the FAA website
            rate_limit: Minimum delay between requests in seconds (default: 1.0)
        """
        self.base_url = base_url
        self.rate_limit = rate_limit
        self.last_request_time = 0

        # Set up session with proper headers
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def _make_request(
        self, url: str, method: str = "get", **kwargs
    ) -> requests.Response:
        """Make an HTTP request with rate limiting and retries.

        Args:
            url: The URL to request
            method: HTTP method (default: "get")
            **kwargs: Additional arguments for requests

        Returns:
            requests.Response: The response object
        """
        import random

        # Rate limiting: ensure minimum delay between requests
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last + random.uniform(0.5, 2.0)
            time.sleep(sleep_time)

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                kwargs.setdefault("timeout", 60)
                response = getattr(self.session, method.lower())(url, **kwargs)

                self.last_request_time = time.time()
                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                retry_count += 1

                if retry_count >= max_retries:
                    raise e

                console.print(
                    f"[yellow]Request failed, retrying ({retry_count}/{max_retries}): {e}[/yellow]"
                )
                delay = (2**retry_count) + random.uniform(1, 3)
                time.sleep(delay)

    def get_vfr_page(self) -> str:
        """Get the FAA VFR Raster Charts page."""
        url = "https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/"
        response = self._make_request(url)
        return response.text

    def extract_sectional_charts(self, html: str) -> List[Dict[str, str]]:
        """Extract Sectional chart information from the HTML page.

        Args:
            html: HTML content of the VFR page

        Returns:
            List of dictionaries with chart information
        """
        soup = BeautifulSoup(html, "html.parser")
        charts = []

        # Find the Sectional charts table
        # Look for the table with "Sectional Aeronautical Raster Charts" heading
        tables = soup.find_all("table")
        sectional_table = None

        for table in tables:
            # Check if this is the sectional table by looking for preceding text
            for prev in table.find_all_previous(string=True):
                if "Sectional Aeronautical Raster Charts" in prev or "__Sectional Aeronautical Raster Charts" in prev:
                    # Verify it's actually sectional by checking URLs in the table
                    all_links = table.find_all("a", href=True)
                    has_sectional_urls = any(
                        "/sectional-files/" in link.get("href", "").lower() 
                        for link in all_links
                    )
                    if has_sectional_urls:
                        sectional_table = table
                        break
            if sectional_table:
                break

        if not sectional_table:
            # Try alternative: look for table with URLs containing "sectional-files"
            for table in tables:
                headers = table.find_all("th")
                if any("Chart Name" in h.get_text() for h in headers):
                    # Check URLs in the table to verify it's sectional
                    all_links = table.find_all("a", href=True)
                    has_sectional_urls = any(
                        "/sectional-files/" in link.get("href", "").lower() 
                        for link in all_links
                    )
                    has_tac_urls = any(
                        "/tac-files/" in link.get("href", "").lower() 
                        for link in all_links
                    )
                    if has_sectional_urls and not has_tac_urls:
                        sectional_table = table
                        break

        if not sectional_table:
            console.print("[yellow]Could not find Sectional charts table[/yellow]")
            return charts

        # Extract rows from the table
        rows = sectional_table.find_all("tr")[1:]  # Skip header row

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            chart_name = cells[0].get_text(strip=True)
            if not chart_name:
                continue

            # Find GEO-TIFF link from Current Edition column (not Next Edition)
            # The Current Edition is in the second column (cells[1])
            geo_tiff_link = None
            current_edition_cell = cells[1] if len(cells) > 1 else None
            
            if current_edition_cell:
                # Look for links in the Current Edition cell
                links = current_edition_cell.find_all("a", href=True)
                for link in links:
                    link_text = link.get_text(strip=True)
                    href = link.get("href", "")
                    # Must be in sectional-files directory and be a zip file
                    if (
                        href.endswith(".zip") 
                        and "/sectional-files/" in href.lower()
                        and ("GEO-TIFF" in link_text.upper() or "GEO-Tiff" in link_text or "Geo-Tiff" in link_text or not link_text)
                    ):
                        geo_tiff_link = href
                        break
            
            # Fallback: search all links in row if not found in Current Edition cell
            if not geo_tiff_link:
                links = row.find_all("a", href=True)
                for link in links:
                    href = link.get("href", "")
                    # Must be in sectional-files directory
                    if href.endswith(".zip") and "/sectional-files/" in href.lower():
                        geo_tiff_link = href
                        break

            if geo_tiff_link:
                # Convert relative URL to absolute
                if not geo_tiff_link.startswith("http"):
                    geo_tiff_link = urljoin(self.base_url, geo_tiff_link)

                # Extract edition date from the Current Edition cell
                edition_date = None
                if current_edition_cell:
                    date_text = current_edition_cell.get_text(strip=True)
                    # Try to extract date pattern (e.g., "Nov 27 2025")
                    date_match = re.search(r"(\w+\s+\d+\s+\d{4})", date_text)
                    if date_match:
                        edition_date = date_match.group(1)

                charts.append(
                    {
                        "chart_name": chart_name,
                        "chart_type": "sectional",
                        "geo_tiff_url": geo_tiff_link,
                        "edition_date": edition_date,
                    }
                )

        return charts

    def extract_terminal_charts(self, html: str) -> List[Dict[str, str]]:
        """Extract Terminal Area chart information from the HTML page.

        Args:
            html: HTML content of the VFR page

        Returns:
            List of dictionaries with chart information
        """
        soup = BeautifulSoup(html, "html.parser")
        charts = []

        # Find the Terminal Area charts table
        tables = soup.find_all("table")
        terminal_table = None

        for table in tables:
            # Check if this is the terminal table by looking for preceding text
            for prev in table.find_all_previous(string=True):
                if "VFR Terminal Area Raster Charts" in prev or "__VFR Terminal Area Raster Charts" in prev:
                    # Verify it's actually terminal by checking URLs in the table
                    all_links = table.find_all("a", href=True)
                    has_tac_urls = any(
                        "/tac-files/" in link.get("href", "").lower() 
                        for link in all_links
                    )
                    if has_tac_urls:
                        terminal_table = table
                        break
            if terminal_table:
                break

        if not terminal_table:
            # Try alternative: look for table with URLs containing "tac-files"
            for table in tables:
                headers = table.find_all("th")
                if any("Chart Name" in h.get_text() for h in headers):
                    # Check URLs in the table to verify it's terminal
                    all_links = table.find_all("a", href=True)
                    has_tac_urls = any(
                        "/tac-files/" in link.get("href", "").lower() 
                        for link in all_links
                    )
                    has_sectional_urls = any(
                        "/sectional-files/" in link.get("href", "").lower() 
                        for link in all_links
                    )
                    if has_tac_urls and not has_sectional_urls:
                        terminal_table = table
                        break

        if not terminal_table:
            console.print("[yellow]Could not find Terminal Area charts table[/yellow]")
            return charts

        # Extract rows from the table
        rows = terminal_table.find_all("tr")[1:]  # Skip header row

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            chart_name = cells[0].get_text(strip=True)
            if not chart_name:
                continue

            # Find GEO-TIFF link from Current Edition column (not Next Edition)
            # The Current Edition is in the second column (cells[1])
            geo_tiff_link = None
            current_edition_cell = cells[1] if len(cells) > 1 else None
            
            if current_edition_cell:
                # Look for links in the Current Edition cell
                links = current_edition_cell.find_all("a", href=True)
                for link in links:
                    link_text = link.get_text(strip=True)
                    href = link.get("href", "")
                    # Must be in tac-files directory and be a zip file
                    if (
                        href.endswith(".zip") 
                        and "/tac-files/" in href.lower()
                        and ("GEO-TIFF" in link_text.upper() or "GEO-Tiff" in link_text or "Geo-Tiff" in link_text or not link_text)
                    ):
                        geo_tiff_link = href
                        break
            
            # Fallback: search all links in row if not found in Current Edition cell
            if not geo_tiff_link:
                links = row.find_all("a", href=True)
                for link in links:
                    href = link.get("href", "")
                    # Must be in tac-files directory
                    if href.endswith(".zip") and "/tac-files/" in href.lower():
                        geo_tiff_link = href
                        break

            if geo_tiff_link:
                # Convert relative URL to absolute
                if not geo_tiff_link.startswith("http"):
                    geo_tiff_link = urljoin(self.base_url, geo_tiff_link)

                # Extract edition date from the Current Edition cell
                edition_date = None
                if current_edition_cell:
                    date_text = current_edition_cell.get_text(strip=True)
                    # Try to extract date pattern (e.g., "Nov 27 2025")
                    date_match = re.search(r"(\w+\s+\d+\s+\d{4})", date_text)
                    if date_match:
                        edition_date = date_match.group(1)

                charts.append(
                    {
                        "chart_name": chart_name,
                        "chart_type": "terminal",
                        "geo_tiff_url": geo_tiff_link,
                        "edition_date": edition_date,
                    }
                )

        return charts

    def download_zip_file(self, url: str, output_path: Path) -> bool:
        """Download a zip file from URL.

        Args:
            url: URL of the zip file
            output_path: Path where to save the zip file

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self._make_request(url, stream=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return True
        except Exception as e:
            console.print(f"[red]Error downloading zip file {url}: {e}[/red]")
            return False

    def extract_geotiff_from_zip(
        self, zip_path: Path, output_dir: Path
    ) -> Optional[Path]:
        """Extract GeoTIFF file from zip archive.

        Args:
            zip_path: Path to the zip file
            output_dir: Directory where to extract the GeoTIFF

        Returns:
            Path to extracted GeoTIFF file, or None if not found
        """
        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Find .tif or .tiff files in the zip
                tif_files = [
                    f for f in zip_ref.namelist() if f.lower().endswith((".tif", ".tiff"))
                ]

                if not tif_files:
                    console.print(
                        f"[yellow]No GeoTIFF files found in {zip_path.name}[/yellow]"
                    )
                    return None

                # For terminal charts, prefer TAC files over FLY files
                # Filter for TAC files first
                tac_files = [f for f in tif_files if "TAC" in f.upper() or "tac" in f.lower()]
                if tac_files:
                    tif_file = tac_files[0]
                else:
                    # If no TAC files, check if there are FLY files and skip them
                    fly_files = [f for f in tif_files if "FLY" in f.upper() or "fly" in f.lower()]
                    if fly_files and len(tif_files) == len(fly_files):
                        # Only FLY files found, skip this chart
                        console.print(
                            f"[yellow]Skipping {zip_path.name}: Only FLY files found (processing TAC files only)[/yellow]"
                        )
                        return None
                    # Use first available file if no TAC/FLY distinction
                    tif_file = tif_files[0]
                
                zip_ref.extract(tif_file, output_dir)

                extracted_path = output_dir / Path(tif_file).name
                return extracted_path

        except Exception as e:
            console.print(f"[red]Error extracting GeoTIFF from {zip_path}: {e}[/red]")
            return None

    def scrape_charts(
        self, chart_types: List[str], limit: Optional[int] = None, verbose: bool = False
    ) -> List[Dict[str, str]]:
        """Scrape FAA charts of specified types.

        Args:
            chart_types: List of chart types to scrape ("sectional", "terminal")
            limit: Optional limit on number of charts per type
            verbose: If True, show detailed progress output

        Returns:
            List of chart dictionaries
        """
        # Always show these status messages (important for user feedback)
        console.print("[bold blue]Fetching FAA VFR Raster Charts page...[/bold blue]")
        html = self.get_vfr_page()

        all_charts = []

        if "sectional" in chart_types:
            console.print("[cyan]Extracting Sectional charts...[/cyan]")
            sectional_charts = self.extract_sectional_charts(html)
            if limit:
                sectional_charts = sectional_charts[:limit]
            all_charts.extend(sectional_charts)
            console.print(
                f"[green]Found {len(sectional_charts)} Sectional charts[/green]"
            )

        if "terminal" in chart_types:
            console.print("[cyan]Extracting Terminal Area charts...[/cyan]")
            terminal_charts = self.extract_terminal_charts(html)
            if limit:
                terminal_charts = terminal_charts[:limit]
            all_charts.extend(terminal_charts)
            console.print(
                f"[green]Found {len(terminal_charts)} Terminal Area charts[/green]"
            )

        return all_charts

    def download_and_extract_charts(
        self,
        charts: List[Dict[str, str]],
        download_dir: Path,
        extract_dir: Path,
        verbose: bool = False,
    ) -> List[Dict[str, str]]:
        """Download zip files and extract GeoTIFF files.

        Args:
            charts: List of chart dictionaries with geo_tiff_url
            download_dir: Directory for temporary zip files
            extract_dir: Directory for extracted GeoTIFF files
            verbose: If True, show detailed progress output

        Returns:
            List of charts with added geotiff_path field
        """
        download_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        charts_with_files = []

        if verbose:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Downloading and extracting charts...", total=len(charts)
                )

                for chart in charts:
                    chart_name = chart["chart_name"]
                    progress.update(task, description=f"Processing {chart_name}")

                    # Sanitize chart name for filename
                    safe_name = re.sub(r'[<>:"/\\|?*]', "_", chart_name)
                    zip_filename = f"{safe_name}.zip"
                    zip_path = download_dir / zip_filename

                    # Download zip file
                    if not self.download_zip_file(chart["geo_tiff_url"], zip_path):
                        console.print(f"[red]Failed to download {chart_name}[/red]")
                        progress.advance(task)
                        continue

                    # Extract GeoTIFF
                    geotiff_path = self.extract_geotiff_from_zip(zip_path, extract_dir)
                    if geotiff_path:
                        chart["geotiff_path"] = str(geotiff_path)
                        charts_with_files.append(chart)
                        console.print(
                            f"[green]Extracted:[/green] {chart_name} -> {geotiff_path.name}"
                        )
                    else:
                        console.print(f"[yellow]No GeoTIFF found in {chart_name}[/yellow]")

                    progress.advance(task)
        else:
            # Non-verbose: show spinner status during download/extraction
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Downloading and extracting charts...", total=None
                )
                
                for idx, chart in enumerate(charts):
                    chart_name = chart["chart_name"]
                    progress.update(task, description=f"Downloading {chart_name}...")

                    # Sanitize chart name for filename
                    safe_name = re.sub(r'[<>:"/\\|?*]', "_", chart_name)
                    zip_filename = f"{safe_name}.zip"
                    zip_path = download_dir / zip_filename

                    # Download zip file
                    if not self.download_zip_file(chart["geo_tiff_url"], zip_path):
                        continue

                    # Extract GeoTIFF
                    progress.update(task, description=f"Extracting {chart_name}...")
                    geotiff_path = self.extract_geotiff_from_zip(zip_path, extract_dir)
                    if geotiff_path:
                        chart["geotiff_path"] = str(geotiff_path)
                        charts_with_files.append(chart)
                
                # Update task to empty to clear the description, then remove it
                progress.update(task, description="")
                progress.remove_task(task)
                # Give Rich a moment to render the removal
                import time
                time.sleep(0.05)
            
            # After progress closes, print final status
            # The spinner line should be cleared by removing the task
            console.print(f"[green]Downloaded and extracted {len(charts_with_files)} charts[/green]")

        return charts_with_files
