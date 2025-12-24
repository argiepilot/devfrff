"""PDF generator for VFR aerodrome charts."""

import json
import re
from pathlib import Path
from typing import Dict, Optional

import img2pdf
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class PDFGenerator:
    """Generate PDF files from chart images for ForeFlight BYOP."""

    def __init__(self, output_dir: str = "AIP Germany", current_date: Optional[str] = None):
        """Initialize the PDF generator."""
        self.output_dir = Path(output_dir)
        self.current_date = current_date
        # Create output directory and BYOP subdirectory
        self.output_dir.mkdir(exist_ok=True)
        (self.output_dir / "byop").mkdir(exist_ok=True)
        # Keep layers directory for unified packages (FAA mbtiles live here)
        (self.output_dir / "layers").mkdir(exist_ok=True)

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for BYOP format."""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        # Remove extra spaces and replace with single space
        filename = re.sub(r"\s+", " ", filename)
        # Remove leading/trailing spaces
        filename = filename.strip()
        return filename

    def generate_byop_filename(self, chart_info: Dict) -> str:
        """Generate BYOP filename according to ForeFlight format."""
        icao_code = chart_info["icao_code"]
        chart_name = self.sanitize_filename(chart_info["chart_name"])

        # Check if this is an AD chart (Info type) - any AD followed by space and content
        if re.match(r"^AD\s+.+", chart_name):
            # AD charts get "Info_" prefix
            filename = f"{icao_code}_Info_{chart_name}.PDF"
        else:
            # All other charts get "Visual_" prefix - remove redundant ICAO code
            # Extract chart name without the ICAO code prefix
            chart_name_clean = chart_name
            if chart_name.startswith(f"{icao_code} "):
                chart_name_clean = chart_name[len(icao_code) + 1:]  # Remove ICAO + space
            filename = f"{icao_code}_Visual_{chart_name_clean}.PDF"

        return filename



    def image_to_pdf(self, image_data: bytes, output_path: Path) -> bool:
        """Convert image data to PDF."""
        try:
            # Convert image data to PDF
            pdf_data = img2pdf.convert(image_data)

            # Write PDF to file
            with open(output_path, "wb") as f:
                f.write(pdf_data)

            return True

        except Exception as e:
            console.print(f"[red]Error converting image to PDF: {e}[/red]")
            return False

    def process_chart(self, chart_info: Dict, image_data: bytes) -> Optional[Path]:
        """Process a single chart and generate PDF."""
        try:
            # Generate BYOP filename
            filename = self.generate_byop_filename(chart_info)
            output_path = self.output_dir / "byop" / filename

            # Convert image to PDF
            if self.image_to_pdf(image_data, output_path):
                console.print(f"[green]✓[/green] Generated: {filename}")
                return output_path
            else:
                console.print(
                    f"[red]✗[/red] Failed to generate PDF for {chart_info['icao_code']}"
                )
                return None

        except Exception as e:
            console.print(
                f"[red]Error processing chart {chart_info['icao_code']}: {e}[/red]"
            )
            return None

    def process_charts_batch(self, charts_with_images: list) -> Dict[str, Path]:
        """Process multiple charts and generate PDFs."""
        successful_pdfs = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Generating PDFs...", total=len(charts_with_images)
            )

            for chart_info, image_data in charts_with_images:
                progress.update(
                    task, description=f"Processing {chart_info['icao_code']}"
                )

                pdf_path = self.process_chart(chart_info, image_data)
                if pdf_path:
                    key = f"{chart_info['icao_code']}_{chart_info['chart_name']}"
                    successful_pdfs[key] = pdf_path

                progress.advance(task)

        console.print(
            f"[bold green]Successfully generated {len(successful_pdfs)} PDF files[/bold green]"
        )
        return successful_pdfs

    def create_content_pack_structure(self) -> None:
        """Create the complete BYOP content pack structure."""
        # Create main directories
        (self.output_dir / "byop").mkdir(exist_ok=True)
        (self.output_dir / "layers").mkdir(exist_ok=True)

        console.print(
            f"[green]Created BYOP content pack structure in: {self.output_dir}[/green]"
        )

    def create_manifest(self) -> Optional[Path]:
        """Create ForeFlight BYOP manifest.json file."""
        if not self.current_date:
            console.print("[yellow]⚠️  No current date available, skipping manifest creation[/yellow]")
            return None
            
        manifest_data = {
            "name": f"AIP VFR Germany {self.current_date}",
            "abbreviation": "VFR GER",
            "version": f"{self.current_date}",
            "organizationName": "from DFS"
        }
        
        manifest_path = self.output_dir / "manifest.json"
        
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2, ensure_ascii=False)
            
            console.print(f"[green]✓[/green] Created manifest: {manifest_path.name}")
            return manifest_path
            
        except Exception as e:
            console.print(f"[red]Error creating manifest: {e}[/red]")
            return None

    def get_generated_files_summary(self) -> Dict[str, int]:
        """Get summary of generated files."""
        # Look for PDFs in the byop subdirectory
        byop_dir = self.output_dir / "byop"
        pdf_files = list(byop_dir.glob("*.PDF")) if byop_dir.exists() else []

        summary = {
            "total_pdfs": len(pdf_files),
            "byop_files": len(pdf_files),
        }

        return summary
