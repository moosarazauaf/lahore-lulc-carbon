"""Spatial driver stack describing *where* each conversion is likely.

Every driver here is derived from the LULC maps themselves, so the pipeline is
reproducible from the four Earth Engine exports alone with no extra downloads.
Lahore District is a flat alluvial plain, so terrain adds almost nothing; the
variables that actually govern conversion here are proximity to existing
built-up fabric and position along the city's growth gradient.

Externally-sourced drivers (OSM road network, canal network) plug in through
`extra_layers` when available.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from config import PIXEL_SIZE_M

NEIGHBOURHOOD_WINDOWS = (3, 7, 15)


def _distance_to(binary: np.ndarray) -> np.ndarray:
    """Euclidean distance in metres to the nearest True pixel."""
    if not binary.any():
        return np.full(binary.shape, np.nan, dtype="float32")
    d = ndimage.distance_transform_edt(~binary, sampling=PIXEL_SIZE_M)
    return d.astype("float32")


def _fraction(binary: np.ndarray, size: int) -> np.ndarray:
    """Share of a square neighbourhood occupied by the given class."""
    return ndimage.uniform_filter(
        binary.astype("float32"), size=size, mode="nearest"
    ).astype("float32")


def build(lulc: np.ndarray, mask: np.ndarray, extra_layers: dict | None = None):
    """Return (stack, names) where stack is (n_pixels, n_features) over `mask`.

    Drivers are recomputed from the *current* map at every simulation step, which
    is what makes this a cellular automaton rather than a static regression: new
    built-up created in 2033 changes the neighbourhood and distance surfaces that
    drive allocation in 2043.
    """
    layers: list[np.ndarray] = []
    names: list[str] = []

    built = lulc == 0
    veg = lulc == 1
    water = lulc == 2
    bare = lulc == 3

    for arr, nm in ((built, "builtup"), (water, "water"), (veg, "vegetation")):
        layers.append(_distance_to(arr))
        names.append(f"dist_to_{nm}_m")

    for arr, nm in ((built, "builtup"), (veg, "vegetation"), (bare, "bare")):
        for w in NEIGHBOURHOOD_WINDOWS:
            layers.append(_fraction(arr, w))
            names.append(f"frac_{nm}_{w}x{w}")

    # Position relative to the built-up centre of mass: a scale-free stand-in for
    # distance to the city core, which dominates peri-urban conversion.
    rows, cols = np.indices(lulc.shape, dtype="float32")
    if built.any():
        cr, cc = ndimage.center_of_mass(built)
    else:
        cr, cc = lulc.shape[0] / 2, lulc.shape[1] / 2
    dr, dc = (rows - cr) * PIXEL_SIZE_M, (cols - cc) * PIXEL_SIZE_M
    layers.append(np.hypot(dr, dc).astype("float32"))
    names.append("dist_to_urban_core_m")
    layers.append(np.arctan2(dr, dc).astype("float32"))
    names.append("bearing_from_core_rad")

    if extra_layers:
        for nm, arr in extra_layers.items():
            layers.append(arr.astype("float32"))
            names.append(nm)

    stack = np.column_stack([lay[mask] for lay in layers])
    stack = np.nan_to_num(stack, nan=-1.0, posinf=-1.0, neginf=-1.0)
    return stack.astype("float32"), names
