#!/usr/bin/env python3
"""Test script for manifest generation."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_generator import PDFGenerator
from rich.console import Console

console = Console()

def test_manifest_generation():
    """Test manifest generation with different scenarios."""
    
    # Test 1: With current date
    console.print("[bold blue]Test 1: Manifest with current date[/bold blue]")
    pdf_gen = PDFGenerator("test_manifest_output", current_date="2025JUL25")
    manifest_path = pdf_gen.create_manifest()
    
    if manifest_path:
        console.print(f"[green]✓[/green] Manifest created: {manifest_path}")
        # Read and display the manifest content
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
            console.print(f"[cyan]Manifest content:[/cyan]\n{content}")
    else:
        console.print("[red]✗[/red] Failed to create manifest")
    
    # Test 2: Without current date
    console.print("\n[bold blue]Test 2: Manifest without current date[/bold blue]")
    pdf_gen_no_date = PDFGenerator("test_manifest_output_no_date")
    manifest_path_no_date = pdf_gen_no_date.create_manifest()
    
    if manifest_path_no_date:
        console.print(f"[green]✓[/green] Manifest created: {manifest_path_no_date}")
    else:
        console.print("[yellow]⚠️  No manifest created (expected behavior)[/yellow]")
    
    # Test 3: Check directory structure
    console.print("\n[bold blue]Test 3: Directory structure[/bold blue]")
    output_dir = Path("test_manifest_output")
    if output_dir.exists():
        console.print(f"[green]✓[/green] Output directory created: {output_dir}")
        byop_dir = output_dir / "byop"
        if byop_dir.exists():
            console.print(f"[green]✓[/green] BYOP subdirectory created: {byop_dir}")
        else:
            console.print("[red]✗[/red] BYOP subdirectory not created")
    else:
        console.print("[red]✗[/red] Output directory not created")

if __name__ == "__main__":
    test_manifest_generation() 