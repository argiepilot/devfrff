# deVFRff
## VFR Charts from Germany and the USA for ForeFlight BYOP

A CLI tool to collect VFR charts from multiple sources and generate content packs suitable for ForeFlight BYOP (Bring Your Own Plates). Supports DFS (Germany) Visual Operations and Aerodrome charts and FAA (USA) Sectional and Terminal Area charts.

## TL;DR 

**What it does:** Scrapes VFR charts from DFS AIP (Germany) and FAA (USA) sources, generating ForeFlight BYOP content packs in PDF (DFS) and MBTiles (FAA) formats. The DFS charts include the Visual Operation Charts ("Sichtflugkarten") and Aerodrome Charts ("Flugplatzkarten") for Germany. The FAA charts include the Sectional Charts and Terminal Charts which are both georeferenced and will be overlaid onto the moving map. 

> [!IMPORTANT]
> This tool is provided for educational purposes only. It is your responsibility to ensure that use of this script is permitted in your jurisdiction and complies with all applicable laws and regulations. Always review and respect the terms of service of the data sources (DFS AIP, FAA) and ForeFlight BYOP before using this tool. The authors and contributors are not affiliated with or endorsed by DFS, FAA, or ForeFlight, and assume no liability for any misuse or consequences arising from the use of this software.

**Technology:** Python with Conda (Anaconda) environment management.

**Quick start:**
```bash
# Install and setup
conda env create -f environment.yml
conda activate devfrff

# Run the script (defaults to process-all, interactive selection).
python run.py 
```

**Output:** Creates `VFR Charts Package/` folder in the ForeFlight "Bring your own Chart" format with:
- **DFS Charts**: `byop/` subfolder containing PDF charts (e.g., `EDKA_Visual_Aachen-Merzbrueck 1.PDF`)
- **FAA Charts**: `layers/` subfolder containing georeferenced MBTiles files (e.g., sectional charts like `S_Detroit.mbtiles`, or terminal charts like `T_Chicago.mbtiles`)
- `manifest.json` for ForeFlight compatibility


This will take some time. Then just create a zip file of the `VFR Charts Package/` folder. You can then import content packs (the zip file) into ForeFlight via AirDrop, email, iTunes, online hyperlinks, and ForeFlight's Cloud Documents feature (the last one requires a Pro plan or above). For more info on content packs, see: [ForeFlight Content Packs Guide](https://foreflight.com/support/content-packs/)

**Features:**
- **DFS (Germany) Charts**: PDF format for Visual Ops and aerodrome charts
  - Human-like browsing behavior (randomized pauses to not overload the server)
  - Downloads full-size chart images from print URLs
  - Converts images to PDFs with proper BYOP naming
  - Automatic chart categorization (Visual/Info)
- **FAA (USA) Charts**: MBTiles format for Sectional and Terminal Area charts
  - Scrapes FAA VFR Raster Charts page
  - Downloads GeoTIFF files and converts to tiled MBTiles (no MapTiler required)
  - Handles paletted TIFFs with VRT expansion
  - Multi-zoom tile generation (zoom 6-12, 512x512 tiles)
  - JPEG compression where possible for optimal file sizes
- ForeFlight BYOP compatible format
- Progress tracking and error handling
- Rate limiting to avoid blocking

---

## Installation

### Prerequisites

- Python 3.11 or later
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

Process selected chart sources (interactive mode):

```bash
# Process all selected sources (interactive selection)
python run.py process-all

# Process with custom output directory
python run.py process-all --output-dir "My Charts"


```

### Command Options

```bash
python run.py [COMMAND] [OPTIONS]

Commands:
  scrape              Extract DFS chart information only
  download            Download DFS charts and generate PDFs
  full-pipeline       Complete DFS workflow (scrape + download + PDFs)
  process-realistic   Process DFS charts with human-like behavior
  process-all         Process selected sources (DFS/FAA) into unified package
  info                Display project information

Options for process-all:
  --output-dir TEXT       Output directory (default: "VFR Charts Package")
  --limit-dfs INT         Limit number of DFS aerodromes to process
  --limit-faa INT         Limit number of FAA charts per type to process
  --airport-pause FLOAT   Pause between DFS airports in seconds (default: 5.0)
  --section-pause FLOAT   Pause between DFS letter sections in seconds (default: 15.0)
  --verbose, -v           Verbose output with detailed progress information

Options for process-realistic:
  --limit INT         Limit number of aerodromes to process
  --output-dir TEXT   Output directory (default: "AIP Germany")
  --airport-pause     Pause between airports (default: 3-8s random)
  --section-pause     Pause between sections (default: 12-18s random)
```

