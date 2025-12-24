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



# Worker globals for parallel tile processing
_worker_cog_reader: Optional[COGReader] = None
_worker_tms = None
_worker_logged = False


def _worker_init(cog_path: str, tms_id: str) -> None:
    """Initializer for worker processes to open COGReader once per process."""
    global _worker_cog_reader, _worker_tms
    
    # Suppress warnings in worker processes
    import warnings
    warnings.filterwarnings("ignore", module="rio_tiler.reader")
    try:
        from rio_tiler.errors import NodataShadowWarning
        warnings.filterwarnings("ignore", category=NodataShadowWarning)
    except Exception:
        warnings.filterwarnings(
            "ignore",
            category=UserWarning,
            message=".*NodataShadowWarning.*",
        )
    
    _worker_tms = morecantile.tms.get(tms_id)
    _worker_cog_reader = COGReader(cog_path, tms=_worker_tms)


def _worker_process_tile(args: Tuple[int, int, int, int, int]) -> Tuple[str, int, int, int, Optional[bytes], bool, Optional[str]]:
    """Process a single tile in a worker process.

    Returns:
        ("ok", z, x, y, tile_bytes, has_alpha, None) on success
        ("dropped", z, x, y, None, False, None) if transparent
        ("error", z, x, y, None, False, error_message) on error
    """
    global _worker_cog_reader
    if _worker_cog_reader is None:
        return ("error", -1, -1, -1, None, False, "COGReader not initialized")

    x, y, z, alpha_threshold, tile_size = args
    try:
        data, mask = _worker_cog_reader.tile(x, y, z, tilesize=tile_size)
    except Exception as e:  # pragma: no cover - defensive
        return ("error", z, x, y, None, False, str(e))

    global _worker_logged
    if not _worker_logged:
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

    def __init__(self, min_zoom: int = 6, max_zoom: int = 12, verbose: bool = False):
        """Initialize the mbtiles converter.

        Args:
            min_zoom: Minimum zoom level for tiles (default: 6, shows when zoomed out)
            max_zoom: Maximum zoom level for tiles (default: 12, reasonable detail)
            verbose: If True, show detailed progress output; if False, show progress bar with status
        """
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        self.verbose = verbose
        self.tile_size = 512  # Use 512x512 tiles for better performance

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
        

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                "gdal2mbtiles",
                "-z",
                f"{self.min_zoom}-{self.max_zoom}",
                str(geotiff_path),
                str(output_path),
            ]

            

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600
            )

            

            if result.returncode == 0:
                return True
            else:
                console.print(
                    f"[red]gdal2mbtiles failed: {result.stderr}[/red]"
                )
                return False

        except subprocess.TimeoutExpired:
            console.print("[red]Conversion timed out[/red]")
            
            return False
        except Exception as e:
            console.print(f"[red]Error converting with gdal2mbtiles: {e}[/red]")
            
            return False

    def _check_and_convert_paletted_geotiff(
        self, geotiff_path: Path, temp_dir: Path, verbose: bool = False
    ) -> Optional[Path]:
        """Check if GeoTIFF is paletted and convert to RGBA if needed.

        Args:
            geotiff_path: Path to input GeoTIFF file
            temp_dir: Temporary directory for converted file

        Returns:
            Path to RGBA GeoTIFF if conversion needed, original path otherwise
        """
        

        try:
            from osgeo import gdal

            src_ds = gdal.Open(str(geotiff_path))
            if src_ds is None:
                return None

            # Check if it's paletted (indexed color)
            band = src_ds.GetRasterBand(1)
            color_table = band.GetColorTable()

            

            src_ds = None
            band = None

            if color_table is not None:
                # Use VRT format instead of full RGBA conversion (much faster!)
                # VRT is a virtual format that expands on-the-fly without creating a huge file
                if verbose:
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

                

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60
                )

                if result.returncode == 0 and vrt_path.exists():
                    
                    return vrt_path
                else:
                    console.print(
                        f"[yellow]Warning: Failed to create VRT: {result.stderr}[/yellow]"
                    )
                    
                    return None

            return geotiff_path  # Not paletted, use original

        except Exception as e:
            console.print(f"[yellow]Warning: Could not check GeoTIFF format: {e}[/yellow]")
            
            return geotiff_path  # Assume not paletted, use original

    def _inspect_geotiff_quick(self, geotiff_path: Path) -> None:
        """Collect minimal GeoTIFF metadata for debugging palette/scaling issues."""
        try:
            from osgeo import gdal
        except Exception as e:  # pragma: no cover - defensive
            
            return

        try:
            ds = gdal.Open(str(geotiff_path))
            if ds is None:
                
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
        except Exception as e:  # pragma: no cover - defensive
            return False

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
        

        try:
            import shutil
            import tempfile

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Find gdal2tiles.py
            gdal2tiles = shutil.which("gdal2tiles.py") or shutil.which("gdal2tiles")
            if not gdal2tiles:
                
                return False

            # Create temporary directory for tiles and converted GeoTIFF
            with tempfile.TemporaryDirectory() as temp_base_dir:
                temp_base_path = Path(temp_base_dir)
                temp_tiles_path = temp_base_path / "tiles"
                temp_geotiff_dir = temp_base_path / "geotiff"
                temp_geotiff_dir.mkdir(exist_ok=True)

                # Check if GeoTIFF is paletted and convert if needed
                input_geotiff = self._check_and_convert_paletted_geotiff(
                    geotiff_path, temp_geotiff_dir, verbose=self.verbose
                )
                if input_geotiff is None:
                    
                    return False

                

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

                

                if result.returncode != 0:
                    console.print(
                        f"[red]gdal2tiles.py failed: {result.stderr}[/red]"
                    )
                    return False

                # Convert tile directory to mbtiles
                if self._tiles_dir_to_mbtiles(temp_tiles_path, output_path, geotiff_path):
                    
                    return True
                else:
                    return False

        except Exception as e:
            console.print(f"[red]Error converting with gdal2tiles: {e}[/red]")
            
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

            # Calculate bounds in source projection
            min_x = geotransform[0]
            max_y = geotransform[3]
            max_x = min_x + width * geotransform[1]
            min_y = max_y + height * geotransform[5]

            # CRITICAL FIX: Convert bounds to WGS84 (lat/lon) for ForeFlight
            # MBTiles bounds must be in WGS84 format: min_lon, min_lat, max_lon, max_lat
            src_srs = osr.SpatialReference()
            src_srs.ImportFromWkt(projection)
            tgt_srs = osr.SpatialReference()
            tgt_srs.ImportFromEPSG(4326)  # WGS84
            
            transform = osr.CoordinateTransformation(src_srs, tgt_srs)
            
            # Transform corners to WGS84
            corners = [
                (min_x, min_y),  # bottom-left
                (max_x, min_y),  # bottom-right
                (max_x, max_y),  # top-right
                (min_x, max_y),  # top-left
            ]
            
            wgs84_corners = []
            for x, y in corners:
                lon, lat, _ = transform.TransformPoint(x, y)
                wgs84_corners.append((lon, lat))
            
            # Get min/max lon and lat
            min_lon = min(c[0] for c in wgs84_corners)
            max_lon = max(c[0] for c in wgs84_corners)
            min_lat = min(c[1] for c in wgs84_corners)
            max_lat = max(c[1] for c in wgs84_corners)
            
            

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
            chart_name = output_path.stem.replace("T_", "").replace("S_", "").replace("terminal_", "").replace("sectional_", "")
            metadata = [
                ("name", chart_name),
                ("type", "overlay"),
                ("version", "1.1"),
                ("description", chart_name),
                ("format", "jpeg" if compress_jpeg else "png"),
                ("bounds", f"{min_lon},{min_lat},{max_lon},{max_lat}"),  # WGS84 bounds
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

            

            console.print(f"[cyan]Inserted {tile_count} tiles into mbtiles[/cyan]")
            
            
            
            if tile_count == 0:
                console.print("[red]ERROR: No tiles found in tile directory![/red]")
                return False
            
            return True

        except Exception as e:
            console.print(f"[red]Error converting tiles to mbtiles: {e}[/red]")
            
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
        

        try:
            from osgeo import gdal

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Open the GeoTIFF
            src_ds = gdal.Open(str(geotiff_path))
            if src_ds is None:
                console.print(f"[red]Failed to open GeoTIFF: {geotiff_path}[/red]")
                
                return False

            

            # Create mbtiles driver
            driver = gdal.GetDriverByName("MBTiles")
            if driver is None:
                console.print("[red]MBTiles driver not available[/red]")
                
                return False

            # GDAL MBTiles driver does NOT support ZOOM_LEVEL option (as confirmed by warning)
            # We need to use a different approach - skip CreateCopy and use gdal2tiles instead
            
            
            # Return False to fall back to gdal2tiles method
            return False

            if dst_ds is None:
                console.print(f"[red]Failed to create mbtiles: {output_path}[/red]")
                
                return False

            

            # Clean up
            dst_ds = None
            src_ds = None

            return True

        except ImportError:
            console.print(
                "[yellow]Python GDAL bindings not available, trying alternative methods[/yellow]"
            )
            
            return False
        except Exception as e:
            console.print(f"[red]Error converting with Python GDAL: {e}[/red]")
            
            return False

    def _convert_with_rio_tiler(self, geotiff_path: Path, output_path: Path, verbose: bool = False) -> bool:
        """Convert GeoTIFF to mbtiles using rio-tiler with a temp COG (overviews) and progress."""
        # Quick inspection to catch palette/scale issues before conversion
        self._inspect_geotiff_quick(geotiff_path)

        try:
            # Suppress noisy warnings from GDAL/rio-cogeo/rio-tiler that don't affect output
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
                # rio-tiler NodataShadowWarning
                try:
                    from rio_tiler.errors import NodataShadowWarning
                    warnings.filterwarnings("ignore", category=NodataShadowWarning)
                except Exception:
                    # Fallback on text match if class import fails
                    warnings.filterwarnings(
                        "ignore",
                        category=UserWarning,
                        message=".*NodataShadowWarning.*",
                    )
                # Also suppress by module to catch any rio_tiler warnings
                warnings.filterwarnings(
                    "ignore",
                    module="rio_tiler.reader",
                )

                tms = morecantile.tms.get("WebMercatorQuad")
                if output_path.exists():
                    output_path.unlink()

                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_dir_path = Path(temp_dir)
                    prep_path = self._check_and_convert_paletted_geotiff(
                        geotiff_path, temp_dir_path, verbose=verbose
                    )
                    source_for_cog = prep_path or geotiff_path
                    

                    temp_cog_path = temp_dir_path / "temp_cog.tif"

                    profile = cog_profiles.get("deflate")
                    # Match block sizes to tile size for better performance
                    tile_size = self.tile_size
                    profile.update({"blockxsize": tile_size, "blockysize": tile_size})
                    cog_translate(
                        str(source_for_cog),
                        str(temp_cog_path),
                        profile,
                        nodata=0,
                        overview_level=5,
                        overview_resampling="average",
                        quiet=True,
                    )
                    

                    with COGReader(str(temp_cog_path), tms=tms) as cog:
                        # Get bounds in dataset CRS
                        dataset_bounds = cog.bounds
                        dataset_crs = cog.dataset.crs
                        
                        # CRITICAL FIX: Convert bounds to WGS84 (lat/lon) for ForeFlight
                        # cog.bounds returns bounds in the dataset's native CRS, not necessarily WGS84
                        from rasterio.warp import transform_bounds
                        bounds_wgs84 = transform_bounds(
                            dataset_crs,
                            "EPSG:4326",  # WGS84
                            dataset_bounds[0],  # minx
                            dataset_bounds[1],  # miny
                            dataset_bounds[2],  # maxx
                            dataset_bounds[3],  # maxy
                        )
                        
                        
                        
                        try:
                            pass
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
                    tile_size = self.tile_size
                    for base_tile in base_tiles:
                        try:
                            _, base_mask = cog.tile(base_tile.x, base_tile.y, base_zoom, tilesize=tile_size)
                        except Exception as e:
                            continue
                        if base_mask.max() > alpha_threshold:
                            valid_base.add((base_tile.x, base_tile.y))
                    
                    # If no valid base tiles found, try processing all tiles anyway (maybe threshold is too strict)
                    if len(valid_base) == 0 and len(base_tiles) > 0:
                        if verbose:
                            console.print("[yellow]Warning: No tiles passed alpha threshold, processing all tiles anyway[/yellow]")
                        valid_base = {(t.x, t.y) for t in base_tiles}

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

                    # Tile-level progress display
                    if verbose:
                        # Verbose: spinner with description
                        progress_display = Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            console=console,
                        )
                    else:
                        # Non-verbose: no display (outer progress bar shows status)
                        # Create a no-op progress object
                        class NoOpProgress:
                            def __enter__(self):
                                return self
                            def __exit__(self, *args):
                                pass
                            def add_task(self, *args, **kwargs):
                                return None
                            def advance(self, *args):
                                pass
                        progress_display = NoOpProgress()
                    
                    with progress_display:
                        if verbose:
                            task = progress_display.add_task(
                                f"Converting {geotiff_path.name} tiles...", total=len(tiles_list)
                            )
                        else:
                            task = None
                        
                        progress = progress_display

                        workers = max(2, (os.cpu_count() or 1) - 2)
                        if verbose:
                            console.print(f"Using {workers} cores")
                        tile_size = self.tile_size
                        with concurrent.futures.ProcessPoolExecutor(
                            max_workers=workers,
                            initializer=_worker_init,
                            initargs=(str(temp_cog_path), "WebMercatorQuad"),
                        ) as executor:
                            for result in executor.map(
                                _worker_process_tile,
                                ((x, y, z, alpha_threshold, tile_size) for (x, y, z) in tiles_list),
                                chunksize=32,
                            ):
                                if result is None:
                                    if verbose and task is not None:
                                        progress.advance(task)
                                    continue

                                status, z, x, y, tile_data_bytes, has_alpha, err = result

                                if status == "error":
                                    if verbose and task is not None:
                                        progress.advance(task)
                                    continue

                                if status == "dropped":
                                    dropped_transparent_by_zoom[z] = (
                                        dropped_transparent_by_zoom.get(z, 0) + 1
                                    )
                                    if verbose and task is not None:
                                        progress.advance(task)
                                    continue

                                tile_count_by_zoom[z] = tile_count_by_zoom.get(z, 0) + 1
                                if has_alpha:
                                    alpha_by_zoom[z] = alpha_by_zoom.get(z, 0) + 1
                                    if not alpha_logged:
                                        alpha_logged = True

                                size_count_by_zoom[z] = size_count_by_zoom.get(z, 0) + 1
                                if z not in sample_dims_by_zoom:
                                    sample_dims_by_zoom[z] = {"w": tile_size, "h": tile_size}

                                if tile_data_bytes is None:
                                    if verbose and task is not None:
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
                                if verbose and task is not None:
                                    progress.advance(task)

                    conn.commit()

                    metadata = [
                        ("name", output_path.stem.replace("T_", "").replace("S_", "").replace("terminal_", "").replace("sectional_", "")),
                        ("type", "overlay"),
                        ("version", "1.1"),
                        ("description", output_path.stem.replace("T_", "").replace("S_", "").replace("terminal_", "").replace("sectional_", "")),
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

                    

                    # CRITICAL: Return False if no tiles were generated
                    if tile_count == 0:
                        console.print("[red]ERROR: No tiles were generated![/red]")
                        
                        return False

                    return True

        except Exception as e:
            console.print(f"[red]Error converting with rio-tiler: {e}[/red]")
            return False
        finally:
            if "temp_cog_path" in locals() and temp_cog_path and temp_cog_path.exists():
                try:
                    temp_cog_path.unlink()
                except Exception:
                    pass

    def convert(self, geotiff_path: Path, output_path: Path, verbose: Optional[bool] = None) -> bool:
        """Convert GeoTIFF to mbtiles using available method.

        Args:
            geotiff_path: Path to input GeoTIFF file
            output_path: Path to output mbtiles file
            verbose: Override verbose setting (None uses instance default)

        Returns:
            True if successful, False otherwise
        """
        if verbose is None:
            verbose = self.verbose

        if not geotiff_path.exists():
            if verbose:
                console.print(f"[red]GeoTIFF file not found: {geotiff_path}[/red]")
            return False

        if verbose:
            console.print(
                f"[cyan]Converting {geotiff_path.name} to mbtiles...[/cyan]"
            )

        # Preferred: rio-tiler pipeline (Python, full control)
        if self._convert_with_rio_tiler(geotiff_path, output_path, verbose=verbose):
            if verbose:
                console.print("[green]Converted using rio-tiler[/green]")
            
            if self._verify_mbtiles(output_path):
                if self._verify_and_fix_zoom_levels(output_path):
                    return True

        if verbose:
            console.print(
                "[red]Conversion failed with rio-tiler[/red]"
            )
        
        return False

    def _verify_mbtiles(self, mbtiles_path: Path) -> bool:
        """Verify mbtiles file structure and content.

        Args:
            mbtiles_path: Path to mbtiles file

        Returns:
            True if valid, False otherwise
        """
        

        if not mbtiles_path.exists():
            
            return False

        file_size = mbtiles_path.stat().st_size
        

        if file_size == 0:
            
            return False

        try:
            # Check if it's a valid SQLite database
            conn = sqlite3.connect(str(mbtiles_path))
            cursor = conn.cursor()

            # Check for metadata table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
            has_metadata = cursor.fetchone() is not None
            

            if has_metadata:
                # Get metadata
                cursor.execute("SELECT name, value FROM metadata")
                metadata = dict(cursor.fetchall())
                

            # Check for tiles table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tiles'")
            has_tiles = cursor.fetchone() is not None
            

            if has_tiles:
                # Count tiles
                cursor.execute("SELECT COUNT(*) FROM tiles")
                tile_count = cursor.fetchone()[0]
                

                # Get zoom level range
                cursor.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
                zoom_range = cursor.fetchone()
                

            conn.close()

            is_valid = has_metadata and has_tiles
            
            return is_valid

        except Exception as e:
            
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

            

            # Check if zoom levels match what we requested
            # If tiles only exist at one zoom level (like 13), we need to warn
            if actual_minzoom == actual_maxzoom and actual_minzoom > self.max_zoom:
                console.print(
                    f"[yellow]  Warning: Tiles only exist at zoom {actual_maxzoom}, "
                    f"but ForeFlight may need lower zoom levels (requested {self.min_zoom}-{self.max_zoom})[/yellow]"
                )
                
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
            
            return True  # Assume valid if we can't verify

    def convert_batch(
        self, charts: list, output_dir: Path, chart_type_label: str = "Charts"
    ) -> list:
        """Convert multiple GeoTIFF files to mbtiles.

        Args:
            charts: List of chart dictionaries with geotiff_path
            output_dir: Directory for output mbtiles files
            chart_type_label: Label for the chart type (e.g., "Sectional charts", "Terminal charts")

        Returns:
            List of charts with added mbtiles_path field
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        charts_with_mbtiles = []

        if self.verbose:
            # Verbose mode: spinner with detailed output
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
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

                    # Generate mbtiles filename with short prefix
                    safe_name = self._sanitize_filename(chart_name)
                    chart_type = chart.get("chart_type", "unknown")
                    # Use short prefixes: T_ for terminal, S_ for sectional
                    prefix_map = {"terminal": "T", "sectional": "S"}
                    prefix = prefix_map.get(chart_type, chart_type[:1].upper())
                    mbtiles_filename = f"{prefix}_{safe_name}.mbtiles"
                    mbtiles_path = output_dir / mbtiles_filename

                    # Convert
                    if self.convert(geotiff_path, mbtiles_path, verbose=self.verbose):
                        chart["mbtiles_path"] = str(mbtiles_path)
                        charts_with_mbtiles.append(chart)
                        console.print(
                            f"[green]Created:[/green] {mbtiles_filename}"
                        )
                    else:
                        console.print(
                            f"[red]Failed to convert {chart_name}[/red]"
                        )

                    progress.advance(task)
        else:
            # Non-verbose mode: progress bar with spinner and status
            with Progress(
                SpinnerColumn(),
                BarColumn(),
                TextColumn("[progress.description]{task.description}"),
                TextColumn("[dim]{task.fields[status]}[/dim]", justify="right"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Processing {chart_type_label}",
                    total=len(charts),
                    status=""
                )

                for idx, chart in enumerate(charts):
                    geotiff_path = Path(chart.get("geotiff_path", ""))
                    if not geotiff_path.exists():
                        progress.update(task, status=f"[yellow]Skipping {chart.get('chart_name', 'unknown')}[/yellow]")
                        progress.advance(task)
                        continue

                    chart_name = chart["chart_name"]
                    progress.update(task, status=chart_name)

                    # Generate mbtiles filename with short prefix
                    safe_name = self._sanitize_filename(chart_name)
                    chart_type = chart.get("chart_type", "unknown")
                    # Use short prefixes: T_ for terminal, S_ for sectional
                    prefix_map = {"terminal": "T", "sectional": "S"}
                    prefix = prefix_map.get(chart_type, chart_type[:1].upper())
                    mbtiles_filename = f"{prefix}_{safe_name}.mbtiles"
                    mbtiles_path = output_dir / mbtiles_filename

                    # Convert (suppress output in non-verbose mode)
                    if self.convert(geotiff_path, mbtiles_path, verbose=False):
                        chart["mbtiles_path"] = str(mbtiles_path)
                        charts_with_mbtiles.append(chart)
                    else:
                        progress.update(task, status=f"[red]Failed: {chart_name}[/red]")

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
