"""
Tests for the FAA scraper module.

This module contains comprehensive tests for the FAAScraper class, which is responsible
for scraping VFR raster charts from the FAA website.

What is being tested?
---------------------
- Scraping FAA VFR charts page HTML
- Extracting Sectional chart information
- Extracting Terminal Area chart information
- Downloading ZIP files
- Extracting GeoTIFF files from ZIP archives
"""

import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import zipfile
import tempfile

from src.faa_scraper import FAAScraper


class TestFAAScraper:
    """
    Test cases for FAAScraper class.
    
    Each test method verifies a specific piece of functionality.
    """

    def test_init(self):
        """
        Test that the FAA scraper initializes correctly.
        
        What this test does:
        - Creates a new FAAScraper instance
        - Verifies default values are set correctly
        - Checks that session headers are configured
        
        Why this matters:
        - Proper initialization ensures the scraper is ready to use
        - Headers make requests look like a real browser
        """
        scraper = FAAScraper()
        
        # Check default base URL (FAA website)
        assert scraper.base_url == "https://www.faa.gov"
        
        # Check default rate limit (prevents overwhelming the server)
        assert scraper.rate_limit == 1.0
        
        # Check that session has User-Agent header
        assert "User-Agent" in scraper.session.headers
        
        # Check that last_request_time is initialized
        assert scraper.last_request_time == 0

    def test_init_with_custom_parameters(self):
        """
        Test initialization with custom parameters.
        
        What this test does:
        - Creates scraper with custom base_url and rate_limit
        - Verifies custom values are used
        
        Why this matters:
        - Allows testing against different servers
        - Useful for development/testing environments
        """
        custom_url = "https://test.example.com"
        custom_rate = 2.5
        
        scraper = FAAScraper(base_url=custom_url, rate_limit=custom_rate)
        
        assert scraper.base_url == custom_url
        assert scraper.rate_limit == custom_rate

    @patch('src.faa_scraper.FAAScraper._make_request')
    def test_get_vfr_page(self, mock_make_request):
        """
        Test getting the FAA VFR Raster Charts page.
        
        What this test does:
        - Mocks the HTTP request to avoid making real network calls
        - Verifies that the correct URL is requested
        - Checks that HTML content is returned
        
        Why this matters:
        - This is the first step in scraping FAA charts
        - The HTML contains links to chart download pages
        """
        scraper = FAAScraper()
        
        # Create mock response
        mock_response = Mock()
        mock_response.text = "<html><body>FAA VFR Page</body></html>"
        mock_make_request.return_value = mock_response
        
        # Call the method
        result = scraper.get_vfr_page()
        
        # Verify result
        assert result == "<html><body>FAA VFR Page</body></html>"
        
        # Verify correct URL was requested
        mock_make_request.assert_called_once()
        call_url = mock_make_request.call_args[0][0]
        assert "faa.gov" in call_url
        assert "vfr" in call_url.lower()

    def test_extract_sectional_charts(self):
        """
        Test extracting Sectional chart information from HTML.
        
        What this test does:
        - Tests parsing HTML table to find Sectional charts
        - Verifies that chart names, URLs, and dates are extracted
        - Checks that only Sectional charts (not Terminal) are returned
        
        Why this matters:
        - Sectional charts are different from Terminal charts
        - We need correct URLs to download the charts
        - Edition dates help track chart versions
        """
        scraper = FAAScraper()
        
        # HTML with Sectional charts table
        html = """
        <html>
            <body>
                <h2>Sectional Aeronautical Raster Charts</h2>
                <table>
                    <tr>
                        <th>Chart Name</th>
                        <th>Current Edition</th>
                    </tr>
                    <tr>
                        <td>Anchorage</td>
                        <td>
                            Nov 27 2025
                            <a href="/sectional-files/Anchorage.zip">GEO-TIFF</a>
                        </td>
                    </tr>
                    <tr>
                        <td>Atlanta</td>
                        <td>
                            Dec 1 2025
                            <a href="/sectional-files/Atlanta.zip">GEO-TIFF</a>
                        </td>
                    </tr>
                </table>
            </body>
        </html>
        """
        
        # Extract charts
        result = scraper.extract_sectional_charts(html)
        
        # Should find 2 charts
        assert len(result) == 2
        
        # Check first chart
        chart1 = result[0]
        assert chart1["chart_name"] == "Anchorage"
        assert chart1["chart_type"] == "sectional"
        assert "/sectional-files/" in chart1["geo_tiff_url"]
        assert chart1["geo_tiff_url"].endswith(".zip")
        # Edition date extraction uses regex, so it should extract the date part
        assert chart1["edition_date"] == "Nov 27 2025"
        
        # Check second chart
        chart2 = result[1]
        assert chart2["chart_name"] == "Atlanta"
        assert chart2["chart_type"] == "sectional"

    def test_extract_sectional_charts_no_table(self):
        """
        Test handling when Sectional charts table is not found.
        
        What this test does:
        - Tests error handling when HTML structure is unexpected
        - Verifies that empty list is returned (graceful degradation)
        
        Why this matters:
        - Website structure might change
        - We should handle missing data gracefully
        """
        scraper = FAAScraper()
        
        # HTML without Sectional charts table
        html = "<html><body>No charts here</body></html>"
        
        # Should return empty list, not crash
        result = scraper.extract_sectional_charts(html)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_terminal_charts(self):
        """
        Test extracting Terminal Area chart information from HTML.
        
        What this test does:
        - Tests parsing HTML table to find Terminal Area charts
        - Verifies that chart names, URLs, and dates are extracted
        - Checks that only Terminal charts (not Sectional) are returned
        
        Why this matters:
        - Terminal charts are different from Sectional charts
        - Different chart types go to different directories
        """
        scraper = FAAScraper()
        
        # HTML with Terminal Area charts table
        html = """
        <html>
            <body>
                <h2>VFR Terminal Area Raster Charts</h2>
                <table>
                    <tr>
                        <th>Chart Name</th>
                        <th>Current Edition</th>
                    </tr>
                    <tr>
                        <td>Anchorage-Fairbanks</td>
                        <td>
                            Nov 27 2025
                            <a href="/tac-files/Anchorage-Fairbanks.zip">GEO-TIFF</a>
                        </td>
                    </tr>
                    <tr>
                        <td>Atlanta</td>
                        <td>
                            Dec 1 2025
                            <a href="/tac-files/Atlanta.zip">GEO-TIFF</a>
                        </td>
                    </tr>
                </table>
            </body>
        </html>
        """
        
        # Extract charts
        result = scraper.extract_terminal_charts(html)
        
        # Should find 2 charts
        assert len(result) == 2
        
        # Check first chart
        chart1 = result[0]
        assert chart1["chart_name"] == "Anchorage-Fairbanks"
        assert chart1["chart_type"] == "terminal"
        assert "/tac-files/" in chart1["geo_tiff_url"]  # Terminal charts use tac-files
        assert chart1["geo_tiff_url"].endswith(".zip")
        assert chart1["edition_date"] == "Nov 27 2025"

    def test_extract_terminal_charts_no_table(self):
        """
        Test handling when Terminal charts table is not found.
        
        What this test does:
        - Tests graceful handling of missing data
        """
        scraper = FAAScraper()
        
        html = "<html><body>No terminal charts here</body></html>"
        
        result = scraper.extract_terminal_charts(html)
        assert isinstance(result, list)
        assert len(result) == 0

    @patch('src.faa_scraper.FAAScraper._make_request')
    def test_download_zip_file(self, mock_make_request, tmp_path):
        """
        Test downloading a ZIP file.
        
        What this test does:
        - Mocks the HTTP request to simulate downloading a file
        - Verifies that the file is saved to disk correctly
        - Tests with a temporary directory (tmp_path is provided by pytest)
        
        Why tmp_path?
        - pytest provides tmp_path fixture for temporary directories
        - Files are automatically cleaned up after the test
        - No need to manually clean up test files
        
        Why this matters:
        - ZIP files contain the GeoTIFF chart images
        - Files must be saved correctly before extraction
        """
        scraper = FAAScraper()
        
        # Create mock response with ZIP file content
        zip_content = b"PK\x03\x04fake zip content"  # ZIP files start with PK
        mock_response = Mock()
        mock_response.iter_content.return_value = [zip_content]
        mock_make_request.return_value = mock_response
        
        # Test URL and output path
        test_url = "https://www.faa.gov/sectional-files/test.zip"
        output_path = tmp_path / "test.zip"
        
        # Download the file
        result = scraper.download_zip_file(test_url, output_path)
        
        # Should succeed
        assert result is True
        
        # Verify file was created
        assert output_path.exists()
        
        # Verify file content
        assert output_path.read_bytes() == zip_content

    def test_extract_geotiff_from_zip(self, tmp_path):
        """
        Test extracting GeoTIFF file from ZIP archive.
        
        What this test does:
        - Creates a test ZIP file with a GeoTIFF inside
        - Tests extracting the GeoTIFF file
        - Verifies that the correct file is extracted
        
        Why this matters:
        - GeoTIFF files are the actual chart images
        - We need to extract them from ZIP archives before conversion
        """
        scraper = FAAScraper()
        
        # Create a test ZIP file
        zip_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extracted"
        
        # Create ZIP with a GeoTIFF file inside
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Add a fake GeoTIFF file
            zf.writestr("chart.tif", b"fake geotiff content")
            zf.writestr("readme.txt", b"readme content")  # Non-TIFF file
        
        # Extract GeoTIFF
        result = scraper.extract_geotiff_from_zip(zip_path, extract_dir)
        
        # Should return path to extracted file
        assert result is not None
        assert isinstance(result, Path)
        assert result.exists()
        assert result.name == "chart.tif"

    def test_extract_geotiff_from_zip_no_tif(self, tmp_path):
        """
        Test handling when ZIP contains no GeoTIFF files.
        
        What this test does:
        - Tests error handling when ZIP has no .tif files
        - Verifies that None is returned (not an exception)
        
        Why this matters:
        - Some ZIP files might not contain GeoTIFFs
        - We should handle this gracefully
        """
        scraper = FAAScraper()
        
        # Create ZIP without GeoTIFF files
        zip_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extracted"
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("readme.txt", b"readme content")
        
        # Should return None, not crash
        result = scraper.extract_geotiff_from_zip(zip_path, extract_dir)
        assert result is None

    def test_extract_geotiff_from_zip_prefers_tac(self, tmp_path):
        """
        Test that Terminal charts prefer TAC files over FLY files.
        
        What this test does:
        - Tests that when both TAC and FLY files exist, TAC is preferred
        - Verifies FLY files are skipped when TAC files are available
        
        Why this matters:
        - Terminal charts can have both TAC and FLY files
        - We only want TAC files (FLY files are for different purposes)
        """
        scraper = FAAScraper()
        
        zip_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extracted"
        
        # Create ZIP with both TAC and FLY files
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("chart_TAC.tif", b"TAC content")
            zf.writestr("chart_FLY.tif", b"FLY content")
        
        # Extract - should prefer TAC
        result = scraper.extract_geotiff_from_zip(zip_path, extract_dir)
        
        assert result is not None
        assert "TAC" in result.name or "tac" in result.name.lower()

    @patch('src.faa_scraper.FAAScraper.get_vfr_page')
    @patch('src.faa_scraper.FAAScraper.extract_sectional_charts')
    @patch('src.faa_scraper.FAAScraper.extract_terminal_charts')
    def test_scrape_charts_sectional_only(self, mock_terminal, mock_sectional, mock_get_page):
        """
        Test scraping only Sectional charts.
        
        What this test does:
        - Tests the scrape_charts method with only "sectional" chart type
        - Verifies that only Sectional charts are returned
        - Mocks all the internal methods to avoid real network calls
        
        Why this matters:
        - Users might want only Sectional or only Terminal charts
        - The method should handle different chart type requests
        """
        scraper = FAAScraper()
        
        # Set up mocks
        mock_get_page.return_value = "<html>VFR page</html>"
        mock_sectional.return_value = [
            {"chart_name": "Anchorage", "chart_type": "sectional"},
            {"chart_name": "Atlanta", "chart_type": "sectional"},
        ]
        mock_terminal.return_value = []  # Should not be called
        
        # Scrape only Sectional charts
        result = scraper.scrape_charts(chart_types=["sectional"], limit=None, verbose=False)
        
        # Should return Sectional charts only
        assert len(result) == 2
        assert all(chart["chart_type"] == "sectional" for chart in result)
        
        # Verify Terminal extraction was not called
        mock_terminal.assert_not_called()

    @patch('src.faa_scraper.FAAScraper.get_vfr_page')
    @patch('src.faa_scraper.FAAScraper.extract_sectional_charts')
    @patch('src.faa_scraper.FAAScraper.extract_terminal_charts')
    def test_scrape_charts_with_limit(self, mock_terminal, mock_sectional, mock_get_page):
        """
        Test scraping charts with a limit.
        
        What this test does:
        - Tests that the limit parameter works correctly
        - Verifies that only the specified number of charts are returned
        
        Why this matters:
        - Limits are useful for testing (don't process all charts)
        - Helps with faster development iterations
        """
        scraper = FAAScraper()
        
        # Create many charts
        many_charts = [
            {"chart_name": f"Chart{i}", "chart_type": "sectional"}
            for i in range(10)
        ]
        
        mock_get_page.return_value = "<html>VFR page</html>"
        mock_sectional.return_value = many_charts
        
        # Scrape with limit of 3
        result = scraper.scrape_charts(chart_types=["sectional"], limit=3, verbose=False)
        
        # Should return only 3 charts
        assert len(result) == 3

    @patch('src.faa_scraper.FAAScraper.download_zip_file')
    @patch('src.faa_scraper.FAAScraper.extract_geotiff_from_zip')
    def test_download_and_extract_charts(self, mock_extract, mock_download, tmp_path):
        """
        Test downloading and extracting multiple charts.
        
        What this test does:
        - Tests the batch download and extraction process
        - Verifies that charts are processed correctly
        - Checks that geotiff_path is added to chart dictionaries
        
        Why this matters:
        - This is the main workflow for processing FAA charts
        - Multiple charts need to be processed efficiently
        """
        scraper = FAAScraper()
        
        # Test charts
        charts = [
            {
                "chart_name": "Anchorage",
                "chart_type": "sectional",
                "geo_tiff_url": "https://example.com/anchorage.zip",
            },
            {
                "chart_name": "Atlanta",
                "chart_type": "sectional",
                "geo_tiff_url": "https://example.com/atlanta.zip",
            },
        ]
        
        download_dir = tmp_path / "downloads"
        extract_dir = tmp_path / "extracted"
        
        # Set up mocks
        mock_download.return_value = True  # Download succeeds
        mock_extract.side_effect = [
            extract_dir / "anchorage.tif",  # First extraction
            extract_dir / "atlanta.tif",    # Second extraction
        ]
        
        # Process charts
        result = scraper.download_and_extract_charts(
            charts, download_dir, extract_dir, verbose=False
        )
        
        # Should return charts with geotiff_path added
        assert len(result) == 2
        assert "geotiff_path" in result[0]
        assert "geotiff_path" in result[1]
        
        # Verify download was called for each chart
        assert mock_download.call_count == 2
        
        # Verify extract was called for each chart
        assert mock_extract.call_count == 2


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v"])

