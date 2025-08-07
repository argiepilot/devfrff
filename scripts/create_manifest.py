#!/usr/bin/env python3
"""Create manifest file manually with the correct date."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_generator import PDFGenerator
from rich.console import Console

console = Console()

def create_manifest():
    """Create manifest file with the correct date."""
    
    console.print("[bold blue]Creating manifest file...[/bold blue]")
    
    # Use the current date from the DFS AIP URL
    current_date = "2025JUL25"
    
    # Create PDF generator with the current date
    pdf_generator = PDFGenerator("AIP Germany", current_date=current_date)
    
    # Create manifest
    manifest_path = pdf_generator.create_manifest()
    
    if manifest_path:
        console.print(f"[green]✓[/green] Manifest created: {manifest_path}")
        
        # Read and display the manifest content
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
            console.print(f"[cyan]Manifest content:[/cyan]\n{content}")
    else:
        console.print("[red]✗[/red] Failed to create manifest")
    
    # Check directory structure
    output_dir = Path("AIP Germany")
    if output_dir.exists():
        console.print(f"[green]✓[/green] Output directory: {output_dir}")
        
        byop_dir = output_dir / "byop"
        if byop_dir.exists():
            pdf_files = list(byop_dir.glob("*.PDF"))
            console.print(f"[green]✓[/green] BYOP subdirectory: {byop_dir}")
            console.print(f"[green]✓[/green] Found {len(pdf_files)} PDF files")
        
        manifest_file = output_dir / "manifest.json"
        if manifest_file.exists():
            console.print(f"[green]✓[/green] Manifest file: {manifest_file}")
        else:
            console.print("[red]✗[/red] Manifest file not found")
    else:
        console.print("[red]✗[/red] Output directory not found")

if __name__ == "__main__":
    create_manifest() 