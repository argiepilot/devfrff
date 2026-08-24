# deVFRff
## VFR Charts from Germany and the USA for ForeFlight BYOP

[![Tests](https://github.com/argiepilot/devfrff/actions/workflows/tests.yml/badge.svg)](https://github.com/argiepilot/devfrff/actions/workflows/tests.yml)

A CLI tool that collects VFR charts and builds ForeFlight BYOP (Bring Your Own Plates) content packs. It supports DFS (Germany) Visual Operations and Aerodrome charts ("Sichtflugkarten" / "Flugplatzkarten") as PDFs, and FAA (USA) Sectional and Terminal Area charts as georeferenced MBTiles overlays.

> [!IMPORTANT]
> This tool is provided for educational purposes only. It is your responsibility to ensure that use of this script is permitted in your jurisdiction and complies with all applicable laws and regulations. Always review and respect the terms of service of the data sources (DFS AIP, FAA) and ForeFlight BYOP before using this tool. The authors and contributors are not affiliated with or endorsed by DFS, FAA, or ForeFlight, and assume no liability for any misuse or consequences arising from the use of this software.

## Quick start

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python 3.11).

```bash
git clone <repository-url>
cd devfrff
uv sync
uv run python run.py info          # sanity check
uv run python run.py               # process-all, interactive source selection
```

That writes `VFR Charts Package/`. Zip the folder, then import it into ForeFlight (AirDrop, email, iTunes, a link, or Cloud Documents on Pro and above). See the [ForeFlight Content Packs Guide](https://foreflight.com/support/content-packs/). This takes a while.

After ForeFlight has the pack, reclaim disk space:

```bash
uv run python run.py clean         # folders and sibling .zip files
```

## Usage

```bash
uv run python run.py --help
uv run python run.py [COMMAND] --help
```

| Command | What it does |
| --- | --- |
| `process-all` | DFS + FAA into one package (default when you omit a command) |
| `process-realistic` | DFS only, with human-like pauses |
| `process-faa-sectional` | FAA sectional MBTiles only |
| `process-faa-terminal` | FAA terminal MBTiles only |
| `clean` | Remove generated packages and their `.zip` files |
| `info` | Tool overview |

`process-all` includes DFS, FAA sectional, and FAA terminal unless you pass `--no-dfs`, `--no-faa-sectional`, or `--no-faa-terminal`.

```bash
uv run python run.py process-all --output-dir "My Charts"
uv run python run.py process-all --limit-faa 2 --verbose
uv run python run.py process-realistic --limit 3
uv run python run.py process-faa-terminal --quick --limit 1
uv run python run.py clean --yes
uv run python run.py clean --dry-run
```

## Output

```
VFR Charts Package/
├── manifest.json
├── byop/                 # DFS PDFs (if selected)
│   ├── EDKA_Visual_Aachen-Merzbrueck 1.PDF
│   └── EDKA_Info_AD 2-3.PDF
└── layers/               # FAA MBTiles (if selected)
    ├── S_Detroit.mbtiles
    └── T_Chicago.mbtiles
```

DFS-only runs (`process-realistic`, `full-pipeline`, `download`) write the same layout to `AIP Germany/`.

DFS PDFs are named `{ICAO}_Visual_{ChartName}.PDF` or `{ICAO}_Info_{ChartName}.PDF` (AD pages). FAA files are `S_{ChartName}.mbtiles` (sectional) and `T_{ChartName}.mbtiles` (terminal).

## Data sources

- DFS AIP: [https://aip.dfs.de](https://aip.dfs.de)
- FAA VFR Raster Charts: [https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/)

## License

GPL v3.0 — see [LICENSE](LICENSE). Not affiliated with DFS, FAA, or ForeFlight.

## For developers

Open improvements:

- Smaller `.mbtiles` files
- Faster MBTiles conversion
- Exclude FAA chart legends and similar chrome

```bash
uv run pytest tests/
uv run black src/ tests/
uv run isort src/ tests/
```

More detail: [Testing](docs/TESTING.md), [FAA workflow](docs/FAA_workflow.md).

```
devfrff/
├── src/                 # scrapers, PDF/MBTiles conversion, CLI
├── tests/
├── docs/
├── run.py
├── pyproject.toml
└── uv.lock
```

1. Fork and create a feature branch
2. Add tests for new behavior
3. Run the test suite
4. Open a pull request
