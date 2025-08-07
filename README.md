# Germany VFR Aerodrome Charts for ForeFlight BYOP

A CLI tool to collect VFR aerodrome charts and airport information from the DFS AIP site and generate PDF files suitable for ForeFlight BYOP (Bring Your Own Plates) content packs.

## 🚀 TL;DR 

**What it does:** Scrapes German VFR aerodrome charts from DFS AIP and creates ForeFlight BYOP content packs.

**⚠️ Disclaimer:** This tool is for educational purposes only. Please ensure it is permitted in your jurisdiction to run such a script.

**Technology:** Python with Conda (Anaconda) environment management.

**Quick start:**
```bash
# Install and setup
conda env create -f environment.yml
conda activate devfrff

# Run full dataset
python run.py
```

**Output:** Creates `AIP Germany/` folder with:
- `byop/` subfolder containing PDF charts
- `manifest.json` for ForeFlight compatibility
- Charts named like: `EDKA_Visual_Aachen-Merzbrueck 1.PDF`, `EDKA_Info_AD 2-3.PDF`


Now create a zip file of the folder AIP Germany. You can then import content packs (the zip file) into ForeFlight via AirDrop, email, iTunes, online hyperlinks, and ForeFlight’s Cloud Documents feature (requires a Pro plan or above). For more info on content packs, see: [ForeFlight Content Packs Guide](https://foreflight.com/support/content-packs/)

**Features:**
- ✅ Human-like browsing behavior (randomized pauses)
- ✅ Automatic chart categorization (Visual/Info)
- ✅ ForeFlight BYOP compatible format
- ✅ Progress tracking and error handling
- ✅ Rate limiting to avoid blocking

---

## Features

- 🔍 **Smart Web Scraping**: Automatically navigates DFS AIP with human-like behavior
- 📥 **High-Resolution Downloads**: Downloads full-size chart images from print URLs
- 📄 **PDF Generation**: Converts images to PDF with proper BYOP naming
- 🏷️ **Smart Categorization**: Automatically categorizes charts (Visual/Info)
- 📊 **Rich Progress Tracking**: Console interface with progress bars and summaries
- 🎯 **ForeFlight Compatible**: Generates complete BYOP content packs with manifest
- ⏱️ **Rate Limiting**: Randomized pauses to mimic human browsing
- 🛡️ **Error Handling**: Robust retry logic and graceful failure handling

## Installation

### Prerequisites

- Python 3.10 or later
- Anaconda (recommended)

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd devfrff
   ```

2. **Create and activate conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate devfrff
   ```

3. **Verify installation:**
   ```bash
   python run.py info
   ```

## Usage

### Quick Start

Run the realistic processing pipeline (recommended):

```bash
# Test with a few airports
python run.py --limit 5

# Process all airports
python run.py
```

### Command Options

```bash
python run.py [COMMAND] [OPTIONS]

Commands:
  scrape              Extract chart information only
  download            Download charts and generate PDFs
  full-pipeline       Complete workflow (scrape + download + PDFs)
  process-realistic   Realistic processing with human-like behavior
  info                Display project information

Options:
  --limit INT         Limit number of aerodromes to process
  --output-dir TEXT   Output directory (default: "AIP Germany")
  --airport-pause     Pause between airports (default: 3-8s random)
  --section-pause     Pause between sections (default: 12-18s random)
```

### Examples

```bash
# Test with 3 airports
python run.py --limit 3

# Custom output directory
python run.py --output-dir "My Charts"

# Custom pause settings
python run.py --airport-pause 5 --section-pause 15
```

## BYOP File Format

The tool generates PDF files with the following naming convention:

### Visual Charts
```
{ICAO}_Visual_{ChartName}.PDF
```

Examples:
- `EDKA_Visual_Aachen-Merzbrueck 1.PDF`
- `EDPA_Visual_Aalen-Heidenheim Elchingen 1.PDF`

### Info Charts (AD Charts)
```
{ICAO}_Info_{ChartName}.PDF
```

Examples:
- `EDKA_Info_AD 2-3.PDF`
- `EDPA_Info_AD 2-3.PDF`

### Chart Categorization

The tool currently only recognizes two categories:
- **Visual Charts**: All regular aerodrome charts (approach, taxi, parking, etc.)
- **Info Charts**: AD charts (typically containing additional information pages)

## Output Structure

```
AIP Germany/
├── manifest.json              # ForeFlight BYOP manifest
└── byop/                      # PDF charts
    ├── EDKA_Visual_Aachen-Merzbrueck 1.PDF
    ├── EDKA_Visual_Aachen-Merzbrueck 2.PDF
    ├── EDKA_Info_AD 2-3.PDF
    └── ...
```

### Manifest Format

```json
{
  "name": "AIP Germany 2025JUL25",
  "abbreviation": "AIP GER",
  "version": "2025JUL25",
  "organizationName": "from DFS"
}
```

## Project Structure

```
devfrff/
├── src/                    # Source code
│   ├── scraper.py         # Web scraping logic
│   ├── pdf_generator.py   # PDF generation
│   └── main.py           # CLI interface
├── scripts/               # Executable scripts
├── tests/                 # Test files
├── run.py                 # Main runner (moved to root)
├── environment.yml        # Conda environment
└── README.md             # This file
```

## Development

### Code Quality

The project follows Python best practices:

- **Type Hints**: All functions include type annotations
- **Code Formatting**: Uses `black` for consistent formatting
- **Import Sorting**: Uses `isort` for organized imports
- **Linting**: Uses `flake8` for code quality checks

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/ tests/
isort src/ tests/
```

## Data Sources

The tool scrapes data from the [DFS AIP (Aeronautical Information Publication)](https://aip.dfs.de) website:

- **Main Page**: `https://aip.dfs.de/basicaip/`
- **VFR Section**: Dynamically navigated via "AIP VFR Online" link
- **Aerodromes**: Dynamically found via "AD Flugplätze" link
- **Chart Pages**: Individual aerodrome pages with chart links
- **Print URLs**: High-resolution chart images for PDF generation

### Navigation Flow

1. Start at main AIP page
2. Find and follow "AIP VFR Online" link
3. Find and follow "AD Flugplätze" link
4. Navigate through alphabetical sections (A, B, C, etc.)
5. Process each aerodrome's charts
6. Download images and generate PDFs

## Technical Details

### Human-Like Behavior

The scraper mimics real user behavior:
- **Randomized pauses**: 3-8 seconds between airports, 12-18 seconds between sections
- **Proper headers**: User-Agent, Referer, Accept headers
- **Session management**: Maintains cookies and session state
- **Rate limiting**: Exponential backoff with jitter

### Error Handling

- **Retry logic**: Automatic retries for failed requests
- **Graceful degradation**: Continues processing even if some charts fail
- **Progress tracking**: Real-time feedback on processing status
- **Cache management**: Caches section pages to reduce requests

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is for educational and personal use only. Please ensure it is permitted in your jurisdiction to run such a script. Please respect the DFS AIP website's terms of service and rate limiting. The generated content is intended for use with ForeFlight's BYOP feature in accordance with their terms of service.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request
