"""
Tests for the BYOP packager module.

This module contains comprehensive tests for the BYOPPackager class, which is responsible
for creating unified BYOP packages from multiple chart sources (DFS, FAA Sectional, FAA Terminal).

What is a unified BYOP package?
-------------------------------
A unified package combines charts from multiple sources into a single BYOP package:
- DFS charts: PDF files in byop/ directory
- FAA Sectional charts: MBTiles files in layers/ directory
- FAA Terminal charts: MBTiles files in layers/ directory
- Single manifest.json file describing the entire package

What is being tested?
---------------------
- Package initialization and directory structure
- Adding chart sources
- Setting version information
- Manifest file generation
- Package summary statistics
"""

import pytest
from pathlib import Path
import tempfile
import json

from src.byop_packager import BYOPPackager


class TestBYOPPackager:
    """
    Test cases for BYOPPackager class.
    
    Each test verifies a specific aspect of package creation and management.
    """

    def test_init(self):
        """
        Test that BYOP packager initializes correctly.
        
        What this test does:
        - Creates a BYOPPackager instance
        - Verifies that output directories are created
        - Checks that required subdirectories exist
        
        Why this matters:
        - BYOP format requires specific directory structure
        - Directories must exist before files can be added
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            
            # Check that output directory was set
            assert packager.output_dir == Path(tmpdir)
            
            # Check that byop subdirectory was created
            byop_dir = packager.output_dir / "byop"
            assert byop_dir.exists()
            assert byop_dir.is_dir()
            
            # Check that layers subdirectory was created
            layers_dir = packager.output_dir / "layers"
            assert layers_dir.exists()
            assert layers_dir.is_dir()
            
            # Check that sources list is initialized
            assert isinstance(packager.sources, list)
            assert len(packager.sources) == 0
            
            # Check that version is None initially
            assert packager.version is None

    def test_init_default_output_dir(self):
        """
        Test initialization with default output directory name.
        
        What this test does:
        - Tests that default directory name is used when not specified
        - Verifies directory is created in current working directory
        
        Why this matters:
        - Default behavior should work without configuration
        """
        # Use a temporary directory as working directory
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            try:
                # Change to temp directory
                import os
                os.chdir(tmpdir)
                
                # Create packager with default name
                packager = BYOPPackager()
                
                # Should create "VFR Charts Package" directory
                assert packager.output_dir.name == "VFR Charts Package"
                assert packager.output_dir.exists()
            finally:
                # Restore original working directory
                os.chdir(original_cwd)

    def test_add_source(self):
        """
        Test adding chart sources to the package.
        
        What this test does:
        - Tests adding different chart sources
        - Verifies that sources are stored correctly
        - Checks that duplicate sources are not added
        
        Why this matters:
        - Packages can contain charts from multiple sources
        - Sources are listed in the manifest file
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            
            # Initially no sources
            assert len(packager.sources) == 0
            
            # Add DFS source
            packager.add_source("DFS")
            assert "DFS" in packager.sources
            assert len(packager.sources) == 1
            
            # Add FAA Sectional source
            packager.add_source("FAA Sectional")
            assert "FAA Sectional" in packager.sources
            assert len(packager.sources) == 2
            
            # Add FAA Terminal source
            packager.add_source("FAA Terminal")
            assert "FAA Terminal" in packager.sources
            assert len(packager.sources) == 3
            
            # Try adding duplicate (should not add again)
            packager.add_source("DFS")
            assert len(packager.sources) == 3  # Still 3, not 4

    def test_set_version(self):
        """
        Test setting package version.
        
        What this test does:
        - Tests setting version string
        - Verifies that version is stored correctly
        
        Why this matters:
        - Versions track chart editions (e.g., "2025JUL25")
        - Version appears in manifest file
        - Helps users identify chart dates
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            
            # Initially no version
            assert packager.version is None
            
            # Set version
            test_version = "2025JUL25"
            packager.set_version(test_version)
            
            # Verify version was set
            assert packager.version == test_version

    def test_create_manifest_dfs_only(self):
        """
        Test creating manifest for DFS-only package.
        
        What this test does:
        - Tests manifest generation with only DFS charts
        - Verifies manifest content is correct
        - Checks JSON format is valid
        
        Why this matters:
        - Manifest files tell ForeFlight about the chart package
        - Different sources have different abbreviations and organization names
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            packager.add_source("DFS")
            packager.set_version("2025JUL25")
            
            # Create manifest
            result = packager.create_manifest()
            
            # Should return path to manifest
            assert result is not None
            assert isinstance(result, Path)
            assert result.exists()
            assert result.name == "manifest.json"
            
            # Verify manifest content
            manifest_data = json.loads(result.read_text())
            
            assert manifest_data["name"] == "VFR Charts Package 2025JUL25"
            assert manifest_data["abbreviation"] == "DFS"
            assert manifest_data["version"] == "2025JUL25"
            assert manifest_data["organizationName"] == "from DFS"
            assert manifest_data["sources"] == ["DFS"]

    def test_create_manifest_faa_sectional_only(self):
        """
        Test creating manifest for FAA Sectional-only package.
        
        What this test does:
        - Tests manifest with only FAA Sectional charts
        - Verifies abbreviation and organization name
        
        Why this matters:
        - Different chart types have different abbreviations
        - Sectional charts use "SEC" abbreviation
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            packager.add_source("FAA Sectional")
            packager.set_version("2025JUL25")
            
            result = packager.create_manifest()
            manifest_data = json.loads(result.read_text())
            
            assert manifest_data["abbreviation"] == "SEC"
            assert manifest_data["organizationName"] == "from FAA"
            assert "FAA Sectional" in manifest_data["sources"]

    def test_create_manifest_faa_terminal_only(self):
        """
        Test creating manifest for FAA Terminal-only package.
        
        What this test does:
        - Tests manifest with only FAA Terminal charts
        - Verifies abbreviation and organization name
        
        Why this matters:
        - Terminal charts use "TAC" abbreviation
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            packager.add_source("FAA Terminal")
            packager.set_version("2025JUL25")
            
            result = packager.create_manifest()
            manifest_data = json.loads(result.read_text())
            
            assert manifest_data["abbreviation"] == "TAC"
            assert manifest_data["organizationName"] == "from FAA"

    def test_create_manifest_unified_package(self):
        """
        Test creating manifest for unified package (all sources).
        
        What this test does:
        - Tests manifest with DFS + FAA Sectional + FAA Terminal
        - Verifies combined abbreviation and organization name
        
        Why this matters:
        - Unified packages combine multiple sources
        - Abbreviation should include all sources
        - Organization name should reflect all sources
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            packager.add_source("DFS")
            packager.add_source("FAA Sectional")
            packager.add_source("FAA Terminal")
            packager.set_version("2025JUL25")
            
            result = packager.create_manifest()
            manifest_data = json.loads(result.read_text())
            
            # Abbreviation should include all sources
            abbrev = manifest_data["abbreviation"]
            assert "DFS" in abbrev
            assert "SEC" in abbrev
            assert "TAC" in abbrev
            
            # Organization should mention both DFS and FAA
            org_name = manifest_data["organizationName"]
            assert "DFS" in org_name
            assert "FAA" in org_name
            
            # Sources list should have all three
            assert len(manifest_data["sources"]) == 3
            assert "DFS" in manifest_data["sources"]
            assert "FAA Sectional" in manifest_data["sources"]
            assert "FAA Terminal" in manifest_data["sources"]

    def test_create_manifest_without_version(self):
        """
        Test manifest creation when version is not set.
        
        What this test does:
        - Tests that current date is used when version is missing
        - Verifies manifest is still created successfully
        
        Why this matters:
        - Some workflows might not set version explicitly
        - Should use current date as fallback
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            packager.add_source("DFS")
            # Don't set version
            
            # Create manifest (should use current date)
            result = packager.create_manifest()
            
            # Should still create manifest
            assert result is not None
            
            # Verify version was set to current date
            assert packager.version is not None
            assert len(packager.version) > 0

    def test_get_package_summary_empty(self):
        """
        Test getting summary when package is empty.
        
        What this test does:
        - Tests summary with no files in package
        - Verifies that counts are zero
        
        Why this matters:
        - Summary helps users see what's in the package
        - Should handle empty packages gracefully
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            
            # Get summary (no files yet)
            summary = packager.get_package_summary()
            
            # Should return zero counts
            assert summary["total_pdfs"] == 0
            assert summary["total_mbtiles"] == 0
            assert summary["byop_files"] == 0
            assert summary["layers_files"] == 0

    def test_get_package_summary_with_files(self):
        """
        Test getting summary with actual files in package.
        
        What this test does:
        - Creates test PDF and MBTiles files
        - Tests counting files correctly
        - Verifies summary statistics
        
        Why this matters:
        - Users need to know how many charts are in the package
        - Summary helps verify successful processing
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            
            # Create test files
            byop_dir = packager.output_dir / "byop"
            layers_dir = packager.output_dir / "layers"
            
            # Create PDF files
            (byop_dir / "EDFE_Visual_Chart1.PDF").touch()
            (byop_dir / "EDFE_Visual_Chart2.PDF").touch()
            
            # Create MBTiles files
            (layers_dir / "S_Anchorage.mbtiles").touch()
            (layers_dir / "T_Atlanta.mbtiles").touch()
            (layers_dir / "S_Chicago.mbtiles").touch()
            
            # Get summary
            summary = packager.get_package_summary()
            
            # Should count files correctly
            assert summary["total_pdfs"] == 2
            assert summary["total_mbtiles"] == 3
            assert summary["byop_files"] == 2
            assert summary["layers_files"] == 3

    def test_display_summary(self):
        """
        Test displaying package summary.
        
        What this test does:
        - Tests the display_summary method
        - Verifies that it doesn't crash (output is hard to test)
        
        Why this matters:
        - Users need visual feedback about package contents
        - Should display information clearly
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            packager.add_source("DFS")
            packager.set_version("2025JUL25")
            
            # Create some test files
            byop_dir = packager.output_dir / "byop"
            layers_dir = packager.output_dir / "layers"
            (byop_dir / "test1.PDF").touch()
            (layers_dir / "test1.mbtiles").touch()
            
            # Should not crash when displaying summary
            # (We can't easily test the output, but we can verify it runs)
            try:
                packager.display_summary()
                # If we get here, it didn't crash
                assert True
            except Exception as e:
                pytest.fail(f"display_summary raised exception: {e}")

    def test_multiple_sources_ordering(self):
        """
        Test that sources are added in the correct order.
        
        What this test does:
        - Tests adding sources in different orders
        - Verifies that order is preserved
        
        Why this matters:
        - Order might matter for display or processing
        - Should maintain order of addition
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = BYOPPackager(output_dir=tmpdir)
            
            # Add sources in specific order
            packager.add_source("FAA Terminal")
            packager.add_source("DFS")
            packager.add_source("FAA Sectional")
            
            # Verify order is preserved
            assert packager.sources[0] == "FAA Terminal"
            assert packager.sources[1] == "DFS"
            assert packager.sources[2] == "FAA Sectional"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

