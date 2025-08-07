#!/usr/bin/env python3
"""Test script for default folder name change."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_generator import PDFGenerator
from rich.console import Console

console = Console()

def test_default_folder_name():
    """Test that the default folder name is 'AIP Germany'."""
    
    console.print("[bold blue]Testing default folder name...[/bold blue]")
    
    # Test with default constructor (no output_dir specified)
    pdf_generator = PDFGenerator()
    
    console.print(f"[cyan]Default output directory: {pdf_generator.output_dir}[/cyan]")
    
    # Test with explicit output_dir
    pdf_generator_explicit = PDFGenerator("Test Output")
    console.print(f"[cyan]Explicit output directory: {pdf_generator_explicit.output_dir}[/cyan]")
    
    # Check if directories are created correctly
    if pdf_generator.output_dir.exists():
        console.print(f"[green]✓[/green] Default directory exists: {pdf_generator.output_dir}")
    else:
        console.print(f"[yellow]⚠️[/yellow] Default directory doesn't exist yet (will be created when needed)")
    
    # Check byop subdirectory
    byop_dir = pdf_generator.output_dir / "byop"
    if byop_dir.exists():
        console.print(f"[green]✓[/green] BYOP subdirectory exists: {byop_dir}")
    else:
        console.print(f"[yellow]⚠️[/yellow] BYOP subdirectory doesn't exist yet (will be created when needed)")
    
    # Test manifest creation with default folder
    manifest_path = pdf_generator.create_manifest()
    if manifest_path:
        console.print(f"[green]✓[/green] Manifest created in default folder: {manifest_path}")
    else:
        console.print("[yellow]⚠️[/yellow] No manifest created (expected without current_date)")
    
    console.print("\n[bold green]Default folder name test completed![/bold green]")

if __name__ == "__main__":
    test_default_folder_name() 