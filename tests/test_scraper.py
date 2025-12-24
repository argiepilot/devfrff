"""Tests for the AIP scraper module."""

import pytest
from unittest.mock import Mock, patch

from src.scraper import AIPScraper


class TestAIPScraper:
    """Test cases for AIPScraper class."""

    def test_init(self):
        """Test scraper initialization."""
        scraper = AIPScraper()
        assert scraper.base_url == "https://aip.dfs.de"
        assert "User-Agent" in scraper.session.headers

    def test_build_print_url(self):
        """Test print URL building."""
        scraper = AIPScraper()
        page_id = "51B96FC66F7767D88BE754F64116ABC3"
        chart_name = "EDFE Frankfurt-Egelsbach 5"
        
        expected_url = (
            "https://aip.dfs.de/basicVFR/print/AD/"
            "51B96FC66F7767D88BE754F64116ABC3/"
            "EDFE%20Frankfurt-Egelsbach%205"
        )
        
        result = scraper._build_print_url(page_id, chart_name)
        assert result == expected_url

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        scraper = AIPScraper()
        
        # Test basic sanitization
        # Note: sanitize_filename replaces spaces with underscores
        # and replaces invalid characters (<, >, etc.) with underscores
        # Multiple consecutive underscores/spaces are collapsed to a single underscore
        assert scraper.sanitize_filename("Test Chart") == "Test_Chart"
        assert scraper.sanitize_filename("Test<Chart>") == "Test_Chart"  # < and > become _, then collapsed
        assert scraper.sanitize_filename("  Test  Chart  ") == "Test_Chart"  # Spaces become _, then collapsed

    @patch('src.scraper.AIPScraper._make_request')
    @patch('src.scraper.AIPScraper.get_main_aip_page')
    @patch('src.scraper.AIPScraper.extract_vfr_online_link')
    @patch('src.scraper.AIPScraper.extract_aerodromes_section_link')
    def test_get_aerodrome_list_page(
        self, mock_extract_aerodromes, mock_extract_vfr, mock_get_main, mock_make_request
    ):
        """Test getting aerodrome list page."""
        # Mock the chain of method calls
        mock_get_main.return_value = "<html><body>Main AIP page</body></html>"
        mock_extract_vfr.return_value = "https://aip.dfs.de/basicVFR/2025JAN01/"
        
        # Mock VFR Online response
        mock_vfr_response = Mock()
        mock_vfr_response.text = "<html><body>VFR Online page</body></html>"
        # Date format must match regex: \d{4}[A-Z]{3}\d{2} (e.g., 2025JAN01)
        mock_vfr_response.url = "https://aip.dfs.de/basicVFR/2025JAN01/"
        
        # Mock aerodromes section response
        mock_aerodromes_response = Mock()
        mock_aerodromes_response.text = "<html><body>Aerodromes page</body></html>"
        
        mock_extract_aerodromes.return_value = "https://aip.dfs.de/basicVFR/2025JAN01/AD"
        
        # Set up _make_request to return different responses based on URL
        def make_request_side_effect(url):
            if "basicVFR" in url and "AD" not in url:
                return mock_vfr_response
            return mock_aerodromes_response
        
        mock_make_request.side_effect = make_request_side_effect
        
        scraper = AIPScraper()
        result = scraper.get_aerodrome_list_page()
        
        assert result == "<html><body>Aerodromes page</body></html>"
        mock_get_main.assert_called_once()
        mock_extract_vfr.assert_called_once()
        assert mock_make_request.call_count == 2  # Called for VFR Online and aerodromes

    @patch('src.scraper.AIPScraper.get_aerodromes_from_section')
    def test_extract_aerodrome_links(self, mock_get_aerodromes):
        """Test aerodrome link extraction."""
        scraper = AIPScraper()
        
        # Mock HTML with alphabetical section links (folder-link structure)
        html = """
        <html>
            <body>
                <a href="/basicVFR/2025JAN01/AD/A-B" class="folder-link">
                    <span class="folder-name">A-B</span>
                </a>
                <a href="/basicVFR/2025JAN01/AD/C-D" class="folder-link">
                    <span class="folder-name">C-D</span>
                </a>
            </body>
        </html>
        """
        
        # Mock get_aerodromes_from_section to return aerodromes for each section
        mock_get_aerodromes.side_effect = [
            [("EDFE", "Frankfurt-Egelsbach 5", "url1")],  # First section
            [("EDDF", "Frankfurt-Main 3", "url2")],  # Second section
        ]
        
        result = scraper.extract_aerodrome_links(html)
        
        assert len(result) == 2
        assert result[0][0] == "EDFE"  # ICAO code
        assert result[0][1] == "Frankfurt-Egelsbach 5"  # Name
        assert result[1][0] == "EDDF"  # ICAO code
        assert result[1][1] == "Frankfurt-Main 3"  # Name
        assert mock_get_aerodromes.call_count == 2  # Called for each section


if __name__ == "__main__":
    pytest.main([__file__]) 