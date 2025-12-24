# Testing Documentation

This document provides comprehensive documentation for the test suite in this project. It explains how to run tests, what's being tested, and how to write new tests.

## Table of Contents

- [Overview](#overview)
- [Running Tests](#running-tests)
- [Test Structure](#test-structure)
- [Test Files](#test-files)
- [Writing New Tests](#writing-new-tests)
- [Test Concepts Explained](#test-concepts-explained)
- [Common Testing Patterns](#common-testing-patterns)
- [Troubleshooting](#troubleshooting)

## Overview

The test suite uses [pytest](https://docs.pytest.org/), a popular Python testing framework. Tests are located in the `tests/` directory and cover all major components of the application:

- **AIP Scraper**: Web scraping for DFS AIP VFR charts
- **FAA Scraper**: Web scraping for FAA VFR raster charts
- **PDF Generator**: PDF creation for ForeFlight BYOP format
- **BYOP Packager**: Unified package creation from multiple sources

### Test Statistics

- **Total Tests**: 42
- **Test Files**: 4
- **Coverage**: All major classes and methods

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest tests/

# Run with verbose output (shows each test name)
pytest tests/ -v

# Run specific test file
pytest tests/test_scraper.py

# Run specific test class
pytest tests/test_scraper.py::TestAIPScraper

# Run specific test method
pytest tests/test_scraper.py::TestAIPScraper::test_init

# Run tests and show coverage report (if pytest-cov is installed)
pytest tests/ --cov=src --cov-report=html
```

### Running Tests in Different Modes

```bash
# Run tests and stop at first failure
pytest tests/ -x

# Run tests and show local variables on failure
pytest tests/ -l

# Run tests in parallel (if pytest-xdist is installed)
pytest tests/ -n auto

# Run only tests that failed last time
pytest tests/ --lf

# Run tests matching a pattern
pytest tests/ -k "test_init"
```

## Test Structure

### Directory Layout

```
tests/
├── __init__.py              # Makes tests a Python package
├── test_scraper.py         # Tests for AIPScraper
├── test_faa_scraper.py     # Tests for FAAScraper
├── test_pdf_generator.py   # Tests for PDFGenerator
└── test_byop_packager.py   # Tests for BYOPPackager
```

### Test File Structure

Each test file follows this structure:

```python
"""
Module docstring explaining what's being tested.
"""

import pytest
from unittest.mock import Mock, patch
from src.module_name import ClassName


class TestClassName:
    """Test class for ClassName."""
    
    def test_method_name(self):
        """Test description."""
        # Test code here
        assert something == expected_value
```

## Test Files

### 1. `test_scraper.py` - AIP Scraper Tests

**Purpose**: Tests the `AIPScraper` class, which scrapes VFR aerodrome charts from the DFS AIP website.

**Test Coverage**:
- Initialization and configuration
- URL building and encoding
- Filename sanitization
- HTML parsing and link extraction
- Date extraction from URLs
- Section and aerodrome extraction
- Chart information extraction
- Cache management
- Multi-step navigation flow

**Key Tests**:
- `test_init`: Verifies scraper initializes with correct defaults
- `test_build_print_url`: Tests URL construction for chart downloads
- `test_extract_chart_info`: Tests parsing aerodrome pages for chart data
- `test_get_aerodrome_list_page_flow`: Tests complete navigation workflow

**Example Test**:
```python
def test_build_print_url(self):
    """Test that print URLs are built correctly."""
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
```

### 2. `test_faa_scraper.py` - FAA Scraper Tests

**Purpose**: Tests the `FAAScraper` class, which scrapes VFR raster charts from the FAA website.

**Test Coverage**:
- Initialization and configuration
- VFR page retrieval
- Sectional chart extraction
- Terminal Area chart extraction
- ZIP file downloading
- GeoTIFF extraction from ZIP files
- Batch processing
- Chart type filtering

**Key Tests**:
- `test_extract_sectional_charts`: Tests parsing HTML for Sectional charts
- `test_extract_terminal_charts`: Tests parsing HTML for Terminal charts
- `test_extract_geotiff_from_zip`: Tests extracting GeoTIFF files from ZIP archives
- `test_scrape_charts_with_limit`: Tests limiting number of charts processed

**Example Test**:
```python
def test_extract_sectional_charts(self):
    """Test extracting Sectional chart information from HTML."""
    scraper = FAAScraper()
    html = """
    <html>
        <table>
            <tr>
                <td>Anchorage</td>
                <td>
                    Nov 27 2025
                    <a href="/sectional-files/Anchorage.zip">GEO-TIFF</a>
                </td>
            </tr>
        </table>
    </html>
    """
    
    result = scraper.extract_sectional_charts(html)
    assert len(result) == 1
    assert result[0]["chart_name"] == "Anchorage"
```

### 3. `test_pdf_generator.py` - PDF Generator Tests

**Purpose**: Tests the `PDFGenerator` class, which converts chart images to PDF files in ForeFlight BYOP format.

**Test Coverage**:
- Initialization and directory creation
- Filename sanitization
- BYOP filename generation (Visual vs Info charts)
- Image to PDF conversion
- Batch processing
- Manifest file creation
- File summary statistics

**Key Tests**:
- `test_generate_byop_filename_visual_chart`: Tests Visual chart naming
- `test_generate_byop_filename_info_chart`: Tests Info (AD) chart naming
- `test_process_chart`: Tests complete chart processing workflow
- `test_create_manifest_with_date`: Tests manifest file generation

**Note**: This test file requires the `img2pdf` dependency. If not installed, the file will fail to import.

**Example Test**:
```python
def test_generate_byop_filename_visual_chart(self):
    """Test generating BYOP filename for Visual charts."""
    generator = PDFGenerator(output_dir=tmpdir)
    
    chart_info = {
        "icao_code": "EDFE",
        "chart_name": "Frankfurt-Egelsbach 5",
    }
    
    filename = generator.generate_byop_filename(chart_info)
    assert filename.startswith("EDFE_Visual_")
    assert filename.endswith(".PDF")
```

### 4. `test_byop_packager.py` - BYOP Packager Tests

**Purpose**: Tests the `BYOPPackager` class, which creates unified BYOP packages from multiple chart sources.

**Test Coverage**:
- Initialization and directory structure
- Adding chart sources
- Version management
- Manifest generation for different source combinations
- Package summary statistics
- Source ordering

**Key Tests**:
- `test_create_manifest_unified_package`: Tests manifest with all sources
- `test_get_package_summary_with_files`: Tests file counting
- `test_add_source`: Tests source management

**Example Test**:
```python
def test_create_manifest_unified_package(self):
    """Test creating manifest for unified package (all sources)."""
    packager = BYOPPackager(output_dir=tmpdir)
    packager.add_source("DFS")
    packager.add_source("FAA Sectional")
    packager.add_source("FAA Terminal")
    packager.set_version("2025JUL25")
    
    result = packager.create_manifest()
    manifest_data = json.loads(result.read_text())
    
    assert "DFS" in manifest_data["abbreviation"]
    assert "SEC" in manifest_data["abbreviation"]
    assert "TAC" in manifest_data["abbreviation"]
```

## Writing New Tests

### Test Naming Conventions

- Test files: `test_*.py`
- Test classes: `TestClassName`
- Test methods: `test_method_name` or `test_feature_description`

### Basic Test Template

```python
import pytest
from unittest.mock import Mock, patch
from src.your_module import YourClass


class TestYourClass:
    """Test cases for YourClass."""
    
    def test_feature_name(self):
        """
        Test description explaining what this test verifies.
        
        What this test does:
        - Step 1
        - Step 2
        
        Why this matters:
        - Reason 1
        - Reason 2
        """
        # Arrange: Set up test data
        instance = YourClass()
        test_input = "test value"
        
        # Act: Execute the code being tested
        result = instance.method(test_input)
        
        # Assert: Verify the result
        assert result == expected_value
```

### Using Mocks

Mocks are used to avoid making real network requests or file operations:

```python
@patch('src.scraper.AIPScraper._make_request')
def test_method_with_network_call(self, mock_make_request):
    """Test that uses mocked network call."""
    # Set up mock response
    mock_response = Mock()
    mock_response.text = "<html>Test</html>"
    mock_make_request.return_value = mock_response
    
    # Test code
    scraper = AIPScraper()
    result = scraper.get_main_aip_page()
    
    # Verify
    assert result == "<html>Test</html>"
    mock_make_request.assert_called_once()
```

### Using Temporary Directories

For tests that create files, use pytest's `tmp_path` fixture:

```python
def test_file_creation(self, tmp_path):
    """Test that creates files."""
    # tmp_path is automatically created and cleaned up
    output_file = tmp_path / "test.txt"
    
    # Your code that creates files
    output_file.write_text("test content")
    
    # Verify file exists
    assert output_file.exists()
    assert output_file.read_text() == "test content"
```

## Test Concepts Explained

### What is pytest?

**pytest** is a testing framework for Python that makes it easy to write and run tests. Key features:

- **Automatic test discovery**: Finds tests in `test_*.py` files
- **Simple assertions**: Use `assert` statements (no special syntax)
- **Fixtures**: Reusable test setup (like `tmp_path`)
- **Parametrization**: Run same test with different inputs
- **Plugins**: Extend functionality (coverage, parallel execution, etc.)

### What are Assertions?

Assertions check if something is `True`. If an assertion fails, the test fails:

```python
# Simple assertion
assert 1 + 1 == 2  # Passes

# Assertion with message
assert result == expected, f"Got {result}, expected {expected}"

# Assertion with pytest's helpful messages
assert result == expected  # pytest shows both values if it fails
```

### What is Mocking?

**Mocking** creates fake versions of external dependencies (like network requests, file operations) so tests:

- **Run faster**: No waiting for network/file I/O
- **Are reliable**: Don't depend on external services
- **Are isolated**: Don't affect real systems
- **Test error cases**: Can simulate failures easily

Example:
```python
from unittest.mock import Mock, patch

# Mock a function
@patch('module.function_name')
def test_something(mock_function):
    mock_function.return_value = "fake result"
    # Your test code here
```

### What are Fixtures?

**Fixtures** are reusable pieces of test setup. pytest provides built-in fixtures:

- `tmp_path`: Temporary directory (automatically cleaned up)
- `tmpdir`: Older temporary directory fixture
- `monkeypatch`: Modify environment variables, etc.

You can also create custom fixtures:

```python
@pytest.fixture
def sample_scraper():
    """Fixture that creates a scraper instance."""
    return AIPScraper(rate_limit=0.1)  # Fast for testing

def test_something(sample_scraper):
    """Test uses the fixture."""
    result = sample_scraper.method()
    assert result is not None
```

## Common Testing Patterns

### Testing Initialization

```python
def test_init(self):
    """Test that object initializes correctly."""
    obj = MyClass(param1="value1", param2="value2")
    assert obj.param1 == "value1"
    assert obj.param2 == "value2"
```

### Testing with Different Inputs

```python
@pytest.mark.parametrize("input,expected", [
    ("test1", "result1"),
    ("test2", "result2"),
    ("test3", "result3"),
])
def test_multiple_inputs(self, input, expected):
    """Test with multiple input values."""
    result = process(input)
    assert result == expected
```

### Testing Error Handling

```python
def test_error_handling(self):
    """Test that errors are handled correctly."""
    with pytest.raises(ValueError, match="error message"):
        function_that_raises_error()
```

### Testing File Operations

```python
def test_file_operations(self, tmp_path):
    """Test file creation and reading."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    
    assert file_path.exists()
    assert file_path.read_text() == "content"
```

### Testing Batch Operations

```python
def test_batch_processing(self):
    """Test processing multiple items."""
    items = [1, 2, 3, 4, 5]
    results = process_batch(items)
    
    assert len(results) == len(items)
    assert all(r is not None for r in results)
```

## Troubleshooting

### Common Issues

#### 1. Import Errors

**Problem**: `ModuleNotFoundError: No module named 'module_name'`

**Solution**: 
- Make sure you're running tests from the project root
- Check that the module path is correct (`src.module_name`)
- Install missing dependencies: `pip install -r requirements.txt`

#### 2. Tests Fail Due to Missing Dependencies

**Problem**: Some tests require optional dependencies (like `img2pdf`)

**Solution**:
- Install the dependency: `pip install img2pdf`
- Or skip tests that require it: `pytest tests/ -k "not pdf_generator"`

#### 3. Mock Not Working

**Problem**: Mock doesn't seem to be called or returns wrong value

**Solution**:
- Check the patch path matches the import path exactly
- Use `@patch('src.module.ClassName.method')` not `@patch('ClassName.method')`
- Verify mock is called: `mock_function.assert_called_once()`

#### 4. Temporary Files Not Cleaned Up

**Problem**: Test files remain after tests run

**Solution**:
- Use pytest's `tmp_path` fixture (automatically cleaned up)
- Don't use `/tmp` or hardcoded paths
- Ensure tests complete (even on failure)

#### 5. Tests Pass Locally But Fail in CI

**Problem**: Tests work on your machine but fail in continuous integration

**Solution**:
- Check for hardcoded paths (use `tmp_path` instead)
- Verify all dependencies are in `requirements.txt`
- Check for time-dependent tests (use mocked time)
- Ensure tests don't depend on external services

### Getting Help

- **pytest documentation**: https://docs.pytest.org/
- **unittest.mock documentation**: https://docs.python.org/3/library/unittest.mock.html
- **Project README**: See `README.md` for project-specific information

## Best Practices

1. **Write descriptive test names**: `test_user_can_login_with_valid_credentials` not `test_login`

2. **One assertion per test** (when possible): Makes it clear what failed

3. **Use fixtures for common setup**: Don't repeat setup code

4. **Test edge cases**: Empty inputs, None values, very long strings, etc.

5. **Test error cases**: What happens when things go wrong?

6. **Keep tests independent**: Each test should work alone

7. **Use mocks for external dependencies**: Don't make real network calls

8. **Add comments for complex tests**: Explain why, not just what

9. **Run tests frequently**: Catch bugs early

10. **Keep tests fast**: Use mocks to avoid slow operations

## Continuous Integration

Tests should be run automatically in CI/CD pipelines. Example GitHub Actions workflow:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest tests/ -v
```

## Conclusion

This test suite provides comprehensive coverage of the application's functionality. All tests include detailed comments to help beginners understand Python testing concepts. When adding new features, remember to add corresponding tests!

For questions or improvements to the test suite, please refer to the project's contribution guidelines.

