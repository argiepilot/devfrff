"""Web scraper for DFS AIP VFR aerodrome charts."""

import random
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class AIPScraper:
    """Scraper for DFS AIP VFR aerodrome charts."""

    def __init__(self, base_url: str = "https://aip.dfs.de", rate_limit: float = 1.0):
        """Initialize the scraper.

        Args:
            base_url: Base URL for the AIP service
            rate_limit: Minimum delay between requests in seconds (default: 1.0)
        """
        self.base_url = base_url
        self.rate_limit = rate_limit
        self.last_request_time = 0

        # Simple page cache to simulate browser behavior
        # Real browsers cache pages when users hit "back"
        self.page_cache = {}

        # Set up session with proper headers
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
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
            console.print(
                f"[yellow]Rate limiting: sleeping for {sleep_time:.2f}s[/yellow]"
            )
            time.sleep(sleep_time)

        # Add referrer for non-main page requests to simulate real browser behavior
        headers = {}
        if not url.endswith("/basicaip/"):
            headers["Referer"] = f"{self.base_url}/basicaip/"

        if headers:
            self.session.headers.update(headers)

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Add timeout to prevent hanging
                kwargs.setdefault(
                    "timeout", 60
                )  # Increase timeout for better reliability
                response = getattr(self.session, method.lower())(url, **kwargs)

                # Update last request time
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
                time.sleep(delay)  # Exponential backoff with jitter

    def get_main_aip_page(self) -> str:
        """Get the main AIP page to find the AIP VFR Online link."""
        url = f"{self.base_url}/basicaip/"
        response = self._make_request(url)
        return response.text

    def extract_vfr_online_link(self, html: str) -> str:
        """Extract the AIP VFR Online link from the main AIP page."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for "AIP VFR Online" link
        vfr_links = soup.find_all("a", href=True)
        for link in vfr_links:
            text = link.get_text(strip=True)
            if "AIP VFR Online" in text:
                href = link.get("href")
                if href:
                    # Convert relative URL to absolute if needed
                    if href.startswith("/"):
                        return f"{self.base_url}{href}"
                    elif not href.startswith("http"):
                        return f"{self.base_url}/basicaip/{href}"
                    return href

        raise ValueError("Could not find AIP VFR Online link")

    def extract_aerodromes_section_link(self, html: str, base_url: str = None) -> str:
        """Extract the AD Flugplätze link from the VFR online page."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for "AD Flugplätze" or "AD Aerodromes" link
        ad_links = soup.find_all("a", href=True)
        for link in ad_links:
            text = link.get_text(strip=True)
            if "AD Flugplätze" in text or "AD Aerodromes" in text:
                href = link.get("href")
                if href:
                    # Handle different URL formats
                    if href.startswith("http"):
                        return href
                    elif href.startswith("/"):
                        return f"{self.base_url}{href}"
                    else:
                        # Relative URL - construct based on current date
                        current_date = getattr(self, "current_date", None)
                        if not current_date:
                            raise ValueError(
                                "Current date not available. Please call get_aerodrome_list_page() first."
                            )
                        return f"{self.base_url}/BasicVFR/{current_date}/chapter/{href}"

        raise ValueError("Could not find AD Flugplätze link")

    def extract_date_from_url(self, url: str) -> str:
        """Extract the date part (e.g., '2025JUL25') from a VFR URL."""
        import re

        match = re.search(r"/(\d{4}[A-Z]{3}\d{2})/", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract date from URL: {url}")

    def get_aerodrome_list_page(self) -> str:
        """Get the aerodrome list page by following the proper navigation flow."""
        # Step 1: Get main AIP page
        main_aip_html = self.get_main_aip_page()

        # Step 2: Extract AIP VFR Online link
        vfr_online_url = self.extract_vfr_online_link(main_aip_html)

        # Step 3: Get VFR Online page (might be a redirect)
        vfr_online_response = self._make_request(vfr_online_url)

        # Extract date from the final URL (after any redirects)
        final_url = vfr_online_response.url
        self.current_date = self.extract_date_from_url(final_url)
        console.print(f"[green]Extracted current date: {self.current_date}[/green]")

        # Step 4: Extract AD Flugplätze link
        aerodromes_url = self.extract_aerodromes_section_link(vfr_online_response.text)

        # Step 5: Get the aerodromes page
        response = self._make_request(aerodromes_url)
        return response.text

    def get_alphabetical_sections(self, html: str) -> List[Tuple[str, str]]:
        """Extract alphabetical section links from the main page."""
        soup = BeautifulSoup(html, "html.parser")
        sections = []

        # Find all folder links (alphabetical sections)
        folder_links = soup.find_all("a", class_="folder-link")

        for link in folder_links:
            href = link.get("href")

            # Look for folder-name spans within the link
            folder_name_spans = link.find_all("span", class_="folder-name")
            if not folder_name_spans:
                continue

            # Get the first folder name (they're duplicated for different languages)
            text = folder_name_spans[0].get_text(strip=True)

            # Skip non-alphabetical sections (like "AD 0 Content", "AD 1 General Remarks", etc.)
            if not re.match(r"^[A-Z](-[A-Z])?$", text):
                continue

            # This is an alphabetical section
            if href and not any(s[0] == text for s in sections):
                sections.append((text, href))

        return sections

    def get_section_page_cached(self, section_url: str) -> str:
        """Get section page with caching to simulate browser behavior.

        Real browsers cache pages when users navigate back from individual airports
        to the section list. This simulates that behavior.
        """
        # Check cache first
        cache_key = section_url
        if cache_key in self.page_cache:
            return self.page_cache[cache_key]

        # Not in cache, fetch it
        current_date = getattr(self, "current_date", None)
        if not current_date:
            raise ValueError(
                "Current date not available. Please call get_aerodrome_list_page() first."
            )

        full_url = f"{self.base_url}/BasicVFR/{current_date}/chapter/{section_url}"
        response = self._make_request(full_url)

        # Cache for future use
        self.page_cache[cache_key] = response.text

        return response.text

    def get_aerodromes_from_section(
        self, section_url: str
    ) -> List[Tuple[str, str, str]]:
        """Get aerodrome links from an alphabetical section page."""
        # Use cached version to simulate browser behavior
        html = self.get_section_page_cached(section_url)
        soup = BeautifulSoup(html, "html.parser")
        aerodromes = []

        # Find all links that might be aerodrome links
        links = soup.find_all("a", href=True)

        for link in links:
            href = link.get("href")
            text = link.get_text(strip=True)

            # Look for aerodrome links with ICAO codes in the text
            # Pattern like "Frankfurt-Egelsbach EDFEFrankfurt-Egelsbach EDFE»"
            if href and len(text) > 3:
                # Extract ICAO code from the text
                icao_match = re.search(r"([A-Z]{4})", text)
                if icao_match:
                    icao_code = icao_match.group(1)
                    # Extract aerodrome name (everything before the ICAO code)
                    name_match = re.search(r"^(.+?)\s+[A-Z]{4}", text)
                    if name_match:
                        aerodrome_name = name_match.group(1).strip()
                    else:
                        aerodrome_name = text.replace(icao_code, "").strip()

                    # Clean up the name (remove duplicates and special characters)
                    aerodrome_name = re.sub(
                        r"([A-Za-z\s-]+)\1.*", r"\1", aerodrome_name
                    )
                    aerodrome_name = aerodrome_name.replace("»", "").strip()

                    if aerodrome_name:
                        aerodromes.append((icao_code, aerodrome_name, href))

        # If no aerodromes found with the main pattern, try alternative patterns
        if not aerodromes:
            for link in links:
                href = link.get("href")
                text = link.get_text(strip=True)

                # Look for any 4-letter code that might be an ICAO code
                icao_match = re.search(r"([A-Z]{4})", text)
                if icao_match and len(text) > 4:
                    icao_code = icao_match.group(1)
                    aerodrome_name = text.replace(icao_code, "").strip()
                    aerodrome_name = re.sub(
                        r"([A-Za-z\s-]+)\1.*", r"\1", aerodrome_name
                    )
                    aerodrome_name = aerodrome_name.replace("»", "").strip()

                    if aerodrome_name:
                        aerodromes.append((icao_code, aerodrome_name, href))

        return aerodromes

    def extract_aerodrome_links(self, html: str) -> List[Tuple[str, str, str]]:
        """Extract aerodrome links from the main page by following alphabetical sections."""
        # Get alphabetical sections
        sections = self.get_alphabetical_sections(html)
        console.print(f"[cyan]Found {len(sections)} alphabetical sections[/cyan]")

        all_aerodromes = []

        # Process each section
        for section_name, section_url in sections:
            console.print(f"[yellow]Processing section: {section_name}[/yellow]")
            aerodromes = self.get_aerodromes_from_section(section_url)
            all_aerodromes.extend(aerodromes)
            console.print(
                f"  Found {len(aerodromes)} aerodromes in section {section_name}"
            )

        return all_aerodromes

    def get_aerodrome_page(self, page_url: str) -> str:
        """Get the aerodrome detail page."""
        # Use the dynamically extracted date
        current_date = getattr(self, "current_date", None)
        if not current_date:
            raise ValueError(
                "Current date not available. Please call get_aerodrome_list_page() first."
            )  # fallback for backwards compatibility
        full_url = f"{self.base_url}/BasicVFR/{current_date}/chapter/{page_url}"
        response = self._make_request(full_url)
        return response.text

    def extract_chart_info(
        self, html: str, icao_code: str, aerodrome_name: str
    ) -> List[Dict]:
        """Extract chart information from aerodrome page."""
        soup = BeautifulSoup(html, "html.parser")
        charts = []

        # Find all links that might be chart links
        links = soup.find_all("a", href=True)

        for link in links:
            href = link.get("href")
            text = link.get_text(strip=True)

            # Look for chart links (they typically contain page IDs)
            # Pattern like "../pages/51B96FC66F7767D88BE754F64116ABC3.html"
            if href and "pages/" in href and text:
                # Extract page ID from href
                page_id_match = re.search(r"pages/([A-F0-9]+)\.html", href)
                if page_id_match:
                    page_id = page_id_match.group(1)

                    # Clean up chart name (remove duplicates and special characters)
                    # The text might be duplicated like "EDKA Aachen-Merzbrueck 1EDKA Aachen-Merzbrueck 1"
                    # Find the midpoint and check if first half equals second half
                    chart_name = text.replace("»", "").strip()
                    if len(chart_name) % 2 == 0:
                        mid = len(chart_name) // 2
                        first_half = chart_name[:mid]
                        second_half = chart_name[mid:]
                        if first_half == second_half:
                            chart_name = first_half

                    chart_name = chart_name.strip()

                    # Create chart info
                    chart_info = {
                        "icao_code": icao_code,
                        "aerodrome_name": aerodrome_name,
                        "chart_name": chart_name,
                        "page_id": page_id,
                        "page_url": href,
                        "print_url": self._build_print_url(page_id, chart_name),
                    }
                    charts.append(chart_info)

        return charts

    def _build_print_url(self, page_id: str, chart_name: str) -> str:
        """Build the print URL for a chart."""
        # URL encode the chart name
        encoded_name = urllib.parse.quote(chart_name)
        return f"{self.base_url}/basicVFR/print/AD/{page_id}/{encoded_name}"

    def download_chart_image(
        self, print_url: str, referrer_url: Optional[str] = None
    ) -> Optional[bytes]:
        """Download the chart image from the print URL."""
        import time

        from requests.exceptions import RequestException, Timeout

        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                # Increase timeout for chart downloads and add more detailed headers
                session = (
                    self.session if hasattr(self, "session") else requests.Session()
                )
                headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }

                # Add referrer header if provided - this is crucial for getting full-size images
                if referrer_url:
                    headers["Referer"] = referrer_url

                session.headers.update(headers)

                response = session.get(print_url, timeout=60)
                response.raise_for_status()

                # Check what we received
                content_type = response.headers.get("Content-Type", "unknown")
                content_length = len(response.content)

                # Check if it's already an image
                if content_type.startswith("image/"):
                    if content_length > 1000:  # Valid size check
                        return response.content
                    else:
                        console.print(
                            f"[yellow] Image too small ({content_length} bytes), skipping[/yellow]"
                        )
                        return None

                # Parse the print page to find the actual image
                soup = BeautifulSoup(response.text, "html.parser")

                # Look for image tags with chart-like content
                img_tags = soup.find_all("img")
                for img in img_tags:
                    src = img.get("src")

                    # Handle base64 data URIs
                    if src and src.startswith("data:image/"):
                        import base64

                        try:
                            # Extract base64 data after the comma
                            header, data = src.split(",", 1)
                            image_data = base64.b64decode(data)
                            return image_data
                        except Exception as e:
                            console.print(
                                f"[red] Failed to decode base64 image: {e}[/red]"
                            )
                            continue

                    # Handle regular image URLs
                    elif src and (
                        "chart" in src.lower()
                        or "image" in src.lower()
                        or "diagram" in src.lower()
                    ):
                        img_url = urljoin(print_url, src)

                        img_response = session.get(img_url, timeout=60)
                        img_response.raise_for_status()

                        if len(img_response.content) > 1000:  # Valid size check
                            return img_response.content

                # If no specific chart image found, try to find any substantial image
                for i, img in enumerate(img_tags):
                    src = img.get("src")

                    # Handle base64 data URIs in fallback
                    if src and src.startswith("data:image/"):
                        import base64

                        try:
                            # Extract base64 data after the comma
                            header, data = src.split(",", 1)
                            image_data = base64.b64decode(data)
                            return image_data
                        except Exception as e:
                            console.print(
                                f"[red] Failed to decode fallback base64 image: {e}[/red]"
                            )
                            continue

                    # Handle regular URLs
                    elif src and len(src) > 10:
                        img_url = urljoin(print_url, src)

                        img_response = session.get(img_url, timeout=60)
                        img_response.raise_for_status()

                        # Check if it's actually an image and substantial size
                        content_type = img_response.headers.get(
                            "Content-Type", ""
                        ).lower()
                        content_length = len(img_response.content)

                        if content_type.startswith("image/") and content_length > 5000:
                            return img_response.content

                # No suitable image found
                console.print(
                    f"[yellow]No suitable chart image found on {print_url}[/yellow]"
                )
                return None

            except Timeout as e:
                if attempt < max_retries - 1:
                    console.print(
                        f"[yellow]Timeout downloading chart (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...[/yellow]"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    console.print(
                        f"[red]Final timeout downloading chart from {print_url}: {e}[/red]"
                    )
            except RequestException as e:
                if attempt < max_retries - 1:
                    console.print(
                        f"[yellow]Request error downloading chart (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...[/yellow]"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    console.print(
                        f"[red]Final error downloading chart from {print_url}: {e}[/red]"
                    )
            except Exception as e:
                console.print(
                    f"[red]Unexpected error downloading chart from {print_url}: {e}[/red]"
                )
                break

        return None

    def scrape_all_aerodromes(
        self, limit_aerodromes: Optional[int] = None
    ) -> List[Dict]:
        """Scrape all aerodrome charts from the AIP site with realistic browser behavior.

        Args:
            limit_aerodromes: Optional limit on number of aerodromes to process (for testing)
        """
        console.print("[bold blue]Starting AIP aerodrome chart scraping...[/bold blue]")
        console.print("[cyan]  Using browser-like navigation with page caching[/cyan]")

        if limit_aerodromes:
            console.print(
                f"[yellow] Limiting to first {limit_aerodromes} aerodromes for testing[/yellow]"
            )

        # Get main page
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching aerodrome list...", total=None)
            html = self.get_aerodrome_list_page()
            progress.update(task, completed=True)

        # Get alphabetical sections (like a real user browsing)
        sections = self.get_alphabetical_sections(html)
        console.print(f"[green]Found {len(sections)} alphabetical sections[/green]")

        all_charts = []
        total_aerodromes = 0
        processed_aerodromes = 0

        # Process each section (simulating user clicking through sections)
        for section_name, section_url in sections:
            console.print(
                f"\n[bold yellow] Processing section: {section_name}[/bold yellow]"
            )

            # Get aerodromes in this section (with caching)
            aerodromes = self.get_aerodromes_from_section(section_url)
            console.print(
                f"[cyan]Found {len(aerodromes)} aerodromes in section {section_name}[/cyan]"
            )
            total_aerodromes += len(aerodromes)

            if not aerodromes:
                continue

            # Apply limit if specified
            remaining_limit = None
            if limit_aerodromes:
                remaining_limit = limit_aerodromes - processed_aerodromes
                if remaining_limit <= 0:
                    console.print(
                        f"[yellow] Reached limit of {limit_aerodromes} aerodromes, stopping[/yellow]"
                    )
                    break
                if remaining_limit < len(aerodromes):
                    aerodromes = aerodromes[:remaining_limit]
                    console.print(
                        f"[yellow] Processing only {remaining_limit} aerodromes from section {section_name} (limit reached)[/yellow]"
                    )

            # Process aerodromes in this section
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Processing {section_name} aerodromes...", total=len(aerodromes)
                )

                for icao_code, aerodrome_name, page_url in aerodromes:
                    progress.update(
                        task, description=f"Processing {icao_code} - {aerodrome_name}"
                    )

                    try:
                        # Get aerodrome page (user clicks on airport)
                        aerodrome_html = self.get_aerodrome_page(page_url)

                        # Extract chart information
                        charts = self.extract_chart_info(
                            aerodrome_html, icao_code, aerodrome_name
                        )
                        all_charts.extend(charts)

                        console.print(
                            f"[green]{icao_code}:[/green] {len(charts)} charts found"
                        )
                        processed_aerodromes += 1

                        # After processing airport, user would hit "back" to section
                        # (this is where browser would use cached section page)

                        # Check if we've hit the limit
                        if (
                            limit_aerodromes
                            and processed_aerodromes >= limit_aerodromes
                        ):
                            console.print(
                                f"[yellow] Reached limit of {limit_aerodromes} aerodromes, finishing[/yellow]"
                            )
                            progress.advance(task)
                            break

                    except Exception as e:
                        console.print(f"[red]{icao_code}: Error - {e}[/red]")
                        processed_aerodromes += 1  # Count failed ones too

                    progress.advance(task)

            # Break out of section loop if limit reached
            if limit_aerodromes and processed_aerodromes >= limit_aerodromes:
                break

            # Show section summary
            section_charts = len(
                [
                    c
                    for c in all_charts
                    if any(a[0] == c.get("icao_code") for a in aerodromes)
                ]
            )
            console.print(
                f"[green] Section {section_name} completed: {len(aerodromes)} airports, {section_charts} charts[/green]"
            )

        console.print("\n[bold green] Scraping Summary[/bold green]")
        if limit_aerodromes:
            console.print(
                f"[yellow]Limit applied: {limit_aerodromes} aerodromes[/yellow]"
            )
            console.print(
                f"[green]Aerodromes processed: {processed_aerodromes}[/green]"
            )
        else:
            console.print(f"[green]Total aerodromes found: {total_aerodromes}[/green]")
        console.print(f"[green]Total charts found: {len(all_charts)}[/green]")
        console.print(
            f"[green]Cache hits: {len(self.page_cache)} section pages cached[/green]"
        )

        return all_charts

    def scrape_and_process_aerodromes(
        self, 
        pdf_generator, 
        limit_aerodromes: Optional[int] = None,
        airport_pause: float = 5.0,
        section_pause: float = 15.0
    ) -> List[Dict]:
        """Scrape aerodromes and process charts immediately (like a real user).
        
        This method processes one airport at a time, downloading and creating PDFs
        immediately for each chart, with realistic pauses between operations.
        
        Args:
            pdf_generator: PDFGenerator instance for creating PDFs
            limit_aerodromes: Optional limit on number of aerodromes to process
            airport_pause: Pause between airports in seconds (default: 5.0)
            section_pause: Pause between letter sections in seconds (default: 15.0)
        """
        import time
        
        console.print("[bold blue]Starting AIP aerodrome chart scraping with immediate processing...[/bold blue]")
        console.print("[cyan]  Processing like a real user: airport → charts → PDFs → next airport[/cyan]")

        if limit_aerodromes:
            console.print(
                f"[yellow] Limiting to first {limit_aerodromes} aerodromes for testing[/yellow]"
            )

        # Get main page
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching aerodrome list...", total=None)
            html = self.get_aerodrome_list_page()
            progress.update(task, completed=True)

        # Get alphabetical sections
        sections = self.get_alphabetical_sections(html)
        console.print(f"[green]Found {len(sections)} alphabetical sections[/green]")

        all_charts = []
        total_aerodromes = 0
        processed_aerodromes = 0
        successful_pdfs = 0

        # Process each section
        for section_idx, (section_name, section_url) in enumerate(sections):
            console.print(
                f"\n[bold yellow] Processing section: {section_name}[/bold yellow]"
            )

            # Get aerodromes in this section
            aerodromes = self.get_aerodromes_from_section(section_url)
            console.print(
                f"[cyan]Found {len(aerodromes)} aerodromes in section {section_name}[/cyan]"
            )
            total_aerodromes += len(aerodromes)

            if not aerodromes:
                continue

            # Apply limit if specified
            if limit_aerodromes:
                remaining_limit = limit_aerodromes - processed_aerodromes
                if remaining_limit <= 0:
                    console.print(
                        f"[yellow] Reached limit of {limit_aerodromes} aerodromes, stopping[/yellow]"
                    )
                    break
                if remaining_limit < len(aerodromes):
                    aerodromes = aerodromes[:remaining_limit]
                    console.print(
                        f"[yellow] Processing only {remaining_limit} aerodromes from section {section_name} (limit reached)[/yellow]"
                    )

            # Process each aerodrome in this section
            for aerodrome_idx, (icao_code, aerodrome_name, page_url) in enumerate(aerodromes):
                console.print(
                    f"\n[bold cyan]  Processing airport {processed_aerodromes + 1}: {icao_code} - {aerodrome_name}[/bold cyan]"
                )

                try:
                    # Get aerodrome page
                    aerodrome_html = self.get_aerodrome_page(page_url)

                    # Extract chart information
                    charts = self.extract_chart_info(
                        aerodrome_html, icao_code, aerodrome_name
                    )
                    
                    console.print(f"[green]Found[/green] {len(charts)} charts for {icao_code}")

                    # Process each chart immediately (like a real user)
                    for chart_idx, chart in enumerate(charts, 1):
                        console.print(
                            f"  Processing chart {chart_idx}/{len(charts)}: {chart['chart_name']}"
                        )

                        # Build referrer URL
                        if chart.get("page_url") and hasattr(self, "current_date"):
                            page_href = chart["page_url"].replace("../", "")
                            referrer_url = f"{self.base_url}/BasicVFR/{self.current_date}/{page_href}"
                        else:
                            referrer_url = None

                        # Download chart image
                        image_data = self.download_chart_image(chart["print_url"], referrer_url)
                        
                        if image_data:
                            # Create PDF immediately
                            pdf_path = pdf_generator.process_chart(chart, image_data)
                            if pdf_path:
                                successful_pdfs += 1
                                console.print(
                                    f"    [green]Created PDF:[/green] {pdf_path.name}"
                                )
                            else:
                                console.print(
                                    f"    [red]Failed to create PDF for {chart['chart_name']}[/red]"
                                )
                        else:
                            console.print(
                                f"    [red]Failed to download image for {chart['chart_name']}[/red]"
                            )

                    all_charts.extend(charts)
                    processed_aerodromes += 1

                    # Pause between airports (like a real user thinking/reading)
                    if aerodrome_idx < len(aerodromes) - 1:  # Don't pause after last airport in section
                        # Randomize pause around airport_pause (±40% variation)
                        pause_min = airport_pause * 0.6
                        pause_max = airport_pause * 1.4
                        random_pause = random.uniform(pause_min, pause_max)
                        console.print(f"[yellow]Pausing {random_pause:.1f}s before next airport...[/yellow]")
                        time.sleep(random_pause)

                    # Check if we've hit the limit
                    if limit_aerodromes and processed_aerodromes >= limit_aerodromes:
                        console.print(
                            f"[yellow] Reached limit of {limit_aerodromes} aerodromes, finishing[/yellow]"
                        )
                        break

                except Exception as e:
                    console.print(f"[red]{icao_code}: Error - {e}[/red]")
                    processed_aerodromes += 1

            # Pause between sections (like a real user navigating to next letter)
            # Don't pause if we've reached the limit or if this is the last section
            if (section_idx < len(sections) - 1 and 
                not (limit_aerodromes and processed_aerodromes >= limit_aerodromes)):
                # Randomize pause around section_pause (±40% variation)
                pause_min = section_pause * 0.6
                pause_max = section_pause * 1.4
                random_section_pause = random.uniform(pause_min, pause_max)
                console.print(f"[yellow]Pausing {random_section_pause:.1f}s before next section...[/yellow]")
                time.sleep(random_section_pause)

            # Break out of section loop if limit reached
            if limit_aerodromes and processed_aerodromes >= limit_aerodromes:
                break

            # Show section summary
            section_charts = len(
                [
                    c
                    for c in all_charts
                    if any(a[0] == c.get("icao_code") for a in aerodromes)
                ]
            )
            console.print(
                f"[green] Section {section_name} completed: {len(aerodromes)} airports, {section_charts} charts[/green]"
            )

        console.print("\n[bold green] Processing Summary[/bold green]")
        if limit_aerodromes:
            console.print(
                f"[yellow]Limit applied: {limit_aerodromes} aerodromes[/yellow]"
            )
        console.print(f"[green]Aerodromes processed: {processed_aerodromes}[/green]")
        console.print(f"[green]Total charts found: {len(all_charts)}[/green]")
        console.print(f"[green]PDFs successfully created: {successful_pdfs}[/green]")
        console.print(
            f"[green]Cache hits: {len(self.page_cache)} section pages cached[/green]"
        )

        return all_charts

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for debugging."""
        return {
            "cached_pages": len(self.page_cache),
            "cache_size_kb": sum(
                len(content.encode("utf-8")) for content in self.page_cache.values()
            )
            // 1024,
        }

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename for safe filesystem storage.

        Args:
            filename: The filename to sanitize

        Returns:
            str: A sanitized filename safe for filesystem use
        """
        import re

        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

        # Remove control characters
        filename = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", filename)

        # Replace multiple spaces/underscores with single underscore
        filename = re.sub(r"[_\s]+", "_", filename)

        # Remove leading/trailing dots, spaces, and underscores
        filename = filename.strip("._ ")

        # Ensure filename isn't empty
        if not filename:
            filename = "unnamed_chart"

        # Limit length to avoid filesystem issues
        if len(filename) > 200:
            filename = filename[:200]

        return filename

    def display_charts_summary(self, charts: List[Dict]) -> None:
        """Display a summary of found charts."""
        table = Table(title="Found Aerodrome Charts")
        table.add_column("ICAO", style="cyan")
        table.add_column("Aerodrome", style="green")
        table.add_column("Chart Name", style="yellow")
        table.add_column("Page ID", style="magenta")

        for chart in charts:
            table.add_row(
                chart["icao_code"],
                chart["aerodrome_name"],
                chart["chart_name"],
                chart["page_id"],
            )

        console.print(table)
