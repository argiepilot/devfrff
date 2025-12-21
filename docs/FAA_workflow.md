## FAA VFR Charts Workflow (Sectional + Terminal)

### What the pipeline does
- Scrapes the FAA VFR Raster Charts page for GEO‑TIFF download links (Sectional/Terminal).
- Downloads the ZIPs and extracts the GeoTIFFs.
- Handles paletted (indexed color) TIFFs by building a VRT with RGBA expansion on-the-fly (no huge intermediate file).
  VRT (Virtual Dataset): a tiny XML wrapper produced via gdal_translate -of VRT -expand rgba for paletted TIFFs. It references the original raster and expands to RGBA on-the-fly, avoiding large intermediate files while feeding gdal2tiles.
- Generates multi-zoom tiles with `gdal2tiles.py` (zoom 6–13) using XYZ numbering.
- Converts the tile directory into an MBTiles file, compressing tiles to JPEG (quality 75) during insertion to reduce size.
- Writes manifest and packages output under `VFR Charts Package/`.

### Key tools and why
- `requests` + `BeautifulSoup`: scrape FAA chart tables and extract GEO‑TIFF links.
- `zipfile`: download/extract GEO‑TIFFs from FAA ZIPs.
- `gdal_translate -of VRT -expand rgba`: turns paletted TIFFs into a VRT (virtual) RGBA source without producing a giant intermediate file.
- `gdal2tiles.py -z 6-13 --xyz`: creates tiles across multiple zoom levels; 6–13 keeps charts visible when zoomed out but avoids explosion in tile count.
- `sqlite3` + `Pillow`: build MBTiles manually from the tiles directory and recompress to JPEG (quality 75) to cut size.

### MBTiles structure we produce
- **Tables**
  - `metadata`: name, type=overlay, version=1.1, description, format=jpeg, bounds, minzoom, maxzoom.
  - `tiles`: columns (`zoom_level`, `tile_column`, `tile_row`, `tile_data`).
- **Tile numbering**
  - `gdal2tiles.py` emits XYZ (OSM) tiles; when inserting we flip Y to TMS: `tms_y = (2^z - 1) - xyz_y`.
- **Zooms**
  - Default `min_zoom=6`, `max_zoom=13`. Visible when zoomed out; detailed enough without massive size.
- **Compression**
  - Tiles are recompressed to JPEG (quality 75, optimize) during MBTiles assembly; metadata `format` set to `jpeg`.
- **Bounds**
  - Derived from the source GeoTIFF geotransform: `minx,miny,maxx,maxy` stored in metadata.

### Workflow steps (CLI)
1. Activate env: `conda activate devfrff`
2. Run unified/test mode (Terminal example):  
   - Full detail: `python run.py process-all --test-terminal`  
   - Faster quick check (zoom 6–10): `python run.py process-all --test-terminal-quick`
3. Outputs:  
   - `VFR Charts Package/layers/terminal_<Name>.mbtiles` (JPEG-compressed tiles, zoom 6–13)  
   - `VFR Charts Package/manifest.json`

### Design choices for size/performance
- Use VRT (not full RGBA TIFF) to avoid ~10× ballooning of intermediate files.
- Limit zooms to 6–13 to balance visibility vs. tile count.
- JPEG recompression (quality 75) to target sizes closer to MapTiler outputs.

