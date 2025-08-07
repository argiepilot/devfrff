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
        assert scraper.sanitize_filename("Test Chart") == "Test Chart"
        assert scraper.sanitize_filename("Test<Chart>") == "Test_Chart_"
        assert scraper.sanitize_filename("  Test  Chart  ") == "Test Chart"

    @patch('src.scraper.requests.Session.get')
    def test_get_aerodrome_list_page(self, mock_get):
        """Test getting aerodrome list page."""
        mock_response = Mock()
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        scraper = AIPScraper()
        result = scraper.get_aerodrome_list_page()
        
        assert result == "<html><body>Test content</body></html>"
        mock_get.assert_called_once()

    def test_extract_aerodrome_links(self):
        """Test aerodrome link extraction."""
        scraper = AIPScraper()
        
        # Mock HTML with aerodrome links
        html = """
        <html>
            <body>
                <a href="pages/123456.html">EDFE Frankfurt-Egelsbach 5</a>
                <a href="pages/789012.html">EDDF Frankfurt-Main 3</a>
                <a href="other.html">Not an aerodrome</a>
            </body>
        </html>
        """
        
        result = scraper.extract_aerodrome_links(html)
        
        assert len(result) == 2
        assert result[0][0] == "EDFE"  # ICAO code
        assert result[0][1] == "Frankfurt-Egelsbach 5"  # Name
        assert result[1][0] == "EDDF"  # ICAO code
        assert result[1][1] == "Frankfurt-Main 3"  # Name


if __name__ == "__main__":
    pytest.main([__file__]) 