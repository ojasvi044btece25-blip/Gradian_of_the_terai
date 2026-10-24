# Guardian of the Terai

> **Satellite-based flood mapping for Nepal's Terai region**  
> Detects flooded areas by comparing pre-flood and post-flood Sentinel-1 SAR backscatter GeoTIFFs.

---

## ⚠️ Data Disclaimer

All flood statistics produced by this system are derived from **raster pixel arithmetic on actual input files**.  
No flood extents, pixel counts, or statistics are fabricated, interpolated, or estimated from external sources.  
The synthetic rasters used in tests are explicitly labelled and must never be presented as real observations.

---

## Architecture

```
c:\decade\
├── guardian/                    # Core Python package
│   ├── config.py                # Constants and tuneable parameters
│   ├── preprocessing/
│   │   └── sentinel.py          # GeoTIFF validation, loading (dB / linear), alignment check
│   ├── detection/
│   │   └── flood.py             # Backscatter change detection + min-area filter
│   ├── output/
│   │   ├── geotiff.py           # Flood mask → uint8 GeoTIFF (0/1/255)
│   │   └── geojson.py           # Flood mask → GeoJSON polygon (WGS 84)
│   └── api/
│       ├── main.py              # FastAPI app factory
│       └── routes/
│           ├── health.py        # GET /health
│           └── analysis.py      # POST /analyze, GET /results/{job_id}/{file}
├── dashboard/
│   ├── app.py                   # Streamlit UI
│   └── map_utils.py             # Folium helpers
└── tests/                       # pytest suite (synthetic data only)
```

---

## Detection Algorithm

```
σ°_post (dB) − σ°_pre (dB) = Δ

If Δ < threshold_db  AND  pixel is valid in both scenes:
    → flooded
```

| Parameter | Default | Location |
|---|---|---|
| Threshold | **−3 dB** | `guardian/config.py → DEFAULT_THRESHOLD_DB` |
| Min area filter | **9 pixels** | `guardian/config.py → MIN_AREA_PIXELS` |

The −3 dB threshold is a widely-used heuristic from ESA/DLR change-detection literature.  
**Tune it for your region using ground-truth data.**

---

## Input Requirements

| Requirement | Details |
|---|---|
| Format | Single-band GeoTIFF |
| Radiometric scale | **dB** (use `ScaleHint.LINEAR` if your data is in linear power) |
| Co-registration | Both scenes must have identical CRS, pixel dimensions, and affine transform |
| Nodata | Must be declared in the GeoTIFF header (GDAL nodata tag) |
| Polarisation | VV or VH (single band) |

> **Pre-processing tip:** Use [ESA SNAP](https://step.esa.int/main/toolboxes/snap/) to apply  
> orbit correction → thermal noise removal → calibration → terrain correction → co-registration.

---

## Setup

### 1. Install dependencies

> On Windows, rasterio and GDAL are most reliably installed via conda:
> ```bash
> conda create -n guardian python=3.11
> conda activate guardian
> conda install -c conda-forge rasterio scipy fiona shapely
> pip install -r requirements.txt
> ```

Or with pip only (may require pre-built GDAL wheels):
```bash
pip install -r requirements.txt
```

### 2. Run the API backend
```bash
uvicorn guardian.api.main:app --reload --host 0.0.0.0 --port 8000
```
API docs: http://localhost:8000/docs

### 3. Run the Streamlit dashboard
```bash
streamlit run dashboard/app.py
```

### 4. Run tests
```bash
pytest -v
```

---

## API Reference

### `GET /health`
```json
{ "status": "ok", "version": "0.1.0", "service": "Guardian of the Terai" }
```

### `POST /analyze`

**Accepts:** `multipart/form-data` with:
- `pre_flood` — pre-flood Sentinel-1 GeoTIFF (dB scale)
- `post_flood` — post-flood Sentinel-1 GeoTIFF (dB scale)

**Returns:**
```json
{
  "job_id": "550e8400-e29b-...",
  "flooded_pixel_count": 1234,
  "valid_pixel_count": 50000,
  "flooded_fraction": 0.024680,
  "flood_geotiff_url": "/results/{job_id}/flood.tif",
  "flood_geojson_url": "/results/{job_id}/flood.geojson",
  "note": "Statistics are computed from raster pixel arithmetic..."
}
```

**Error responses:**
- `422` — Invalid or misaligned GeoTIFFs
- `500` — Internal processing failure

### `GET /results/{job_id}/flood.tif`
Download the classified flood GeoTIFF.  Pixel encoding:

| Value | Meaning |
|---|---|
| `0` | Valid, not flooded |
| `1` | Flooded |
| `255` | Invalid / nodata |

### `GET /results/{job_id}/flood.geojson`
Download the flood polygons as a GeoJSON FeatureCollection (WGS 84 / EPSG:4326).

---

## Python API

```python
from guardian.preprocessing.sentinel import ScaleHint, validate_geotiff, align_rasters, load_band
from guardian.detection.flood import detect_flood
from guardian.output.geotiff import write_flood_geotiff
from guardian.output.geojson import write_flood_geojson

# Validate inputs
validate_geotiff("pre_flood.tif")
align_rasters("pre_flood.tif", "post_flood.tif")  # raises AlignmentError if mismatched

# Detect flooding
result = detect_flood(
    "pre_flood.tif",
    "post_flood.tif",
    threshold_db=-3.0,     # configurable
    min_area_pixels=9,
    scale=ScaleHint.DB,    # always explicit — never assumed
)

print(f"Flooded: {result.flooded_pixel_count} / {result.valid_pixel_count} px "
      f"({result.flooded_fraction:.2%})")

# Write outputs
write_flood_geotiff(result, "flood_mask.tif")
write_flood_geojson(result, "flood_polygons.geojson")
```

---
# Core geospatial libraries
geopandas>=0.14.0
shapely>=2.0.0
pyproj>=3.6.0

# Data processing
pandas>=2.0.0
numpy>=1.24.0

# Earth Engine (for data acquisition - used by teammate)
earthengine-api>=0.1.300
geemap>=0.14.0

# OSM data processing
osmnx>=1.5.0

# Raster processing (for Sentinel-1 flood detection)
rasterio>=1.3.0
scipy>=1.10.0

# Dashboard
streamlit>=1.28.0
streamlit-folium>=0.11.0
plotly>=5.0.0

# Logging and utilities
python-dateutil>=2.8.0


## Assumptions & Limitations

### Assumptions
- Input imagery is in **dB scale** (default).  Pass `scale=ScaleHint.LINEAR` for linear power.
- Both scenes are **co-registered** before use (same CRS, grid, and extent).
- The −3 dB threshold is an empirical heuristic; it does not generalise to all land covers.
- Nodata pixels are those declared in the GeoTIFF metadata (not implicitly 0 or NaN).

### Limitations
| Limitation | Impact |
|---|---|
| No terrain layover/shadow mask | False positives on steep slopes |
| No urban area mask | Building double-bounce can resemble open water |
| No speckle filter (only a post-classification size filter) | Residual isolated false positives |
| No automatic co-registration | Misaligned inputs produce clear `AlignmentError` |
| No temporal normelling | Seasonally varying dry-land backscatter shifts the effective threshold |
| In-memory job store | Job results lost on server restart; not for production use |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GUARDIAN_RESULTS_DIR` | `./results` | Directory for generated job outputs |

---

## Contributing

1. Fork and branch from `main`.
2. Add tests for any new detection logic.
3. Run `pytest -v` before opening a PR.
4. Never commit real satellite imagery or actual flood observations.
