"""Unified BYOP package generator for multiple chart sources."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console

console = Console()


class BYOPPackager:
    """Generate unified BYOP packages from multiple chart sources."""

    def __init__(self, output_dir: str = "VFR Charts Package"):
        """Initialize the BYOP packager.

        Args:
            output_dir: Output directory for the BYOP package
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        (self.output_dir / "byop").mkdir(exist_ok=True)
        (self.output_dir / "layers").mkdir(exist_ok=True)

        self.sources = []
        self.version = None

    def add_source(self, source_name: str) -> None:
        """Add a source to the package.

        Args:
            source_name: Name of the source (e.g., "DFS", "FAA Sectional", "FAA Terminal")
        """
        if source_name not in self.sources:
            self.sources.append(source_name)

    def set_version(self, version: str) -> None:
        """Set the version string for the package.

        Args:
            version: Version string (e.g., "2025JUL25")
        """
        self.version = version

    def create_manifest(self) -> Optional[Path]:
        """Create unified manifest.json file.

        Returns:
            Path to manifest file, or None if creation failed
        """
        # Generate package name
        if self.version:
            package_name = f"VFR Charts Package {self.version}"
        else:
            # Use current date if no version specified
            current_date = datetime.now().strftime("%Y%b%d").upper()
            package_name = f"VFR Charts Package {current_date}"
            self.version = current_date

        # Generate abbreviation
        abbrev_parts = []
        if "DFS" in self.sources:
            abbrev_parts.append("DFS")
        if "FAA Sectional" in self.sources:
            abbrev_parts.append("SEC")
        if "FAA Terminal" in self.sources:
            abbrev_parts.append("TAC")
        
        abbreviation = " ".join(abbrev_parts) if abbrev_parts else "VFR"

        # Generate organization name
        org_parts = []
        if "DFS" in self.sources:
            org_parts.append("DFS")
        if "FAA Sectional" in self.sources or "FAA Terminal" in self.sources:
            org_parts.append("FAA")
        
        organization_name = " and ".join(org_parts) if org_parts else "Multiple Sources"

        manifest_data = {
            "name": package_name,
            "abbreviation": abbreviation,
            "version": self.version,
            "organizationName": f"from {organization_name}",
            "sources": self.sources,
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

    def get_package_summary(self) -> Dict[str, int]:
        """Get summary of files in the package.

        Returns:
            Dictionary with file counts
        """
        byop_dir = self.output_dir / "byop"
        layers_dir = self.output_dir / "layers"

        pdf_files = list(byop_dir.glob("*.PDF")) if byop_dir.exists() else []
        mbtiles_files = (
            list(layers_dir.glob("*.mbtiles")) if layers_dir.exists() else []
        )

        return {
            "total_pdfs": len(pdf_files),
            "total_mbtiles": len(mbtiles_files),
            "byop_files": len(pdf_files),
            "layers_files": len(mbtiles_files),
        }

    def display_summary(self) -> None:
        """Display a summary of the created package."""
        summary = self.get_package_summary()

        console.print("\n[bold green]📦 BYOP Package Summary[/bold green]")
        console.print(f"[cyan]Package directory:[/cyan] {self.output_dir}")
        console.print(f"[cyan]Sources:[/cyan] {', '.join(self.sources)}")
        console.print(f"[cyan]Version:[/cyan] {self.version}")
        console.print(f"[cyan]PDF charts (byop/):[/cyan] {summary['total_pdfs']}")
        console.print(
            f"[cyan]mbtiles charts (layers/):[/cyan] {summary['total_mbtiles']}"
        )
        console.print(f"[cyan]Total files:[/cyan] {summary['total_pdfs'] + summary['total_mbtiles']}")
