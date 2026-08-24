"""Tests for paletted GeoTIFF handling in the MBTiles converter."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.mbtiles_converter import MBTilesConverter


class TestPalettedGeoTIFF:
    """Paletted FAA charts should be expanded to RGBA via a VRT, without GDAL CLI."""

    def _write_paletted_geotiff(self, path):
        data = np.array([[0, 1], [2, 3]], dtype=np.uint8)
        colormap = {
            0: (255, 0, 0, 255),
            1: (0, 255, 0, 255),
            2: (0, 0, 255, 255),
            3: (0, 0, 0, 0),
        }
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(0, 2, 1, 1),
            photometric="palette",
        ) as dst:
            dst.write(data, 1)
            dst.write_colormap(1, colormap)

    def test_detects_paletted_geotiff(self, tmp_path):
        path = tmp_path / "paletted.tif"
        self._write_paletted_geotiff(path)

        converter = MBTilesConverter()
        assert converter._is_paletted_geotiff(path) is True

    def test_creates_rgba_vrt_for_paletted_geotiff(self, tmp_path):
        path = tmp_path / "paletted.tif"
        self._write_paletted_geotiff(path)

        converter = MBTilesConverter()
        vrt_path = converter._check_and_convert_paletted_geotiff(path, tmp_path)

        assert vrt_path is not None
        assert vrt_path != path
        assert vrt_path.suffix == ".vrt"
        assert vrt_path.exists()

        with rasterio.open(vrt_path) as src:
            assert src.count == 4
            red, green, blue, _alpha = src.read()
            assert red[0, 0] == 255
            assert green[0, 1] == 255
            assert blue[1, 0] == 255

    def test_leaves_rgb_geotiff_unchanged(self, tmp_path):
        path = tmp_path / "rgb.tif"
        data = np.zeros((3, 2, 2), dtype=np.uint8)
        data[0] = 10
        data[1] = 20
        data[2] = 30
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=3,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(0, 2, 1, 1),
        ) as dst:
            dst.write(data)

        converter = MBTilesConverter()
        assert converter._is_paletted_geotiff(path) is False
        result = converter._check_and_convert_paletted_geotiff(path, tmp_path)
        assert result == path