### Examples

```bash
# Process all sources interactively
python run.py process-all

# Process DFS charts only (test with 3 airports)
python run.py process-realistic --limit 3

# Custom output directory
python run.py process-all --output-dir "My Charts"

# Limit FAA charts
python run.py process-all --limit-faa 2

# Verbose output for debugging
python run.py process-all --verbose
```

## Chart Formats

### DFS (Germany) Charts - PDF Format

The tool generates PDF files with the following naming convention:

#### Visual Charts
```
{ICAO}_Visual_{ChartName}.PDF
```

Examples:
- `EDKA_Visual_Aachen-Merzbrueck 1.PDF`
- `EDPA_Visual_Aalen-Heidenheim Elchingen 1.PDF`

#### Info Charts (AD Charts)
```
{ICAO}_Info_{ChartName}.PDF
```

Examples:
- `EDKA_Info_AD 2-3.PDF`
- `EDPA_Info_AD 2-3.PDF`

#### Chart Categorization

The tool recognizes two categories for DFS charts:
- **Visual Charts**: All regular aerodrome charts (approach, taxi, parking, etc.)
- **Info Charts**: AD charts (typically containing additional information pages)

### FAA (USA) Charts - MBTiles Format

FAA charts are converted to MBTiles format for use as map overlays in ForeFlight:

#### Sectional Charts
- Format: MBTiles (JPEG-compressed tiles)
- Naming: `S_{ChartName}.mbtiles`
- Example: `S_Detroit.mbtiles`
- Zoom levels: 6-12 (configurable)
- Tile size: 512x512 pixels
- Compression: JPEG quality 75

#### Terminal Area Charts
- Format: MBTiles (JPEG-compressed tiles)
- Naming: `T_{ChartName}.mbtiles`
- Example: `T_Chicago.mbtiles`
- Zoom levels: 6-12 (configurable)
- Tile size: 512x512 pixels
- Compression: JPEG quality 75

For more details, see [FAA Workflow Documentation](docs/FAA_workflow.md).

## Output Structure

### Unified Package (process-all)

```
VFR Charts Package/
├── manifest.json              # ForeFlight BYOP manifest
├── byop/                      # DFS PDF charts (if DFS selected)
│   ├── EDKA_Visual_Aachen-Merzbrueck 1.PDF
│   ├── EDKA_Visual_Aachen-Merzbrueck 2.PDF
│   ├── EDKA_Info_AD 2-3.PDF
│   └── ...
└── layers/                    # FAA MBTiles charts (if FAA selected)
    ├── S_Detroit.mbtiles
    ├── S_Chicago.mbtiles
    ├── T_Chicago.mbtiles
    └── ...
```

### DFS-Only Output (process-realistic)

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

The manifest is automatically generated based on the sources included:

```json
{
  "name": "VFR Charts Package 2025JUL25",
  "abbreviation": "VFR",
  "version": "2025JUL25",
  "organizationName": "from DFS/FAA"
}
```

## Data Sources

### DFS (Germany) - Aerodrome Charts

