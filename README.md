# CYCLOPS MRV Demo

A minimal, end-to-end geospatial pipeline that demonstrates the core CYCLOPS workflow: **search satellite imagery via STAC, compute vegetation indices, estimate carbon stocks, and output Cloud-Optimized GeoTIFFs for cloud-native access.**

Built as a proof-of-concept for the dClimate CYCLOPS Full-Stack Geospatial Data Engineer role.

## What This Does

1. **STAC search:** Uses `pystac-client` to query the Earth Search API (Element84) for Sentinel-2 L2A scenes over a forested area, filtered by cloud cover.
2. **Band access:** Downloads the red and near-infrared (NIR) bands from the best scene.
3. **NDVI computation:** Calculates the Normalized Difference Vegetation Index (NDVI = (NIR - Red) / (NIR + Red)) using Rasterio.
4. **Carbon stock estimation:** Applies a published NDVI-to-aboveground-carbon regression model to estimate tonnes of carbon per hectare.
5. **COG output:** Writes the result as a Cloud-Optimized GeoTIFF (COG) with internal overviews, LZW compression, and 512x512 tiling for efficient cloud access.
6. **Summary statistics:** Prints total estimated carbon stock, mean, and per-pixel statistics for the area of interest.

## Quickstart

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python pipeline.py
```

Output COG is written to `output/ndvi_carbon_cog.tif`.

### Visualize the COG

Open `viewer.html` in a browser, click "Load COG file," and select `output/ndvi_carbon_cog.tif`. The carbon raster renders on a Leaflet map with a color ramp from low (dark green) to high (red) carbon stock.

The viewer uses `georaster-layer-for-leaflet` to parse the COG client-side, no tile server required.

### Run via Docker

```bash
docker build -t cyclops-mrv-demo .
docker run --rm -v $(pwd)/output:/app/output cyclops-mrv-demo
```

The Docker image uses the official `ghcr.io/osgeo/gdal:ubuntu-small-latest` base with GDAL pre-installed.

## Pipeline Architecture

```
STAC API (Earth Search) --> pystac-client search
    --> Sentinel-2 L2A scene selection (lowest cloud cover)
        --> download red + NIR bands (rasterio)
            --> NDVI computation
                --> carbon stock regression (NDVI -> tC/ha)
                    --> write Cloud-Optimized GeoTIFF
                        --> summary statistics
```

## Carbon Estimation Method

The pipeline uses a published linear regression model relating NDVI to aboveground carbon stock:

```
AGC (tC/ha) = 48.358 * NDVI - 4.2339
```

This model was derived from field inventory data correlated with Landsat NDVI in tropical secondary forest (Gajabuih, West Sumatra, R2 = 0.43). Carbon is estimated as 50% of aboveground biomass, following the standard IPCC conversion factor.

**Limitations:** This is a simplified demonstration. Production MRV systems would use:
- Field-calibrated allometric equations specific to the project region
- Multi-temporal biomass change detection (not single-scene)
- Uncertainty quantification and propagation
- Validation against ground truth plots
- Additional covariates (EVI, SAVI, radar backscatter, canopy height models)

## Area of Interest

Default AOI is the **Kakum National Park** area in Ghana (5.35N, 1.38W), a protected tropical forest. This is configurable in `pipeline.py`.

## Tech Stack

| Component | Tool |
|---|---|
| STAC search | pystac-client, Earth Search API (Element84) |
| Raster I/O | rasterio, GDAL |
| COG creation | rasterio + GDAL COG driver |
| Data format | Cloud-Optimized GeoTIFF (LZW, 512px tiles, overviews) |
| Language | Python 3.10+ |

## Repository Layout

```
cyclops-mrv-demo/
  pipeline.py          Main pipeline: STAC search -> NDVI -> carbon -> COG
  viewer.html          Leaflet web viewer for COG visualization
  Dockerfile           Containerized pipeline (GDAL + Python)
  requirements.txt     Python dependencies
  README.md            This file
  output/              Generated COGs (gitignored)
```

## Why This Matters for CYCLOPS

CYCLOPS turns petabytes of Earth observation imagery into auditable carbon metrics. This demo shows the foundational pipeline pattern:

- **STAC-based scene discovery** (not manual downloads)
- **Cloud-Optimized GeoTIFF output** (not plain TIFFs)
- **Web visualization** (Leaflet + georaster-layer-for-leaflet, no tile server)
- **Containerized** (Docker with GDAL base image)
- **Reproducible carbon estimation** (documented model, deterministic)
- **Minimal dependencies** (no heavy frameworks, just the right tools)

At production scale, this pattern extends to: Dask for distributed processing, Zarr for chunked array storage, Prefect for orchestration, and GPU-accelerated processing (RAPIDS/TorchGeo) for petabyte-scale workflows.

## References

- STAC API: https://earth-search.aws.element84.com/v1
- pystac-client docs: https://pystac-client.readthedocs.io
- GDAL COG driver: https://gdal.org/drivers/raster/cog.html
- NDVI-carbon regression model: Gajabuih Forest, West Sumatra (IJPSAT v28.1.3422)
- IPCC carbon conversion factor: Carbon = 0.5 x Biomass
