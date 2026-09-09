"""Raster loading, alignment checking and writing.

The four classified maps come out of Earth Engine as separate exports. They are
NOT guaranteed to share a grid, so every load goes through a consistency check
rather than assuming the arrays line up. Silently comparing misaligned rasters
would produce a transition matrix full of fictitious change.
"""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from config import CLASS_IDS, LULC_FILES, NODATA


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
        legal = np.isin(arr, CLASS_IDS)
        if not legal.all():
            notes.append(f"{y}: {int((~legal).sum()):,} pixels outside class range")
        arr[~legal] = NODATA
        maps[y] = arr

    valid = np.ones(ref_arr.shape, dtype=bool)
    for arr in maps.values():
        valid &= arr != NODATA

    if valid.sum() == 0:
        raise GridMismatch("no pixel is valid in all years; check exports share an extent")

    for n in notes:
        print(f"  note  {n}")
    print(f"  common valid pixels: {int(valid.sum()):,} of {valid.size:,} "
          f"({100 * valid.sum() / valid.size:.1f}%)")
    return maps, profile, valid


def write(path, array: np.ndarray, profile: dict, dtype: str = "uint8", nodata=NODATA):
    p = profile.copy()
    p.update(dtype=dtype, count=1, nodata=nodata, compress="lzw")
    with rasterio.open(path, "w", **p) as dst:
        dst.write(array.astype(dtype), 1)
    return path
