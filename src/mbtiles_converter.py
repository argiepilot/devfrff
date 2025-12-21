"""Convert GeoTIFF files to mbtiles format."""

import concurrent.futures
import io
import json
import os
import time
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rasterio.warp import transform_bounds
from rio_tiler.io import COGReader
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
import mercantile
import morecantile
import tempfile
import warnings
try:
    from osgeo import gdal as _gdal_for_warnings
    _gdal_for_warnings.UseExceptions()
except Exception:
    pass

console = Console()

# #region agent log
LOG_PATH = Path("/Users/wolf/dev/devfrff/.cursor/debug.log")

def _log_debug(location: str, message: str, data: dict, hypothesis_id: str = "A"):
    """Write debug log entry."""
    try:
        log_entry = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(os.path.getmtime(__file__) * 1000) if os.path.exists(__file__) else 0
        }
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass
# #endregion

# #region agent log
def _log_runtime_event(
    location: str,
    message: str,
    data: dict,
    hypothesis_id: str,
    run_id: str = "run_mbtiles_black1",
):
    """Append a runtime log entry for debug-mode analysis."""
    try:
        log_entry = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass
# #endregion


# Worker globals for parallel tile processing
_worker_cog_reader: Optional[COGReader] = None
_worker_tms = None
_worker_logged = False


def _worker_init(cog_path: str, tms_id: str) -> None:
    """Initializer for worker processes to open COGReader once per process."""
    global _worker_cog_reader, _worker_tms
    _worker_tms = morecantile.tms.get(tms_id)
    _worker_cog_reader = COGReader(cog_path, tms=_worker_tms)


