"""Regenerate the map figures from saved rasters, without re-running the model.

The projection takes several minutes; cartographic tweaks should not. This
reads the observed maps plus the projected GeoTIFFs already in outputs/maps/
and rebuilds every map figure.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import rasterio

import cartography as carto
import carbon
import rasters
from config import FIG_DIR, MAP_DIR, NODATA, OBSERVED_YEARS, PROJECTION_YEARS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_projected(profile, mask):
    out = {}
    for y in PROJECTION_YEARS:
        p = MAP_DIR / f"projected_{y}.tif"
        if not p.exists():
            print(f"  missing {p.name}; run src/run_pipeline.py first")
            continue
        with rasterio.open(p) as src:
            arr = src.read(1).astype("uint8")
        arr[~mask] = NODATA
        out[y] = arr
    return out


def main():
    maps, profile, mask = rasters.load_all(OBSERVED_YEARS)
    area = rasters.pixel_area_ha(profile)
    maps.update(load_projected(profile, mask))
    years = sorted(maps)

    print("\nmap figures")
    print("  " + str(carto.lulc_panel(maps, mask, profile, area=area,
                                      observed=OBSERVED_YEARS)))

    for y in years:
        print("  " + str(carto.single_map(
            maps[y], mask, profile, y, area=area,
            projected=y not in OBSERVED_YEARS)))

    for a, b in ((1993, 2023), (2023, 2043)):
        if a in maps and b in maps:
            print("  " + str(carto.builtup_expansion_map(
                maps[a], maps[b], mask, profile, a, b, area=area)))

    vmax = max(float(np.nanmax(carbon.density_map(maps[y], mask)))
               for y in years)
    for y in (OBSERVED_YEARS[0], OBSERVED_YEARS[-1], years[-1]):
        dens = carbon.density_map(maps[y], mask)
        print("  " + str(carto.carbon_map(dens, mask, profile, y, vmax=vmax, area=area)))

    print(f"\n  all written to {FIG_DIR}")


if __name__ == "__main__":
    main()
