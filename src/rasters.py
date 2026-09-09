"""Raster loading, alignment checking and writing.

The four classified maps come out of Earth Engine as separate exports. They are
NOT guaranteed to share a grid, so every load goes through a consistency check
rather than assuming the arrays line up. Silently comparing misaligned rasters
would produce a transition matrix full of fictitious change.
"""
from __future__ import annotations

import numpy as np
import rasterio
from scipy import ndimage
from rasterio.enums import Resampling
from rasterio.warp import reproject

from config import LULC_FILES, MERGE, NODATA, RAW_CLASS_IDS, SCHEME


class GridMismatch(RuntimeError):
    pass


def load_reference(year: int):
    """Load one map and return (array, profile) as the reference grid."""
    with rasterio.open(LULC_FILES[year]) as src:
        arr = src.read(1)
        profile = src.profile.copy()
    return arr, profile


def _align_to(path, ref_profile) -> np.ndarray:
    """Read `path` onto the reference grid, nearest-neighbour only.

    Nearest neighbour is not a preference here, it is a requirement: class codes
    are nominal, so any averaging resampler would invent classes that do not
    exist (the mean of Built-up=0 and Water=2 is Vegetation=1).
    """
    with rasterio.open(path) as src:
        same = (
            src.crs == ref_profile["crs"]
            and src.transform.almost_equals(ref_profile["transform"])
            and src.width == ref_profile["width"]
            and src.height == ref_profile["height"]
        )
        if same:
            return src.read(1)

        dst = np.full((ref_profile["height"], ref_profile["width"]), NODATA, dtype="uint8")
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            dst_nodata=NODATA,
            resampling=Resampling.nearest,
        )
        return dst


def load_all(years) -> tuple[dict[int, np.ndarray], dict, np.ndarray]:
    """Load every year onto a common grid.

    Returns (maps, profile, valid_mask). `valid_mask` is True only where EVERY
    year has a legal class code, so all downstream statistics are computed over
    an identical pixel population and area totals are comparable between dates.
    """
    ref_year = years[0]
    ref_arr, profile = load_reference(ref_year)
    profile.update(dtype="uint8", count=1, nodata=NODATA, compress="lzw")

    maps: dict[int, np.ndarray] = {}
    notes: list[str] = []
    for y in years:
        arr = ref_arr if y == ref_year else _align_to(LULC_FILES[y], profile)
        arr = arr.astype("uint8", copy=True)
        legal = np.isin(arr, RAW_CLASS_IDS)
        if not legal.all():
            notes.append(f"{y}: {int((~legal).sum()):,} pixels outside class range")
        arr[~legal] = NODATA
        maps[y] = arr

    valid = np.ones(ref_arr.shape, dtype=bool)
    for arr in maps.values():
        valid &= arr != NODATA

    # The mask must be derived from the RAW codes. Merging bare land into
    # built-up first would add class-0 pixels along the district edge and let
    # the flood fill leak inward, eroding the boundary.
    inside = district_mask(maps)
    dropped = int((valid & ~inside).sum())
    valid &= inside
    for arr in maps.values():
        arr[~valid] = NODATA
    print(f"  district mask: excluded {dropped:,} pixels written as class 0 "
          f"outside the clip geometry")

    if MERGE:
        moved = 0
        for arr in maps.values():
            for src, dst in MERGE.items():
                sel = arr == src
                moved += int(sel.sum())
                arr[sel] = dst
        print(f"  scheme '{SCHEME}': merged {moved:,} pixels via {MERGE}")

    if valid.sum() == 0:
        raise GridMismatch("no pixel is valid in all years; check exports share an extent")

    for n in notes:
        print(f"  note  {n}")
    print(f"  common valid pixels: {int(valid.sum()):,} of {valid.size:,} "
          f"({100 * valid.sum() / valid.size:.1f}%)")
    return maps, profile, valid


def pixel_area_ha(profile) -> np.ndarray:
    """Per-pixel area in hectares, computed geodesically.

    The exports are geographic (EPSG:4326), so pixel width in metres shrinks
    with latitude and a pixel is NOT (30 m)^2. Area of a graticule cell on a
    sphere is R^2 * dlon * (sin(lat_top) - sin(lat_bottom)), which is exact
    enough here and avoids reprojecting nominal class codes.
    """
    R = 6378137.0
    T = profile["transform"]
    h, w = profile["height"], profile["width"]
    rows = np.arange(h)
    lat_top = T.f
    dlat, dlon = abs(T.e), abs(T.a)
    p1 = np.radians(lat_top - rows * dlat)
    p2 = np.radians(lat_top - (rows + 1) * dlat)
    row_m2 = (R ** 2) * np.radians(dlon) * np.abs(np.sin(p1) - np.sin(p2))
    return np.repeat((row_m2 / 10_000.0)[:, None], w, axis=1).astype("float64")


def district_mask(maps: dict[int, np.ndarray]) -> np.ndarray:
    """Recover the clip geometry that Earth Engine applied.

    The exports carry no nodata value, so every pixel outside the district
    polygon was written as 0 - which is the Built-up class code. Left alone this
    labels roughly 44% of the raster as city and corrupts every area, carbon and
    transition figure computed from these files.

    The outside region is identifiable as the set of pixels that are class 0 in
    EVERY year AND connect to the raster border. Genuine built-up that was
    already urban in 1993 is also class 0 in every year, but the district's own
    edges were rural in 1993, so it does not bridge to the border. The recovered
    area is checked against the district's published extent by the caller.
    """
    zero_all = np.ones(next(iter(maps.values())).shape, dtype=bool)
    for a in maps.values():
        zero_all &= a == 0

    labels, _ = ndimage.label(zero_all)
    edge = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    edge.discard(0)
    outside = np.isin(labels, sorted(edge))

    inside = ~outside
    # Close pinholes where a lone in-district pixel touched the outside region.
    inside = ndimage.binary_fill_holes(inside)
    return inside


def write(path, array: np.ndarray, profile: dict, dtype: str = "uint8", nodata=NODATA):
    p = profile.copy()
    p.update(dtype=dtype, count=1, nodata=nodata, compress="lzw")
    with rasterio.open(path, "w", **p) as dst:
        dst.write(array.astype(dtype), 1)
    return path
