"""
Tests for the PDF generator module.

This module contains comprehensive tests for the PDFGenerator class, which is responsible
for converting chart images to PDF files in the ForeFlight BYOP format.

What is BYOP?
------------
BYOP stands for "Bring Your Own Paper" - it's ForeFlight's format for custom charts.
Charts must be:
- PDF format
- Named according to specific conventions (ICAO_Visual_ChartName.PDF or ICAO_Info_ChartName.PDF)
- Placed in a "byop" subdirectory
- Accompanied by a manifest.json file

What is being tested?
---------------------
- PDF generation from image data
- BYOP filename generation (naming conventions)
- Filename sanitization
- Directory structure creation
- Manifest file generation

Note: These tests require the img2pdf dependency. If not installed, tests will be skipped.
"""

import pytest

# Check if img2pdf is available, skip all tests in this module if not
try:
    import img2pdf
    IMG2PDF_AVAILABLE = True
except ImportError:
    IMG2PDF_AVAILABLE = False
    pytest.skip("img2pdf not available, skipping PDF generator tests", allow_module_level=True)

from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import tempfile
import shutil

from src.pdf_generator import PDFGenerator


class TestPDFGenerator:
    """
    Test cases for PDFGenerator class.
    
    Each test verifies a specific aspect of PDF generation and BYOP formatting.
    """

    def test_init(self):
        """
        Test that PDF generator initializes correctly.
        
        What this test does:
        - Creates a PDFGenerator instance
        - Verifies that output directories are created
        - Checks that required subdirectories exist
        
        Why this matters:
        - BYOP format requires specific directory structure
        - Directories must exist before files can be saved
        """
        # Use temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Check that output directory was set
            assert generator.output_dir == Path(tmpdir)
            
            # Check that byop subdirectory was created
            byop_dir = generator.output_dir / "byop"
            assert byop_dir.exists()
            assert byop_dir.is_dir()
            
            # Check that layers subdirectory was created (for unified packages)
            layers_dir = generator.output_dir / "layers"
            assert layers_dir.exists()
            assert layers_dir.is_dir()

    def test_init_with_current_date(self):
        """
        Test initialization with current_date parameter.
        
        What this test does:
        - Tests that current_date is stored correctly
        - Verifies it's used for manifest generation
        
        Why this matters:
        - Dates are used in manifest files to track chart versions
        - Different chart editions have different dates
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_date = "2025JUL25"
            generator = PDFGenerator(output_dir=tmpdir, current_date=test_date)
            
            assert generator.current_date == test_date

    def test_sanitize_filename(self):
        """
        Test filename sanitization for BYOP format.
        
        What this test does:
        - Tests removing/replacing invalid characters
        - Verifies that filenames are safe for filesystem
        
        Why this matters:
        - BYOP filenames must be valid for all operating systems
        - Invalid characters can cause file save errors
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Test basic sanitization
            result = generator.sanitize_filename("Test Chart")
            assert result == "Test Chart"
            
            # Test invalid characters (should be replaced with underscore)
            result = generator.sanitize_filename("Test<Chart>")
            assert "<" not in result
            assert ">" not in result
            
            # Test extra spaces (should be normalized)
            result = generator.sanitize_filename("  Test  Chart  ")
            assert result == "Test Chart"  # Trimmed and normalized

    def test_generate_byop_filename_visual_chart(self):
        """
        Test generating BYOP filename for Visual charts.
        
        What this test does:
        - Tests filename generation for regular visual charts
        - Verifies format: ICAO_Visual_ChartName.PDF
        
        Why this matters:
        - ForeFlight requires specific naming conventions
        - Wrong names mean charts won't be recognized
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Visual chart (not an AD/Info chart)
            chart_info = {
                "icao_code": "EDFE",
                "chart_name": "Frankfurt-Egelsbach 5",
            }
            
            filename = generator.generate_byop_filename(chart_info)
            
            # Should be: EDFE_Visual_Frankfurt-Egelsbach 5.PDF
            assert filename.startswith("EDFE_Visual_")
            assert filename.endswith(".PDF")
            assert "Frankfurt-Egelsbach 5" in filename

    def test_generate_byop_filename_info_chart(self):
        """
        Test generating BYOP filename for Info (AD) charts.
        
        What this test does:
        - Tests filename generation for AD charts (Info type)
        - Verifies format: ICAO_Info_ChartName.PDF
        
        Why this matters:
        - AD charts are a special type that need "Info_" prefix
        - Different chart types have different naming rules
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # AD chart (Info type)
            chart_info = {
                "icao_code": "EDFE",
                "chart_name": "AD Frankfurt-Egelsbach Information",
            }
            
            filename = generator.generate_byop_filename(chart_info)
            
            # Should be: EDFE_Info_AD Frankfurt-Egelsbach Information.PDF
            assert filename.startswith("EDFE_Info_")
            assert filename.endswith(".PDF")
            assert "AD" in filename

    def test_generate_byop_filename_removes_duplicate_icao(self):
        """
        Test that duplicate ICAO codes in chart names are removed.
        
        What this test does:
        - Tests handling of chart names that already include ICAO code
        - Verifies that duplicate ICAO is removed from filename
        
        Why this matters:
        - Some chart names already include the ICAO code
        - We don't want "EDFE_Visual_EDFE Chart Name" (duplicate ICAO)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Chart name that already includes ICAO code
            chart_info = {
                "icao_code": "EDFE",
                "chart_name": "EDFE Frankfurt-Egelsbach 5",  # ICAO already in name
            }
            
            filename = generator.generate_byop_filename(chart_info)
            
            # Should not have duplicate ICAO: EDFE_Visual_Frankfurt-Egelsbach 5.PDF
            # Not: EDFE_Visual_EDFE Frankfurt-Egelsbach 5.PDF
            parts = filename.split("_")
            assert parts[0] == "EDFE"  # First part is ICAO
            assert "Visual" in parts[1]  # Second part is type
            # Should not have EDFE again in the chart name part
            assert parts[2].startswith("Frankfurt")  # Chart name without duplicate ICAO

    @patch('src.pdf_generator.img2pdf.convert')
    def test_image_to_pdf(self, mock_convert, tmp_path):
        """
        Test converting image data to PDF.
        
        What this test does:
        - Mocks the img2pdf library to avoid actual PDF conversion
        - Verifies that PDF data is written to file correctly
        
        Why mock img2pdf?
        - PDF conversion can be slow
        - We're testing our code, not the img2pdf library
        - Mocking makes tests faster and more reliable
        
        Why this matters:
        - Image to PDF conversion is the core functionality
        - Files must be saved correctly for ForeFlight to read them
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Mock PDF conversion
            fake_pdf_data = b"fake pdf content"
            mock_convert.return_value = fake_pdf_data
            
            # Test image data (fake)
            image_data = b"fake image data"
            output_path = Path(tmpdir) / "test.pdf"
            
            # Convert to PDF
            result = generator.image_to_pdf(image_data, output_path)
            
            # Should succeed
            assert result is True
            
            # Verify PDF file was created
            assert output_path.exists()
            
            # Verify file content
            assert output_path.read_bytes() == fake_pdf_data

    @patch('src.pdf_generator.PDFGenerator.image_to_pdf')
    def test_process_chart(self, mock_image_to_pdf, tmp_path):
        """
        Test processing a single chart (download image -> create PDF).
        
        What this test does:
        - Tests the complete workflow for one chart
        - Verifies that PDF is created with correct filename
        - Checks that file is placed in byop subdirectory
        
        Why this matters:
        - This is the main method called for each chart
        - Must handle errors gracefully
        - Files must be in correct location for BYOP format
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Mock PDF conversion to succeed and actually create the file
            def mock_image_to_pdf_side_effect(image_data, output_path):
                # Actually create the file so the test can verify it exists
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"fake pdf content")
                return True
            
            mock_image_to_pdf.side_effect = mock_image_to_pdf_side_effect
            
            # Test chart data
            chart_info = {
                "icao_code": "EDFE",
                "chart_name": "Frankfurt-Egelsbach 5",
            }
            image_data = b"fake image data"
            
            # Process chart
            result = generator.process_chart(chart_info, image_data)
            
            # Should return path to created PDF
            assert result is not None
            assert isinstance(result, Path)
            assert result.exists()
            
            # Verify filename format
            assert result.name.startswith("EDFE_Visual_")
            assert result.name.endswith(".PDF")
            
            # Verify file is in byop directory
            assert "byop" in str(result)

    @patch('src.pdf_generator.PDFGenerator.process_chart')
    def test_process_charts_batch(self, mock_process_chart, tmp_path):
        """
        Test processing multiple charts in batch.
        
        What this test does:
        - Tests batch processing of multiple charts
        - Verifies that all charts are processed
        - Checks return value contains all successful PDFs
        
        Why this matters:
        - Processing many charts efficiently is important
        - Need to track which charts succeeded/failed
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Create test charts
            charts_with_images = [
                (
                    {"icao_code": "EDFE", "chart_name": "Chart 1"},
                    b"image1",
                ),
                (
                    {"icao_code": "EDDF", "chart_name": "Chart 2"},
                    b"image2",
                ),
            ]
            
            # Mock process_chart to return paths
            mock_process_chart.side_effect = [
                Path(tmpdir) / "byop" / "EDFE_Visual_Chart_1.PDF",
                Path(tmpdir) / "byop" / "EDDF_Visual_Chart_2.PDF",
            ]
            
            # Process batch
            result = generator.process_charts_batch(charts_with_images)
            
            # Should return dictionary of successful PDFs
            assert isinstance(result, dict)
            assert len(result) == 2
            
            # Verify process_chart was called for each chart
            assert mock_process_chart.call_count == 2

    def test_create_content_pack_structure(self):
        """
        Test creating BYOP content pack directory structure.
        
        What this test does:
        - Tests that all required directories are created
        - Verifies directory structure matches BYOP requirements
        
        Why this matters:
        - BYOP format requires specific directory structure
        - Missing directories cause errors
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Create structure
            generator.create_content_pack_structure()
            
            # Verify directories exist
            assert (Path(tmpdir) / "byop").exists()
            assert (Path(tmpdir) / "layers").exists()

    def test_create_manifest_with_date(self):
        """
        Test creating manifest.json file with current_date.
        
        What this test does:
        - Tests manifest file generation
        - Verifies that manifest contains correct information
        - Checks JSON format is valid
        
        Why this matters:
        - Manifest files tell ForeFlight about the chart package
        - Wrong format means ForeFlight won't recognize the package
        - Dates track chart versions
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir, current_date="2025JUL25")
            
            # Create manifest
            result = generator.create_manifest()
            
            # Should return path to manifest
            assert result is not None
            assert isinstance(result, Path)
            assert result.exists()
            assert result.name == "manifest.json"
            
            # Verify manifest content
            import json
            manifest_data = json.loads(result.read_text())
            
            assert manifest_data["name"] == "AIP VFR Germany 2025JUL25"
            assert manifest_data["abbreviation"] == "VFR GER"
            assert manifest_data["version"] == "2025JUL25"
            assert manifest_data["organizationName"] == "from DFS"

    def test_create_manifest_without_date(self):
        """
        Test manifest creation when current_date is not set.
        
        What this test does:
        - Tests error handling when date is missing
        - Verifies that None is returned (graceful failure)
        
        Why this matters:
        - Some workflows might not have dates available
        - Should handle missing data gracefully
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            # Don't set current_date
            
            # Create manifest (should fail gracefully)
            result = generator.create_manifest()
            
            # Should return None when date is missing
            assert result is None

    def test_get_generated_files_summary(self):
        """
        Test getting summary of generated PDF files.
        
        What this test does:
        - Tests counting PDF files in byop directory
        - Verifies summary statistics are correct
        
        Why this matters:
        - Users need to know how many charts were generated
        - Summary helps verify successful processing
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Create some fake PDF files
            byop_dir = Path(tmpdir) / "byop"
            byop_dir.mkdir(exist_ok=True)
            
            # Create test PDF files
            (byop_dir / "EDFE_Visual_Chart1.PDF").touch()
            (byop_dir / "EDFE_Visual_Chart2.PDF").touch()
            (byop_dir / "EDDF_Visual_Chart3.PDF").touch()
            
            # Get summary
            summary = generator.get_generated_files_summary()
            
            # Should count 3 PDFs
            assert summary["total_pdfs"] == 3
            assert summary["byop_files"] == 3

    def test_get_generated_files_summary_empty(self):
        """
        Test summary when no PDFs have been generated yet.
        
        What this test does:
        - Tests summary with empty directory
        - Verifies that counts are zero
        
        Why this matters:
        - Should handle empty directories gracefully
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PDFGenerator(output_dir=tmpdir)
            
            # Get summary (no PDFs created yet)
            summary = generator.get_generated_files_summary()
            
            # Should return zero counts
            assert summary["total_pdfs"] == 0
            assert summary["byop_files"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