def _worker_process_tile(args: Tuple[int, int, int, int]) -> Tuple[str, int, int, int, Optional[bytes], bool, Optional[str]]:
    """Process a single tile in a worker process.

    Returns:
        ("ok", z, x, y, tile_bytes, has_alpha, None) on success
        ("dropped", z, x, y, None, False, None) if transparent
        ("error", z, x, y, None, False, error_message) on error
    """
    global _worker_cog_reader
    if _worker_cog_reader is None:
        return ("error", -1, -1, -1, None, False, "COGReader not initialized")

    x, y, z, alpha_threshold = args
    try:
        data, mask = _worker_cog_reader.tile(x, y, z, tilesize=256)
    except Exception as e:  # pragma: no cover - defensive
        return ("error", z, x, y, None, False, str(e))

    global _worker_logged
    if not _worker_logged:
        try:
            log_entry = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "A",
                "location": "mbtiles_converter.py:_worker_process_tile",
                "message": "worker_first_tile_sample",
                "data": {
                    "z": z,
                    "x": x,
                    "y": y,
                    "data_shape": list(data.shape),
                    "data_dtype": str(data.dtype),
                    "data_min": float(np.min(data)) if data.size else None,
                    "data_max": float(np.max(data)) if data.size else None,
                    "mask_shape": list(mask.shape),
                    "mask_min": int(mask.min()) if mask.size else None,
                    "mask_max": int(mask.max()) if mask.size else None,
                },
                "timestamp": int(time.time() * 1000),
            }
            with open("/Users/wolf/dev/devfrff/.cursor/debug.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
        _worker_logged = True

    if mask.max() <= alpha_threshold:
        return ("dropped", z, x, y, None, False, None)

    has_alpha = mask.min() < 255
    arr = np.moveaxis(data, 0, -1)

    tile_data_bytes: Optional[bytes] = None
    if has_alpha:
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        rgba = np.dstack([arr, mask])
        img = Image.fromarray(rgba.astype(np.uint8), mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        tile_data_bytes = buf.getvalue()
    else:
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        rgb = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=75, optimize=True, subsampling=2)
        tile_data_bytes = buf.getvalue()

    return ("ok", z, x, y, tile_data_bytes, has_alpha, None)


class MBTilesConverter:
    """Convert GeoTIFF files to mbtiles format."""

    def __init__(self, min_zoom: int = 6, max_zoom: int = 13):
        """Initialize the mbtiles converter.

        Args:
            min_zoom: Minimum zoom level for tiles (default: 6, shows when zoomed out)
            max_zoom: Maximum zoom level for tiles (default: 13, reasonable detail)
        """
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom

    def _check_gdal_available(self) -> bool:
        """Check if GDAL is available on the system.

        Returns:
            True if GDAL is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["gdalinfo", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_gdal2mbtiles_available(self) -> bool:
        """Check if gdal2mbtiles script is available.

        Returns:
            True if gdal2mbtiles is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["gdal2mbtiles", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_gdal2tiles_available(self) -> bool:
        """Check if gdal2tiles.py script is available.

        Returns:
            True if gdal2tiles.py is available, False otherwise
        """
        try:
            # Try common locations
            import shutil
            gdal2tiles = shutil.which("gdal2tiles.py") or shutil.which("gdal2tiles")
            if gdal2tiles:
                result = subprocess.run(
                    [gdal2tiles, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return result.returncode == 0
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def convert_with_gdal2mbtiles(
        self, geotiff_path: Path, output_path: Path
    ) -> bool:
        """Convert GeoTIFF to mbtiles using gdal2mbtiles script.

        Args:
            geotiff_path: Path to input GeoTIFF file
            output_path: Path to output mbtiles file

        Returns:
            True if successful, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:convert_with_gdal2mbtiles:entry",
            "Starting gdal2mbtiles conversion",
            {
                "geotiff_path": str(geotiff_path),
                "output_path": str(output_path),
                "min_zoom": self.min_zoom,
                "max_zoom": self.max_zoom
            },
            "G"
        )
        # #endregion

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                "gdal2mbtiles",
                "-z",
                f"{self.min_zoom}-{self.max_zoom}",
                str(geotiff_path),
                str(output_path),
            ]

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_gdal2mbtiles:cmd",
                "Running gdal2mbtiles command",
                {"cmd": " ".join(cmd)},
                "G"
            )
            # #endregion

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600
            )

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_gdal2mbtiles:result",
                "gdal2mbtiles command completed",
                {
                    "returncode": result.returncode,
                    "stdout_length": len(result.stdout),
                    "stderr_length": len(result.stderr),
                    "output_exists": output_path.exists(),
                    "output_size": output_path.stat().st_size if output_path.exists() else 0
                },
                "G"
            )
            # #endregion

            if result.returncode == 0:
                return True
            else:
                console.print(
                    f"[red]gdal2mbtiles failed: {result.stderr}[/red]"
                )
                return False

        except subprocess.TimeoutExpired:
            console.print("[red]Conversion timed out[/red]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_gdal2mbtiles:error",
                "Conversion timed out",
                {},
                "G"
            )
            # #endregion
            return False
        except Exception as e:
            console.print(f"[red]Error converting with gdal2mbtiles: {e}[/red]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_gdal2mbtiles:error",
                "Exception during conversion",
                {"error": str(e), "error_type": type(e).__name__},
                "G"
            )
            # #endregion
            return False

    def _check_and_convert_paletted_geotiff(
        self, geotiff_path: Path, temp_dir: Path
    ) -> Optional[Path]:
        """Check if GeoTIFF is paletted and convert to RGBA if needed.

        Args:
            geotiff_path: Path to input GeoTIFF file
            temp_dir: Temporary directory for converted file

        Returns:
            Path to RGBA GeoTIFF if conversion needed, original path otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:_check_and_convert_paletted_geotiff:entry",
            "Checking if GeoTIFF is paletted",
            {"geotiff_path": str(geotiff_path)},
            "K"
        )
        # #endregion

        try:
            from osgeo import gdal

            src_ds = gdal.Open(str(geotiff_path))
            if src_ds is None:
                return None

            # Check if it's paletted (indexed color)
            band = src_ds.GetRasterBand(1)
            color_table = band.GetColorTable()

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_check_and_convert_paletted_geotiff:check",
                "Checked color table",
                {"has_color_table": color_table is not None},
                "K"
            )
            # #endregion

            src_ds = None
            band = None

            if color_table is not None:
                # Use VRT format instead of full RGBA conversion (much faster!)
                # VRT is a virtual format that expands on-the-fly without creating a huge file
                console.print("[cyan]Creating VRT for paletted GeoTIFF (expanding to RGBA on-the-fly)...[/cyan]")
                vrt_path = temp_dir / f"{geotiff_path.stem}_rgba.vrt"

                cmd = [
                    "gdal_translate",
                    "-of",
                    "VRT",
                    "-expand",
                    "rgba",
                    "-a_nodata",
                    "0",
                    str(geotiff_path),
                    str(vrt_path),
                ]

                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:_check_and_convert_paletted_geotiff:convert",
                    "Converting paletted to VRT (RGBA)",
                    {"cmd": " ".join(cmd), "vrt_path": str(vrt_path)},
                    "K"
                )
                # #endregion

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60
                )

                if result.returncode == 0 and vrt_path.exists():
                    # #region agent log
                    _log_debug(
                        "mbtiles_converter.py:_check_and_convert_paletted_geotiff:success",
                        "Successfully created VRT",
                        {"vrt_path": str(vrt_path), "vrt_size": vrt_path.stat().st_size},
                        "K"
                    )
                    # #endregion
                    return vrt_path
                else:
                    console.print(
                        f"[yellow]Warning: Failed to create VRT: {result.stderr}[/yellow]"
                    )
                    # #region agent log
                    _log_debug(
                        "mbtiles_converter.py:_check_and_convert_paletted_geotiff:error",
                        "Failed to create VRT",
                        {"stderr": result.stderr},
                        "K"
                    )
                    # #endregion
                    return None

            return geotiff_path  # Not paletted, use original

        except Exception as e:
            console.print(f"[yellow]Warning: Could not check GeoTIFF format: {e}[/yellow]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_check_and_convert_paletted_geotiff:error",
                "Exception checking GeoTIFF",
                {"error": str(e), "error_type": type(e).__name__},
                "K"
            )
            # #endregion
            return geotiff_path  # Assume not paletted, use original

    def _inspect_geotiff_quick(self, geotiff_path: Path) -> None:
        """Collect minimal GeoTIFF metadata for debugging palette/scaling issues."""
        try:
            from osgeo import gdal
        except Exception as e:  # pragma: no cover - defensive
            # #region agent log
            _log_runtime_event(
                "mbtiles_converter.py:_inspect_geotiff_quick:error",
                "GDAL not available for inspection",
                {"error": str(e), "geotiff_path": str(geotiff_path)},
                hypothesis_id="PAL",
            )
            # #endregion
            return

        try:
            ds = gdal.Open(str(geotiff_path))
            if ds is None:
                # #region agent log
                _log_runtime_event(
                    "mbtiles_converter.py:_inspect_geotiff_quick:error",
                    "GDAL could not open GeoTIFF",
                    {"geotiff_path": str(geotiff_path)},
                    hypothesis_id="PAL",
                )
                # #endregion
                return

            band_count = ds.RasterCount
            band_summaries = []
            for b in range(1, min(band_count, 4) + 1):
                band = ds.GetRasterBand(b)
                color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
                color_table = band.GetColorTable()
                stats = band.GetStatistics(True, True)
                band_summaries.append(
                    {
                        "band": b,
                        "color_interp": color_interp,
                        "has_color_table": color_table is not None,
                        "dtype": gdal.GetDataTypeName(band.DataType),
                        "stats": stats if stats else None,
                    }
                )
            # #region agent log
            _log_runtime_event(
                "mbtiles_converter.py:_inspect_geotiff_quick:info",
                "GeoTIFF quick inspection",
                {
                    "geotiff_path": str(geotiff_path),
                    "bands": band_count,
                    "geotransform": list(ds.GetGeoTransform()) if ds.GetGeoTransform() else None,
                    "projection_snippet": ds.GetProjection()[:80] if ds.GetProjection() else None,
                    "band_summaries": band_summaries,
                },
                hypothesis_id="PAL",
            )
            # #endregion
        except Exception as e:  # pragma: no cover - defensive
            # #region agent log
            _log_runtime_event(
                "mbtiles_converter.py:_inspect_geotiff_quick:exception",
                "Exception during GeoTIFF inspection",
                {"error": str(e), "geotiff_path": str(geotiff_path)},
                hypothesis_id="PAL",
            )
            # #endregion

    def convert_with_gdal2tiles(
        self, geotiff_path: Path, output_path: Path
    ) -> bool:
        """Convert GeoTIFF to mbtiles using gdal2tiles.py (creates multi-zoom tiles).

        Args:
            geotiff_path: Path to input GeoTIFF file
            output_path: Path to output mbtiles file

        Returns:
            True if successful, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:convert_with_gdal2tiles:entry",
            "Starting gdal2tiles conversion",
            {
                "geotiff_path": str(geotiff_path),
                "output_path": str(output_path),
                "min_zoom": self.min_zoom,
                "max_zoom": self.max_zoom
            },
            "I"
        )
        # #endregion

        try:
            import shutil
            import tempfile

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Find gdal2tiles.py
            gdal2tiles = shutil.which("gdal2tiles.py") or shutil.which("gdal2tiles")
            if not gdal2tiles:
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_gdal2tiles:error",
                    "gdal2tiles.py not found",
                    {},
                    "I"
                )
                # #endregion
                return False

            # Create temporary directory for tiles and converted GeoTIFF
            with tempfile.TemporaryDirectory() as temp_base_dir:
                temp_base_path = Path(temp_base_dir)
                temp_tiles_path = temp_base_path / "tiles"
                temp_geotiff_dir = temp_base_path / "geotiff"
                temp_geotiff_dir.mkdir(exist_ok=True)

                # Check if GeoTIFF is paletted and convert if needed
                input_geotiff = self._check_and_convert_paletted_geotiff(
                    geotiff_path, temp_geotiff_dir
                )
                if input_geotiff is None:
                    # #region agent log
                    _log_debug(
                        "mbtiles_converter.py:convert_with_gdal2tiles:error",
                        "Failed to prepare GeoTIFF",
                        {},
                        "I"
                    )
                    # #endregion
                    return False

                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_gdal2tiles:prepared",
                    "GeoTIFF prepared for tiling",
                    {"input_geotiff": str(input_geotiff), "is_converted": input_geotiff != geotiff_path},
                    "I"
                )
                # #endregion

                # Run gdal2tiles.py to create tiles at multiple zoom levels
                effective_min_zoom = max(self.min_zoom, 6)
                effective_max_zoom = min(self.max_zoom, 13)
                
                console.print(
                    f"[cyan]Generating tiles at zoom levels {effective_min_zoom}-{effective_max_zoom}...[/cyan]"
                )
                
                cmd = [
                    gdal2tiles,
                    "-z",
                    f"{effective_min_zoom}-{effective_max_zoom}",
                    "--xyz",  # Use XYZ tile numbering (OSM Slippy Map)
                    "--srcnodata",
                    "0,0,0,0",
                    "-v",  # Verbose mode to show progress
                    str(input_geotiff),
                    str(temp_tiles_path),
                ]

                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_gdal2tiles:cmd",
                    "Running gdal2tiles command",
                    {
                        "cmd": " ".join(cmd),
                        "effective_min_zoom": effective_min_zoom,
                        "effective_max_zoom": effective_max_zoom
                    },
                    "I"
                )
                # #endregion

                # Run with timeout and capture output
                # Use longer timeout for large files (up to 2 hours for very large charts)
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=7200
                )
                
                # Show last few lines of output for debugging
                if result.stdout:
                    output_lines = result.stdout.strip().split('\n')
                    # Show last 5 lines
                    for line in output_lines[-5:]:
                        if line.strip():
                            console.print(f"[dim]{line}[/dim]")

                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_gdal2tiles:gdal2tiles_result",
                    "gdal2tiles command completed",
                    {
                        "returncode": result.returncode,
                        "stdout_length": len(result.stdout),
                        "stderr_length": len(result.stderr),
                        "stderr_preview": result.stderr[:200] if result.stderr else None,
                    },
                    "I"
                )
                # #endregion

                if result.returncode != 0:
                    console.print(
                        f"[red]gdal2tiles.py failed: {result.stderr}[/red]"
                    )
                    return False

                # Convert tile directory to mbtiles
                if self._tiles_dir_to_mbtiles(temp_tiles_path, output_path, geotiff_path):
                    # #region agent log
                    _log_debug(
                        "mbtiles_converter.py:convert_with_gdal2tiles:success",
                        "Successfully converted tiles to mbtiles",
                        {
                            "output_exists": output_path.exists(),
                            "output_size": output_path.stat().st_size if output_path.exists() else 0
                        },
                        "I"
                    )
                    # #endregion
                    return True
                else:
                    return False

        except Exception as e:
            console.print(f"[red]Error converting with gdal2tiles: {e}[/red]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_gdal2tiles:error",
                "Exception during conversion",
                {"error": str(e), "error_type": type(e).__name__},
                "I"
            )
            # #endregion
            return False

    def _tiles_dir_to_mbtiles(
        self, tiles_dir: Path, output_path: Path, geotiff_path: Path, compress_jpeg: bool = True, jpeg_quality: int = 75
    ) -> bool:
        """Convert a directory of tiles (from gdal2tiles.py) to mbtiles format.

        Args:
            tiles_dir: Directory containing tiles (z/x/y structure)
            output_path: Path to output mbtiles file
            geotiff_path: Original GeoTIFF path (for metadata)
            compress_jpeg: If True, convert tiles to JPEG to reduce size
            jpeg_quality: JPEG quality (default 75)

        Returns:
            True if successful, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:_tiles_dir_to_mbtiles:entry",
            "Converting tile directory to mbtiles",
            {
                "tiles_dir": str(tiles_dir),
                "output_path": str(output_path),
                "tiles_dir_exists": tiles_dir.exists()
            },
            "J"
        )
        # #endregion

        try:
            from osgeo import gdal, osr

            # Get bounds and projection from GeoTIFF
            src_ds = gdal.Open(str(geotiff_path))
            if src_ds is None:
                return False

            geotransform = src_ds.GetGeoTransform()
            projection = src_ds.GetProjection()
            width = src_ds.RasterXSize
            height = src_ds.RasterYSize

            # Calculate bounds
            min_x = geotransform[0]
            max_y = geotransform[3]
            max_x = min_x + width * geotransform[1]
            min_y = max_y + height * geotransform[5]

            # Create mbtiles database
            if output_path.exists():
                output_path.unlink()

            conn = sqlite3.connect(str(output_path))
            cursor = conn.cursor()

            # Create tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tiles (
                    zoom_level INTEGER,
                    tile_column INTEGER,
                    tile_row INTEGER,
                    tile_data BLOB
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    name TEXT,
                    value TEXT
                )
            """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS tile_index 
                ON tiles (zoom_level, tile_column, tile_row)
            """
            )

            # Insert metadata
            chart_name = output_path.stem.replace("terminal_", "").replace("sectional_", "")
            metadata = [
                ("name", chart_name),
                ("type", "overlay"),
                ("version", "1.1"),
                ("description", chart_name),
                ("format", "jpeg" if compress_jpeg else "png"),
                ("bounds", f"{min_x},{min_y},{max_x},{max_y}"),
                ("minzoom", str(self.min_zoom)),
                ("maxzoom", str(self.max_zoom)),
            ]

            cursor.executemany("INSERT INTO metadata (name, value) VALUES (?, ?)", metadata)

            # Walk tile directory and insert tiles
            tile_count = 0
            alpha_logged = False
            alpha_by_zoom = {}
            tile_count_by_zoom = {}
            size_sum_by_zoom = {}
            size_count_by_zoom = {}
            sample_dims_by_zoom = {}
            dropped_transparent_by_zoom = {}
            for z_dir in tiles_dir.iterdir():
                if not z_dir.is_dir() or not z_dir.name.isdigit():
                    continue

                zoom_level = int(z_dir.name)
                if zoom_level < self.min_zoom or zoom_level > self.max_zoom:
                    continue

                for x_dir in z_dir.iterdir():
                    if not x_dir.is_dir() or not x_dir.name.isdigit():
                        continue

                    tile_column = int(x_dir.name)

                    for tile_file in list(x_dir.glob("*.png")) + list(x_dir.glob("*.jpg")) + list(x_dir.glob("*.jpeg")):
                        stem = tile_file.stem
                        if not stem.isdigit():
                            continue

                        tile_row = int(stem)

                        # Read tile data
                        with open(tile_file, "rb") as f:
                            raw_data = f.read()

                        tile_data = raw_data
                        if compress_jpeg:
                            try:
                                from PIL import Image
                                import io

                                img = Image.open(io.BytesIO(raw_data))
                                has_alpha = "A" in img.getbands()
                                # Count tiles with/without alpha per zoom
                                tile_count_by_zoom[zoom_level] = tile_count_by_zoom.get(zoom_level, 0) + 1
                                if has_alpha:
                                    alpha_by_zoom[zoom_level] = alpha_by_zoom.get(zoom_level, 0) + 1

                                # Track size info per zoom
                                size_sum_by_zoom[zoom_level] = size_sum_by_zoom.get(zoom_level, 0) + len(raw_data)
                                size_count_by_zoom[zoom_level] = size_count_by_zoom.get(zoom_level, 0) + 1
                                if zoom_level not in sample_dims_by_zoom:
                                    sample_dims_by_zoom[zoom_level] = {"w": img.width, "h": img.height}

                                if has_alpha:
                                    # Detect fully transparent tiles and skip them
                                    if img.mode != "RGBA":
                                        img = img.convert("RGBA")
                                    extrema = img.getchannel("A").getextrema()
                                    fully_transparent = extrema == (0, 0)
                                    if fully_transparent:
                                        dropped_transparent_by_zoom[zoom_level] = (
                                            dropped_transparent_by_zoom.get(zoom_level, 0) + 1
                                        )
                                        continue  # skip inserting this tile

                                    if not alpha_logged:
                                        # #region agent log
                                        _log_debug(
                                            "mbtiles_converter.py:_tiles_dir_to_mbtiles:alpha_detected",
                                            "Source tiles contain alpha; keeping PNG to preserve transparency",
                                            {
                                                "zoom": zoom_level,
                                                "tile_column": tile_column,
                                                "tile_row": tile_row
                                            },
                                            "BG"  # hypothesis black gap
                                        )
                                        # #endregion
                                        alpha_logged = True
                                    # keep PNG to preserve transparency
                                    tile_data = raw_data
                                else:
                                    img = img.convert("RGB")
                                    buf = io.BytesIO()
                                    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
                                    tile_data = buf.getvalue()
                            except Exception:
                                tile_data = raw_data  # fallback to original

                        # Insert tile (using TMS Y coordinate - need to flip)
                        # gdal2tiles with --xyz uses OSM convention, mbtiles uses TMS
                        # TMS Y = (2^zoom - 1) - OSM Y
                        tms_tile_row = (2**zoom_level - 1) - tile_row

                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO tiles 
                            (zoom_level, tile_column, tile_row, tile_data)
                            VALUES (?, ?, ?, ?)
                        """,
                            (zoom_level, tile_column, tms_tile_row, tile_data),
                        )
                        tile_count += 1

            conn.commit()
            conn.close()

            src_ds = None

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_tiles_dir_to_mbtiles:success",
                "Successfully converted tiles to mbtiles",
                {
                    "tile_count": tile_count,
                    "output_size": output_path.stat().st_size,
                    "alpha_by_zoom": alpha_by_zoom,
                    "tile_count_by_zoom": tile_count_by_zoom,
                    "avg_size_by_zoom": {
                        z: size_sum_by_zoom[z] // size_count_by_zoom[z]
                        for z in size_sum_by_zoom
                    },
                    "sample_dims_by_zoom": sample_dims_by_zoom,
                    "dropped_transparent_by_zoom": dropped_transparent_by_zoom
                },
                "J"
            )
            # #endregion

            console.print(f"[cyan]Inserted {tile_count} tiles into mbtiles[/cyan]")
            return tile_count > 0

        except Exception as e:
            console.print(f"[red]Error converting tiles to mbtiles: {e}[/red]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_tiles_dir_to_mbtiles:error",
                "Exception during tile conversion",
                {"error": str(e), "error_type": type(e).__name__},
                "J"
            )
            # #endregion
            return False

    def convert_with_gdal_translate(
        self, geotiff_path: Path, output_path: Path
    ) -> bool:
        """Convert GeoTIFF to mbtiles using gdal_translate.

        Args:
            geotiff_path: Path to input GeoTIFF file
            output_path: Path to output mbtiles file

        Returns:
            True if successful, False otherwise
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # First, create a VRT for better control
            vrt_path = output_path.with_suffix(".vrt")
            vrt_cmd = ["gdal_translate", "-of", "VRT", str(geotiff_path), str(vrt_path)]

            result = subprocess.run(vrt_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                console.print(f"[red]Failed to create VRT: {result.stderr}[/red]")
                return False

            # Then use gdal2mbtiles or gdal_translate to mbtiles
            # Try gdal_translate directly to mbtiles format
            cmd = [
                "gdal_translate",
                "-of",
                "MBTiles",
                "-co",
                f"ZOOM_LEVEL={self.min_zoom}-{self.max_zoom}",
                str(geotiff_path),
                str(output_path),
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600
            )

            # Clean up VRT
            if vrt_path.exists():
                vrt_path.unlink()

            if result.returncode == 0:
                return True
            else:
                console.print(
                    f"[red]gdal_translate failed: {result.stderr}[/red]"
                )
                return False

        except subprocess.TimeoutExpired:
            console.print("[red]Conversion timed out[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Error converting with gdal_translate: {e}[/red]")
            return False

    def convert_with_python_gdal(
        self, geotiff_path: Path, output_path: Path
    ) -> bool:
        """Convert GeoTIFF to mbtiles using Python GDAL bindings.

        Args:
            geotiff_path: Path to input GeoTIFF file
            output_path: Path to output mbtiles file

        Returns:
            True if successful, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:convert_with_python_gdal:entry",
            "Starting Python GDAL conversion",
            {
                "geotiff_path": str(geotiff_path),
                "output_path": str(output_path),
                "min_zoom": self.min_zoom,
                "max_zoom": self.max_zoom
            },
            "E"
        )
        # #endregion

        try:
            from osgeo import gdal

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Open the GeoTIFF
            src_ds = gdal.Open(str(geotiff_path))
            if src_ds is None:
                console.print(f"[red]Failed to open GeoTIFF: {geotiff_path}[/red]")
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_python_gdal:error",
                    "Failed to open GeoTIFF",
                    {"geotiff_path": str(geotiff_path)},
                    "E"
                )
                # #endregion
                return False

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_python_gdal:geotiff_info",
                "GeoTIFF opened successfully",
                {
                    "width": src_ds.RasterXSize,
                    "height": src_ds.RasterYSize,
                    "bands": src_ds.RasterCount,
                    "projection": src_ds.GetProjection()[:100] if src_ds.GetProjection() else None
                },
                "E"
            )
            # #endregion

            # Create mbtiles driver
            driver = gdal.GetDriverByName("MBTiles")
            if driver is None:
                console.print("[red]MBTiles driver not available[/red]")
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_python_gdal:error",
                    "MBTiles driver not available",
                    {},
                    "E"
                )
                # #endregion
                return False

            # GDAL MBTiles driver does NOT support ZOOM_LEVEL option (as confirmed by warning)
            # We need to use a different approach - skip CreateCopy and use gdal2tiles instead
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_python_gdal:skip",
                "Skipping CreateCopy - MBTiles driver doesn't support ZOOM_LEVEL",
                {"min_zoom": self.min_zoom, "max_zoom": self.max_zoom},
                "E"
            )
            # #endregion
            
            # Return False to fall back to gdal2tiles method
            return False

            if dst_ds is None:
                console.print(f"[red]Failed to create mbtiles: {output_path}[/red]")
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_with_python_gdal:error",
                    "CreateCopy returned None",
                    {"output_path": str(output_path)},
                    "E"
                )
                # #endregion
                return False

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_python_gdal:after_create",
                "After CreateCopy",
                {
                    "output_path": str(output_path),
                    "output_exists": output_path.exists(),
                    "output_size": output_path.stat().st_size if output_path.exists() else 0
                },
                "E"
            )
            # #endregion

            # Clean up
            dst_ds = None
            src_ds = None

            return True

        except ImportError:
            console.print(
                "[yellow]Python GDAL bindings not available, trying alternative methods[/yellow]"
            )
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_python_gdal:error",
                "ImportError - GDAL bindings not available",
                {},
                "E"
            )
            # #endregion
            return False
        except Exception as e:
            console.print(f"[red]Error converting with Python GDAL: {e}[/red]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert_with_python_gdal:error",
                "Exception during conversion",
                {"error": str(e), "error_type": type(e).__name__},
                "E"
            )
            # #endregion
            return False

    def _convert_with_rio_tiler(self, geotiff_path: Path, output_path: Path) -> bool:
        """Convert GeoTIFF to mbtiles using rio-tiler with a temp COG (overviews) and progress."""
        _log_debug(
            "mbtiles_converter.py:_convert_with_rio_tiler:entry",
            "Starting rio-tiler conversion",
            {
                "geotiff_path": str(geotiff_path),
                "output_path": str(output_path),
                "min_zoom": self.min_zoom,
                "max_zoom": self.max_zoom,
            },
            "RT",
        )
        # Quick inspection to catch palette/scale issues before conversion
        self._inspect_geotiff_quick(geotiff_path)

        try:
            # Suppress noisy warnings from GDAL/rio-cogeo that don't affect output
            with warnings.catch_warnings():
                # Future GDAL default exception warning
                warnings.filterwarnings(
                    "ignore",
                    category=FutureWarning,
                    module="osgeo.gdal",
                )
                # rio-cogeo explicit warning class
                try:
                    from rio_cogeo.errors import NodataAlphaMaskWarning
                    warnings.filterwarnings("ignore", category=NodataAlphaMaskWarning)
                except Exception:
                    # Fallback on text match if class import fails
                    warnings.filterwarnings(
                        "ignore",
                        category=UserWarning,
                        message=".*NodataAlphaMaskWarning.*",
                    )

                tms = morecantile.tms.get("WebMercatorQuad")
                if output_path.exists():
                    output_path.unlink()

                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_dir_path = Path(temp_dir)
                    prep_path = self._check_and_convert_paletted_geotiff(
                        geotiff_path, temp_dir_path
                    )
                    source_for_cog = prep_path or geotiff_path
                    # #region agent log
                    _log_runtime_event(
                        "mbtiles_converter.py:_convert_with_rio_tiler:palette_prepared",
                        "Palette handling decision",
                        {
                            "original": str(geotiff_path),
                            "prepared": str(source_for_cog),
                            "used_converted": source_for_cog != geotiff_path,
                        },
                        hypothesis_id="PAL",
                    )
                    # #endregion

                    temp_cog_path = temp_dir_path / "temp_cog.tif"

                    profile = cog_profiles.get("deflate")
                    # Optional: enforce block sizes if desired
                    profile.update({"blockxsize": 256, "blockysize": 256})
                    cog_translate(
                        str(source_for_cog),
                        str(temp_cog_path),
                        profile,
                        nodata=0,
                        overview_level=5,
                        overview_resampling="average",
                        quiet=True,
                    )
                    # #region agent log
                    _log_runtime_event(
                        "mbtiles_converter.py:_convert_with_rio_tiler:cog_created",
                        "Temp COG created",
                        {
                            "temp_cog_path": str(temp_cog_path),
                            "temp_cog_exists": temp_cog_path.exists(),
                            "temp_cog_size": temp_cog_path.stat().st_size if temp_cog_path.exists() else 0,
                        },
                        hypothesis_id="PAL",
                    )
                    # #endregion

                    with COGReader(str(temp_cog_path), tms=tms) as cog:
                        bounds_wgs84 = cog.bounds
                        try:
                            # #region agent log
                            _log_runtime_event(
                                "mbtiles_converter.py:_convert_with_rio_tiler:cog_info",
                                "COGReader opened",
                                {
                                    "dataset_count": cog.dataset.count,
                                    "dataset_dtypes": list(cog.dataset.dtypes),
                                    "colorinterp": [str(ci) for ci in cog.dataset.colorinterp],
                                    "crs": str(cog.dataset.crs),
                                },
                                hypothesis_id="PAL",
                            )
                            # #endregion
                        except Exception:
                            pass

                    # Build a filtered tile list: sample at min_zoom to find tiles with data,
                    # then expand only those tiles across higher zooms. This avoids wasting
                    # time on large transparent areas.
                    base_zoom = self.min_zoom
                    alpha_threshold = 1  # drop tiles that are effectively fully transparent
                    base_tiles = list(
                        tms.tiles(
                            bounds_wgs84[0],
                            bounds_wgs84[1],
                            bounds_wgs84[2],
                            bounds_wgs84[3],
                            zooms=[base_zoom],
                        )
                    )
                    valid_base: set[tuple[int, int]] = set()
                    if base_tiles:
                        sample_tile = base_tiles[len(base_tiles) // 2]
                        try:
                            # #region agent log
                            sample_data, sample_mask = cog.tile(sample_tile.x, sample_tile.y, base_zoom, tilesize=256)
                            _log_runtime_event(
                                "mbtiles_converter.py:_convert_with_rio_tiler:sample_tile",
                                "Sample tile stats",
                                {
                                    "x": sample_tile.x,
                                    "y": sample_tile.y,
                                    "z": base_zoom,
                                    "shape": list(sample_data.shape),
                                    "dtype": str(sample_data.dtype),
                                    "data_min": float(np.min(sample_data)) if sample_data.size else None,
                                    "data_max": float(np.max(sample_data)) if sample_data.size else None,
                                    "mask_min": int(sample_mask.min()) if sample_mask.size else None,
                                    "mask_max": int(sample_mask.max()) if sample_mask.size else None,
                                },
                                hypothesis_id="PAL",
                            )
                            # #endregion
                        except Exception as e:
                            # #region agent log
                            _log_runtime_event(
                                "mbtiles_converter.py:_convert_with_rio_tiler:sample_tile_error",
                                "Sample tile read failed",
                                {
                                    "error": str(e),
                                    "x": sample_tile.x,
                                    "y": sample_tile.y,
                                    "z": base_zoom,
                                },
                                hypothesis_id="PAL",
                            )
                            # #endregion
                    for base_tile in base_tiles:
                        try:
                            _, base_mask = cog.tile(base_tile.x, base_tile.y, base_zoom, tilesize=256)
                        except Exception as e:
                            _log_debug(
                                "mbtiles_converter.py:_convert_with_rio_tiler:base_tile_error",
                                "Error reading base tile",
                                {"x": base_tile.x, "y": base_tile.y, "z": base_zoom, "error": str(e)},
                                "RT",
                            )
                            continue
                        if base_mask.max() > alpha_threshold:
                            valid_base.add((base_tile.x, base_tile.y))

                    tiles_list = []
                    for z in range(self.min_zoom, self.max_zoom + 1):
                        if z == base_zoom:
                            for bx, by in valid_base:
                                tiles_list.append((bx, by, z))
                        else:
                            scale = 2 ** (z - base_zoom)
                            for bx, by in valid_base:
                                start_x = bx * scale
                                start_y = by * scale
                                for dx in range(scale):
                                    for dy in range(scale):
                                        tiles_list.append((start_x + dx, start_y + dy, z))

                    conn = sqlite3.connect(str(output_path))
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA journal_mode=MEMORY;")
                    cursor.execute("PRAGMA synchronous=OFF;")
                    cursor.execute("PRAGMA temp_store=MEMORY;")
                    cursor.execute("PRAGMA cache_size=-50000;")
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS tiles (
                            zoom_level INTEGER,
                            tile_column INTEGER,
                            tile_row INTEGER,
                            tile_data BLOB
                        )
                    """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS metadata (
                            name TEXT,
                            value TEXT
                        )
                    """
                    )
                    cursor.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS tile_index 
                        ON tiles (zoom_level, tile_column, tile_row)
                    """
                    )

                    alpha_by_zoom: Dict[int, int] = {}
                    tile_count_by_zoom: Dict[int, int] = {}
                    dropped_transparent_by_zoom: Dict[int, int] = {}
                    size_sum_by_zoom: Dict[int, int] = {}
                    size_count_by_zoom: Dict[int, int] = {}
                    sample_dims_by_zoom: Dict[int, Dict[str, int]] = {}
                    tile_count = 0
                    alpha_logged = False
                    commit_interval = 500

                    # Tile-level spinner only (no bar) to reduce noise; outer bar remains
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task(
                            f"Converting {geotiff_path.name} tiles...", total=len(tiles_list)
                        )

                        workers = max(2, os.cpu_count()-2 or 1)
                        console.print(f"Using {workers} cores")
                        with concurrent.futures.ProcessPoolExecutor(
                            max_workers=workers,
                            initializer=_worker_init,
                            initargs=(str(temp_cog_path), "WebMercatorQuad"),
                        ) as executor:
                            for result in executor.map(
                                _worker_process_tile,
                                ((x, y, z, alpha_threshold) for (x, y, z) in tiles_list),
                                chunksize=32,
                            ):
                                if result is None:
                                    progress.advance(task)
                                    continue

                                status, z, x, y, tile_data_bytes, has_alpha, err = result

                                if status == "error":
                                    _log_debug(
                                        "mbtiles_converter.py:_convert_with_rio_tiler:tile_error",
                                        "Error reading tile",
                                        {"x": x, "y": y, "z": z, "error": err},
                                        "RT",
                                    )
                                    progress.advance(task)
                                    continue

                                if status == "dropped":
                                    dropped_transparent_by_zoom[z] = (
                                        dropped_transparent_by_zoom.get(z, 0) + 1
                                    )
                                    progress.advance(task)
                                    continue

                                tile_count_by_zoom[z] = tile_count_by_zoom.get(z, 0) + 1
                                if has_alpha:
                                    alpha_by_zoom[z] = alpha_by_zoom.get(z, 0) + 1
                                    if not alpha_logged:
                                        _log_debug(
                                            "mbtiles_converter.py:_convert_with_rio_tiler:alpha_detected",
                                            "Source tiles contain alpha; keeping PNG to preserve transparency",
                                            {"zoom": z, "x": x, "y": y},
                                            "BG",
                                        )
                                        alpha_logged = True

                                size_count_by_zoom[z] = size_count_by_zoom.get(z, 0) + 1
                                if z not in sample_dims_by_zoom:
                                    sample_dims_by_zoom[z] = {"w": 256, "h": 256}

                                if tile_data_bytes is None:
                                    progress.advance(task)
                                    continue

                                size_sum_by_zoom[z] = size_sum_by_zoom.get(z, 0) + len(
                                    tile_data_bytes
                                )

                                tms_y = (2**z - 1) - y
                                cursor.execute(
                                    """
                                    INSERT OR REPLACE INTO tiles 
                                    (zoom_level, tile_column, tile_row, tile_data)
                                    VALUES (?, ?, ?, ?)
                                """,
                                    (z, x, tms_y, tile_data_bytes),
                                )
                                tile_count += 1
                                if tile_count % commit_interval == 0:
                                    conn.commit()
                                progress.advance(task)

                    conn.commit()

                    metadata = [
                        ("name", output_path.stem.replace("terminal_", "").replace("sectional_", "")),
                        ("type", "overlay"),
                        ("version", "1.1"),
                        ("description", output_path.stem.replace("terminal_", "").replace("sectional_", "")),
                        ("format", "mixed"),
                        (
                            "bounds",
                            ",".join(
                                [
                                    f"{bounds_wgs84[0]}",
                                    f"{bounds_wgs84[1]}",
                                    f"{bounds_wgs84[2]}",
                                    f"{bounds_wgs84[3]}",
                                ]
                            ),
                        ),
                        ("minzoom", str(self.min_zoom)),
                        ("maxzoom", str(self.max_zoom)),
                    ]
                    cursor.executemany("INSERT INTO metadata (name, value) VALUES (?, ?)", metadata)
                    conn.commit()
                    conn.close()

                    _log_debug(
                        "mbtiles_converter.py:_convert_with_rio_tiler:success",
                        "Successfully converted with rio-tiler",
                        {
                            "tile_count": tile_count,
                            "output_size": output_path.stat().st_size if output_path.exists() else 0,
                            "alpha_by_zoom": alpha_by_zoom,
                            "tile_count_by_zoom": tile_count_by_zoom,
                            "avg_size_by_zoom": {
                                z: size_sum_by_zoom[z] // size_count_by_zoom[z]
                                for z in size_sum_by_zoom
                            },
                            "sample_dims_by_zoom": sample_dims_by_zoom,
                            "dropped_transparent_by_zoom": dropped_transparent_by_zoom,
                        },
                        "J",
                    )
                    return True

        except Exception as e:
            console.print(f"[red]Error converting with rio-tiler: {e}[/red]")
            _log_debug(
                "mbtiles_converter.py:_convert_with_rio_tiler:error",
                "Exception during rio-tiler conversion",
                {"error": str(e), "error_type": type(e).__name__},
                "RT",
            )
            return False
        finally:
            if "temp_cog_path" in locals() and temp_cog_path and temp_cog_path.exists():
                try:
                    temp_cog_path.unlink()
                except Exception:
                    pass

    def convert(self, geotiff_path: Path, output_path: Path) -> bool:
        """Convert GeoTIFF to mbtiles using available method.

        Args:
            geotiff_path: Path to input GeoTIFF file
            output_path: Path to output mbtiles file

        Returns:
            True if successful, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:convert:entry",
            "Starting conversion",
            {
                "geotiff_path": str(geotiff_path),
                "geotiff_exists": geotiff_path.exists(),
                "geotiff_size": geotiff_path.stat().st_size if geotiff_path.exists() else 0,
                "output_path": str(output_path),
                "min_zoom": self.min_zoom,
                "max_zoom": self.max_zoom
            },
            "A"
        )
        # #endregion

        if not geotiff_path.exists():
            console.print(f"[red]GeoTIFF file not found: {geotiff_path}[/red]")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert:error",
                "GeoTIFF file not found",
                {"geotiff_path": str(geotiff_path)},
                "A"
            )
            # #endregion
            return False

        console.print(
            f"[cyan]Converting {geotiff_path.name} to mbtiles...[/cyan]"
        )

        # Preferred: rio-tiler pipeline (Python, full control)
        if self._convert_with_rio_tiler(geotiff_path, output_path):
            console.print(f"[green]✓[/green] Converted using rio-tiler")
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:convert:success",
                "Conversion succeeded with rio-tiler",
                {
                    "method": "rio-tiler",
                    "output_exists": output_path.exists(),
                    "output_size": output_path.stat().st_size if output_path.exists() else 0
                },
                "A"
            )
            # #endregion
            if self._verify_mbtiles(output_path):
                if self._verify_and_fix_zoom_levels(output_path):
                    return True

        console.print(
            "[red]Conversion failed with rio-tiler[/red]"
        )
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:convert:failure",
            "rio-tiler conversion failed",
            {},
            "A"
        )
        # #endregion
        return False

    def _verify_mbtiles(self, mbtiles_path: Path) -> bool:
        """Verify mbtiles file structure and content.

        Args:
            mbtiles_path: Path to mbtiles file

        Returns:
            True if valid, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:_verify_mbtiles:entry",
            "Verifying mbtiles file",
            {"mbtiles_path": str(mbtiles_path), "exists": mbtiles_path.exists()},
            "B"
        )
        # #endregion

        if not mbtiles_path.exists():
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_mbtiles:error",
                "mbtiles file does not exist",
                {"mbtiles_path": str(mbtiles_path)},
                "B"
            )
            # #endregion
            return False

        file_size = mbtiles_path.stat().st_size
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:_verify_mbtiles:size",
            "mbtiles file size",
            {"mbtiles_path": str(mbtiles_path), "file_size": file_size},
            "B"
        )
        # #endregion

        if file_size == 0:
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_mbtiles:error",
                "mbtiles file is empty",
                {"mbtiles_path": str(mbtiles_path), "file_size": file_size},
                "B"
            )
            # #endregion
            return False

        try:
            # Check if it's a valid SQLite database
            conn = sqlite3.connect(str(mbtiles_path))
            cursor = conn.cursor()

            # Check for metadata table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
            has_metadata = cursor.fetchone() is not None
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_mbtiles:metadata",
                "Metadata table check",
                {"has_metadata": has_metadata},
                "B"
            )
            # #endregion

            if has_metadata:
                # Get metadata
                cursor.execute("SELECT name, value FROM metadata")
                metadata = dict(cursor.fetchall())
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:_verify_mbtiles:metadata_content",
                    "Metadata content",
                    {"metadata": metadata},
                    "B"
                )
                # #endregion

            # Check for tiles table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tiles'")
            has_tiles = cursor.fetchone() is not None
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_mbtiles:tiles",
                "Tiles table check",
                {"has_tiles": has_tiles},
                "C"
            )
            # #endregion

            if has_tiles:
                # Count tiles
                cursor.execute("SELECT COUNT(*) FROM tiles")
                tile_count = cursor.fetchone()[0]
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:_verify_mbtiles:tile_count",
                    "Tile count",
                    {"tile_count": tile_count},
                    "C"
                )
                # #endregion

                # Get zoom level range
                cursor.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
                zoom_range = cursor.fetchone()
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:_verify_mbtiles:zoom_range",
                    "Zoom level range",
                    {"min_zoom": zoom_range[0] if zoom_range[0] else None, "max_zoom": zoom_range[1] if zoom_range[1] else None},
                    "C"
                )
                # #endregion

            conn.close()

            is_valid = has_metadata and has_tiles
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_mbtiles:result",
                "Verification result",
                {"is_valid": is_valid, "has_metadata": has_metadata, "has_tiles": has_tiles},
                "B"
            )
            # #endregion
            return is_valid

        except Exception as e:
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_mbtiles:error",
                "Error verifying mbtiles",
                {"error": str(e), "error_type": type(e).__name__},
                "B"
            )
            # #endregion
            console.print(f"[yellow]Warning: Could not verify mbtiles structure: {e}[/yellow]")
            return True  # Assume valid if we can't verify

    def _has_multiple_zoom_levels(self, mbtiles_path: Path) -> bool:
        """Check if mbtiles has tiles at multiple zoom levels.

        Args:
            mbtiles_path: Path to mbtiles file

        Returns:
            True if multiple zoom levels exist, False otherwise
        """
        try:
            conn = sqlite3.connect(str(mbtiles_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT zoom_level) FROM tiles")
            distinct_zooms = cursor.fetchone()[0]
            conn.close()
            return distinct_zooms > 1
        except Exception:
            return False

    def _verify_and_fix_zoom_levels(self, mbtiles_path: Path) -> bool:
        """Verify mbtiles has correct zoom levels and fix metadata if needed.

        Args:
            mbtiles_path: Path to mbtiles file

        Returns:
            True if valid or fixed, False otherwise
        """
        # #region agent log
        _log_debug(
            "mbtiles_converter.py:_verify_and_fix_zoom_levels:entry",
            "Verifying and fixing zoom levels",
            {"mbtiles_path": str(mbtiles_path)},
            "F"
        )
        # #endregion

        if not mbtiles_path.exists():
            return False

        try:
            conn = sqlite3.connect(str(mbtiles_path))
            cursor = conn.cursor()

            # Get current metadata
            cursor.execute("SELECT name, value FROM metadata WHERE name IN ('minzoom', 'maxzoom')")
            metadata_dict = dict(cursor.fetchall())
            current_minzoom = int(metadata_dict.get('minzoom', 0))
            current_maxzoom = int(metadata_dict.get('maxzoom', 0))

            # Get actual zoom levels in tiles table
            cursor.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
            zoom_range = cursor.fetchone()
            actual_minzoom = zoom_range[0] if zoom_range[0] is not None else current_minzoom
            actual_maxzoom = zoom_range[1] if zoom_range[1] is not None else current_maxzoom

            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_and_fix_zoom_levels:current",
                "Current zoom levels",
                {
                    "metadata_minzoom": current_minzoom,
                    "metadata_maxzoom": current_maxzoom,
                    "actual_minzoom": actual_minzoom,
                    "actual_maxzoom": actual_maxzoom,
                    "requested_minzoom": self.min_zoom,
                    "requested_maxzoom": self.max_zoom
                },
                "F"
            )
            # #endregion

            # Check if zoom levels match what we requested
            # If tiles only exist at one zoom level (like 13), we need to warn
            if actual_minzoom == actual_maxzoom and actual_minzoom > self.max_zoom:
                console.print(
                    f"[yellow]⚠️  Warning: Tiles only exist at zoom {actual_maxzoom}, "
                    f"but ForeFlight may need lower zoom levels (requested {self.min_zoom}-{self.max_zoom})[/yellow]"
                )
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:_verify_and_fix_zoom_levels:warning",
                    "Zoom level mismatch - tiles only at high zoom",
                    {
                        "actual_zoom": actual_maxzoom,
                        "requested_range": f"{self.min_zoom}-{self.max_zoom}"
                    },
                    "F"
                )
                # #endregion
                # Update metadata to reflect actual zoom levels
                cursor.execute(
                    "UPDATE metadata SET value = ? WHERE name = 'minzoom'",
                    (str(actual_minzoom),)
                )
                cursor.execute(
                    "UPDATE metadata SET value = ? WHERE name = 'maxzoom'",
                    (str(actual_maxzoom),)
                )
                conn.commit()
                conn.close()
                return True  # File is valid, just has different zoom levels

            # Update metadata if needed
            if current_minzoom != actual_minzoom or current_maxzoom != actual_maxzoom:
                cursor.execute(
                    "UPDATE metadata SET value = ? WHERE name = 'minzoom'",
                    (str(actual_minzoom),)
                )
                cursor.execute(
                    "UPDATE metadata SET value = ? WHERE name = 'maxzoom'",
                    (str(actual_maxzoom),)
                )
                conn.commit()

            conn.close()
            return True

        except Exception as e:
            # #region agent log
            _log_debug(
                "mbtiles_converter.py:_verify_and_fix_zoom_levels:error",
                "Error verifying/fixing zoom levels",
                {"error": str(e), "error_type": type(e).__name__},
                "F"
            )
            # #endregion
            return True  # Assume valid if we can't verify

    def convert_batch(
        self, charts: list, output_dir: Path
    ) -> list:
        """Convert multiple GeoTIFF files to mbtiles.

        Args:
            charts: List of chart dictionaries with geotiff_path
            output_dir: Directory for output mbtiles files

        Returns:
            List of charts with added mbtiles_path field
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        charts_with_mbtiles = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Converting GeoTIFF to mbtiles...", total=len(charts)
            )

            for chart in charts:
                geotiff_path = Path(chart.get("geotiff_path", ""))
                if not geotiff_path.exists():
                    console.print(
                        f"[yellow]GeoTIFF not found for {chart.get('chart_name', 'unknown')}[/yellow]"
                    )
                    progress.advance(task)
                    continue

                chart_name = chart["chart_name"]
                progress.update(task, description=f"Converting {chart_name}")

                # Generate mbtiles filename
                safe_name = self._sanitize_filename(chart_name)
                chart_type = chart.get("chart_type", "unknown")
                mbtiles_filename = f"{chart_type}_{safe_name}.mbtiles"
                mbtiles_path = output_dir / mbtiles_filename

                # Convert
                # #region agent log
                _log_debug(
                    "mbtiles_converter.py:convert_batch:before_convert",
                    "Before conversion",
                    {
                        "chart_name": chart_name,
                        "geotiff_path": str(geotiff_path),
                        "mbtiles_path": str(mbtiles_path),
                        "geotiff_exists": geotiff_path.exists(),
                        "geotiff_size": geotiff_path.stat().st_size if geotiff_path.exists() else 0
                    },
                    "D"
                )
                # #endregion

                if self.convert(geotiff_path, mbtiles_path):
                    chart["mbtiles_path"] = str(mbtiles_path)
                    charts_with_mbtiles.append(chart)
                    console.print(
                        f"[green]✓[/green] Created: {mbtiles_filename}"
                    )
                    # #region agent log
                    _log_debug(
                        "mbtiles_converter.py:convert_batch:after_convert",
                        "After successful conversion",
                        {
                            "chart_name": chart_name,
                            "mbtiles_path": str(mbtiles_path),
                            "mbtiles_exists": mbtiles_path.exists(),
                            "mbtiles_size": mbtiles_path.stat().st_size if mbtiles_path.exists() else 0
                        },
                        "D"
                    )
                    # #endregion
                else:
                    console.print(
                        f"[red]✗[/red] Failed to convert {chart_name}"
                    )
                    # #region agent log
                    _log_debug(
                        "mbtiles_converter.py:convert_batch:convert_failed",
                        "Conversion failed",
                        {
                            "chart_name": chart_name,
                            "mbtiles_path": str(mbtiles_path),
                            "mbtiles_exists": mbtiles_path.exists()
                        },
                        "D"
                    )
                    # #endregion

                progress.advance(task)

        return charts_with_mbtiles

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        import re

        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        # Remove extra spaces and replace with single underscore
        filename = re.sub(r"\s+", "_", filename)
        # Remove leading/trailing underscores
        filename = filename.strip("_")
        return filename