The tool scrapes data from the [DFS AIP (Aeronautical Information Publication)](https://aip.dfs.de) website:

- **Main Page**: `https://aip.dfs.de/basicaip/`
- **VFR Section**: Dynamically navigated via "AIP VFR Online" link
- **Aerodromes**: Dynamically found via "AD Flugplätze" link
- **Chart Pages**: Individual aerodrome pages with chart links
- **Print URLs**: High-resolution chart images for PDF generation

### FAA (USA) - Sectional and Terminal Area Charts

The tool scrapes data from the [FAA VFR Raster Charts](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/) page:

- **Main Page**: `https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/`
- **Sectional Charts**: GeoTIFF downloads from sectional chart tables
- **Terminal Area Charts**: GeoTIFF downloads from terminal area chart tables
- **Format**: GeoTIFF files (often paletted/indexed color) packaged in ZIP files

## License

This project is licensed under the GPL v3.0 License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is provided for educational purposes only. It is your responsibility to ensure that use of this script is permitted in your jurisdiction and complies with all applicable laws and regulations. Always review and respect the terms of service of the data sources (DFS AIP, FAA) and ForeFlight BYOP before using this tool. The authors and contributors are not affiliated with or endorsed by DFS, FAA, or ForeFlight, and assume no liability for any misuse or consequences arising from the use of this software.

---

## For Developers

This section contains information for developers who want to contribute to the project or understand its technical implementation.

Some things that still need a little bit of tweaking and improvement:
- Smaller file size of the .mbtiles files
- Speed up the conversion of .mbtiles
- Find a smart way to exclude the legend, etc. from the FAA charts
- Automated testing

### Testing Options

The tool provides several test modes for faster development and testing. They serve to test the full process with just one chart, and optionally with fewer zoom levels (for faster processing).

#### Test Mode Options for process-all

```bash
# Test Terminal Area charts (process only first chart)
python run.py process-all --test-terminal

# Test Terminal Area charts (quick mode with reduced zoom levels 6-9)
python run.py process-all --test-terminal-quick

# Test Sectional charts (process only first chart)
python run.py process-all --test-sectional

# Test Sectional charts (quick mode with reduced zoom levels 6-9)
python run.py process-all --test-sectional-quick

# Combine with other options
python run.py process-all --test-terminal-quick --limit-dfs 0
python run.py process-all --test-sectional-quick --limit-dfs 0
```

**Note:** Test modes automatically select the appropriate chart type and skip interactive source selection.

### Project Structure

```
devfrff/
├── src/                      # Source code
│   ├── scraper.py            # DFS web scraping logic
│   ├── faa_scraper.py        # FAA web scraping logic
│   ├── pdf_generator.py      # PDF generation for DFS charts
│   ├── mbtiles_converter.py  # MBTiles conversion for FAA charts
│   ├── byop_packager.py      # BYOP package generation
│   └── main.py               # CLI interface
├── scripts/                  # Executable scripts
├── tests/                    # Test files
├── docs/                     # Documentation
│   └── FAA_workflow.md       # FAA charts workflow details
├── run.py                    # Main runner
├── environment.yml           # Conda environment
└── README.md                 # This file
```

### Development

#### Code Quality

The project follows Python best practices:

- **Type Hints**: All functions include type annotations
- **Code Formatting**: Uses `black` for consistent formatting
- **Import Sorting**: Uses `isort` for organized imports
- **Linting**: Uses `flake8` for code quality checks

#### Running Tests

```bash
pytest tests/
```

#### Code Formatting

```bash
black src/ tests/
isort src/ tests/
```

### Technical Details

#### DFS Scraping - Human-Like Behavior

The DFS scraper mimics real user behavior:
- **Randomized pauses**: 3-8 seconds between airports, 12-18 seconds between sections
- **Proper headers**: User-Agent, Referer, Accept headers
- **Session management**: Maintains cookies and session state
- **Rate limiting**: Exponential backoff with jitter

#### Navigation Flow

1. Start at main AIP page
2. Find and follow "AIP VFR Online" link
3. Find and follow "AD Flugplätze" link
4. Navigate through alphabetical sections (A, B, C, etc.)
5. Process each aerodrome's charts
6. Download images and generate PDFs

#### FAA Processing - GeoTIFF to MBTiles

The FAA processing pipeline:
- **VRT Expansion**: Uses GDAL VRT (Virtual Dataset) to expand paletted TIFFs to RGBA without creating large intermediate files
- **Multi-zoom Tiling**: Generates tiles at zoom levels 6-12 using 512x512 pixel tiles
- **Tile Compression**: Recompresses tiles to JPEG (quality 75) during MBTiles assembly
- **Coordinate Systems**: Handles XYZ to TMS tile coordinate conversion for MBTiles format

#### Processing Flow

1. Scrape FAA VFR Raster Charts page HTML
2. Extract GeoTIFF download links from chart tables
3. Download ZIP files containing GeoTIFFs
4. Extract GeoTIFF files (TAC files only for terminal charts, FLY files are skipped)
5. Convert paletted TIFFs to RGBA using VRT (Virtual Dataset)
6. Generate multi-zoom tiles using `gdal2tiles.py` or rio-tiler
7. Package tiles into MBTiles format with JPEG compression

#### Error Handling

- **Retry logic**: Automatic retries for failed requests
- **Graceful degradation**: Continues processing even if some charts fail
- **Progress tracking**: Real-time feedback on processing status
- **Cache management**: Caches section pages to reduce requests (DFS)
- **Temporary file cleanup**: Automatically cleans up downloaded ZIPs and extracted GeoTIFFs (FAA)

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request
