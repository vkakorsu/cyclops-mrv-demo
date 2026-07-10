"""
CYCLOPS MRV Demo Pipeline
=========================
Searches Sentinel-2 imagery via STAC, computes NDVI, estimates carbon stock,
and writes a Cloud-Optimized GeoTIFF.

This demonstrates the core CYCLOPS workflow: STAC discovery -> vegetation
index -> carbon estimation -> cloud-native raster output.

Author: Vincent Kofi Akorsu
"""

import os
import tempfile
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy
from pystac_client import Client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STAC_API = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# Area of interest: Kakum National Park, Ghana (protected tropical forest)
# bbox = [west, south, east, north]
AOI_BBOX = [-1.45, 5.30, -1.30, 5.42]

DATE_RANGE = "2024-01-01/2024-06-30"
MAX_CLOUD_COVER = 10  # percent

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
OUTPUT_COG = os.path.join(OUTPUT_DIR, "ndvi_carbon_cog.tif")

# NDVI-to-aboveground-carbon regression (Gajabuih Forest, West Sumatra)
# AGC (tC/ha) = 48.358 * NDVI - 4.2339
# Source: IJPSAT v28.1.3422, R2 = 0.43
# Carbon = 0.5 * Biomass (IPCC standard)
CARBON_SLOPE = 48.358
CARBON_INTERCEPT = -4.2339


def search_scenes():
    """Search the STAC API for the least-cloudy Sentinel-2 scene over the AOI."""
    print(f"Connecting to STAC API: {STAC_API}")
    client = Client.open(STAC_API)

    search = client.search(
        collections=[COLLECTION],
        bbox=AOI_BBOX,
        datetime=DATE_RANGE,
        query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
        sortby=["+properties.eo:cloud_cover"],
        max_items=10,
    )

    items = list(search.items())
    if not items:
        raise RuntimeError(
            f"No scenes found over {AOI_BBOX} with cloud cover < {MAX_CLOUD_COVER}%"
        )

    best = items[0]
    cloud = best.properties.get("eo:cloud_cover", "unknown")
    print(f"Found {len(items)} scenes. Best: {best.id} (cloud cover: {cloud}%)")
    return best


def download_band(item, band_name):
    """Download a single band asset from a STAC item and return the array + metadata."""
    if band_name not in item.assets:
        raise KeyError(f"Band '{band_name}' not found in item assets: {list(item.assets.keys())}")

    href = item.assets[band_name].href
    print(f"  Downloading {band_name} from {href[:80]}...")

    with rasterio.open(href) as src:
        # Read at native resolution, windowed read for the AOI
        data = src.read(1, resampling=Resampling.nearest).astype(np.float32)
        profile = src.profile.copy()

    return data, profile


def compute_ndvi(red, nir):
    """Compute NDVI = (NIR - Red) / (NIR + Red), handling division by zero."""
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / (nir + red)
    ndvi = np.where(np.isfinite(ndvi), ndvi, 0.0)
    # Clip to valid NDVI range
    ndvi = np.clip(ndvi, -1.0, 1.0)
    return ndvi


def estimate_carbon(ndvi):
    """
    Estimate aboveground carbon stock (tC/ha) from NDVI.

    Uses a published linear regression: AGC = 48.358 * NDVI - 4.2339
    (Gajabuih Forest, West Sumatra, R2 = 0.43).

    Pixels with NDVI < 0.1 (non-vegetated) are set to 0 carbon.
    """
    carbon = CARBON_SLOPE * ndvi + CARBON_INTERCEPT
    # Mask non-vegetated and negative estimates
    carbon = np.where(ndvi >= 0.1, carbon, 0.0)
    carbon = np.clip(carbon, 0.0, None)
    return carbon


def write_cog(array, profile, output_path):
    """
    Write a Cloud-Optimized GeoTIFF.

    Uses GDAL's COG driver via rasterio's copy operation with COG
    creation options: LZW compression, 512px tiles, internal overviews.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Update profile for single-band float32 output
    cog_profile = profile.copy()
    cog_profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        compress="lzw",
        tiled=True,
        blockxsize=512,
        blockysize=512,
        predictor=2,
    )

    # Write to a temp GeoTIFF first, then translate to COG
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    with rasterio.open(tmp_path, "w", **cog_profile) as dst:
        dst.write(array.astype(np.float32), 1)
        dst.set_band_description(1, "Aboveground Carbon Stock (tC/ha)")

    # Translate to COG using GDAL's COG driver
    cog_profile_final = {
        "driver": "COG",
        "compress": "LZW",
        "blocksize": 512,
        "resampling": Resampling.average,
    }

    with rasterio.open(tmp_path) as src:
        rio_copy(src, output_path, **cog_profile_final)

    os.unlink(tmp_path)
    print(f"  COG written to {output_path}")


def print_summary(carbon, ndvi):
    """Print summary statistics for the computed NDVI and carbon estimates."""
    valid_carbon = carbon[carbon > 0]
    valid_ndvi = ndvi[(ndvi >= 0.1) & (ndvi <= 1.0)]

    pixel_area_ha = 0.01  # 10m x 10m pixel = 100 m2 = 0.01 ha

    print("\n" + "=" * 60)
    print("CYCLOPS MRV Demo - Summary")
    print("=" * 60)
    print(f"  NDVI range:     {valid_ndvi.min():.3f} to {valid_ndvi.max():.3f}")
    print(f"  NDVI mean:      {valid_ndvi.mean():.3f}")
    print(f"  Vegetated pixels: {len(valid_ndvi):,} of {ndvi.size:,}")
    print(f"  Carbon (tC/ha): {valid_carbon.min():.2f} to {valid_carbon.max():.2f}")
    print(f"  Carbon mean:    {valid_carbon.mean():.2f} tC/ha")
    print(f"  Total carbon:   {valid_carbon.sum() * pixel_area_ha:.2f} tC")
    print(f"  Area:           {ndvi.size * pixel_area_ha:.2f} ha")
    print("=" * 60)


def main():
    """Run the full pipeline: STAC search -> NDVI -> carbon -> COG output."""
    print("CYCLOPS MRV Demo Pipeline")
    print("-" * 40)

    # 1. Search for Sentinel-2 scenes via STAC
    print("\n[1/5] Searching STAC API for Sentinel-2 scenes...")
    scene = search_scenes()

    # 2. Download red and NIR bands
    print("\n[2/5] Downloading bands...")
    red_band, profile = download_band(scene, "red")
    nir_band, _ = download_band(scene, "nir")

    # 3. Compute NDVI
    print("\n[3/5] Computing NDVI...")
    ndvi = compute_ndvi(red_band, nir_band)

    # 4. Estimate carbon stock
    print("\n[4/5] Estimating aboveground carbon stock...")
    carbon = estimate_carbon(ndvi)

    # 5. Write Cloud-Optimized GeoTIFF
    print("\n[5/5] Writing Cloud-Optimized GeoTIFF...")
    write_cog(carbon, profile, OUTPUT_COG)

    # Summary
    print_summary(carbon, ndvi)

    print(f"\nDone. Output: {OUTPUT_COG}")
    print("Open in QGIS or load via rasterio.open() to inspect.")


if __name__ == "__main__":
    main()
