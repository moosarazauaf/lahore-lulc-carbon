"""Project-wide configuration: class scheme, carbon densities, paths, years.

Two class schemes are supported, selected by the LULC_SCHEME environment
variable so that every module importing this file agrees on one of them:

  four  (default)  Built-up / Vegetation / Water / Bare land, as classified
  three            Bare land merged into Built-up as a single non-vegetated class

The three-class scheme exists because bare land is not stable in these maps:
between 58% and 82% of bare-land pixels change class each decade, which is
Landsat confusing dry soil with concrete rather than real land change. Merging
removes that churn from the transition matrix. Both schemes are kept so the
choice can be justified rather than asserted.
"""
import os
from pathlib import Path

SCHEME = os.environ.get("LULC_SCHEME", "four").lower()
if SCHEME not in ("four", "three"):
    raise ValueError(f"LULC_SCHEME must be 'four' or 'three', got {SCHEME!r}")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LULC_DIR = DATA / "lulc"
DRIVER_DIR = DATA / "drivers"
OUT = ROOT / ("outputs" if SCHEME == "four" else "outputs_3class")
MAP_DIR = OUT / "maps"
FIG_DIR = OUT / "figures"
TAB_DIR = OUT / "tables"

for _d in (LULC_DIR, DRIVER_DIR, MAP_DIR, FIG_DIR, TAB_DIR):
    _d.mkdir(parents=True, exist_ok=True)

OBSERVED_YEARS = [1993, 2003, 2013, 2023]
PROJECTION_YEARS = [2033, 2043]

LULC_FILES = {y: LULC_DIR / f"Lahore_{y}_RF_LULC.tif" for y in OBSERVED_YEARS}

# ---------------------------------------------------------------- class scheme
# What the Earth Engine exports actually contain, always.
RAW_CLASSES = {0: "Built-up", 1: "Vegetation", 2: "Water", 3: "Bare land"}
RAW_CLASS_IDS = sorted(RAW_CLASSES)

# Remapping applied to the raw codes for the active scheme.
MERGE = {} if SCHEME == "four" else {3: 0}

if SCHEME == "four":
    CLASSES = dict(RAW_CLASSES)
    CLASS_COLOURS = {0: "#c0392b", 1: "#27ae60", 2: "#2874a6", 3: "#d4ac0d"}
else:
    CLASSES = {0: "Built-up / bare", 1: "Vegetation", 2: "Water"}
    CLASS_COLOURS = {0: "#c0392b", 1: "#27ae60", 2: "#2874a6"}

CLASS_IDS = sorted(CLASSES)
N_CLASSES = len(CLASS_IDS)

# Nominal Landsat resolution, used only for distance drivers.
#
# Pixel AREA is deliberately not a constant. The Earth Engine exports are in
# EPSG:4326, where a 0.000269 degree pixel at Lahore's latitude is about 29.9 m
# tall but only 25.6 m wide - roughly 766 m2, not the 900 m2 a 30 m grid
# suggests. Multiplying pixel counts by 0.09 ha overstates every area by 17%.
# Real per-pixel areas are computed geodesically in rasters.pixel_area_ha().
PIXEL_SIZE_M = 30.0

# ------------------------------------------------------------- carbon densities
# Mg C/ha, split into the four IPCC pools. Values are (low, best, high) so that
# every carbon figure this project reports carries an uncertainty band rather
# than a single false-precision number.
#
# PROVENANCE / ACTION REQUIRED
# ---------------------------
# These are Tier 1 order-of-magnitude defaults for a warm-temperate/tropical dry
# climate with irrigated annual cropland, chosen to be defensible for Lahore
# District. They are NOT copied from a specific table in the IPCC guidelines and
# MUST be checked against IPCC 2006 Vol.4 (Ch.4 Forest Land, Ch.5 Cropland,
# Ch.8 Settlements) and against Pakistani literature before thesis submission.
# Replace with cited values and record the citation in docs/carbon_sources.md.
#
# Why these differ from the original GEE script: that script assigned the
# Vegetation class 150 Mg C/ha total, which is a closed-forest value. Lahore's
# vegetation class is dominated by irrigated rice-wheat cropland, which is
# harvested annually and therefore stores very little standing biomass. Using a
# forest value inflates both the absolute stock and, more damagingly, the
# vegetation-to-builtup carbon loss by roughly a factor of three.
CARBON_POOLS_MG_C_PER_HA = {
    0: {  # Built-up: street/garden trees over largely sealed soil
        "above": (2.0, 5.0, 9.0),
        "below": (0.5, 1.5, 3.0),
        "soil":  (10.0, 18.0, 30.0),
        "dead":  (0.0, 0.5, 1.5),
    },
    1: {  # Vegetation: irrigated annual cropland with orchard/tree component
        "above": (3.0, 6.0, 14.0),
        "below": (1.0, 2.0, 4.0),
        "soil":  (30.0, 42.0, 55.0),
        "dead":  (0.5, 1.5, 3.0),
    },
    2: {  # Water: sediment carbon only
        "above": (0.0, 0.0, 0.0),
        "below": (0.0, 0.0, 0.0),
        "soil":  (2.0, 5.0, 10.0),
        "dead":  (0.0, 0.0, 0.0),
    },
    3: {  # Bare land: degraded/fallow, sparse cover
        "above": (0.3, 1.0, 2.5),
        "below": (0.1, 0.4, 1.0),
        "soil":  (8.0, 14.0, 22.0),
        "dead":  (0.0, 0.0, 0.5),
    },
}

# The single-value table the original GEE script used, retained so the thesis can
# quantify exactly how much the correction changes the headline number.
LEGACY_TOTAL_CARBON = {0: 28.0, 1: 150.0, 2: 5.0, 3: 18.0}

# Under the three-class scheme the merged non-vegetated class needs one density.
# It is the area-weighted blend of the built-up and bare-land values, using the
# 2023 observed split (77,371 ha built-up against 5,486 ha bare). Bare land is a
# small minority, so the blend sits close to the built-up value - which is the
# honest consequence of merging, not a fudge.
#
# Note this makes absolute carbon totals slightly HIGHER under the three-class
# scheme, because former bare-land pixels inherit a denser value. The two
# schemes are therefore not directly comparable in absolute Mg C; compare
# trajectories and the validation metrics, not the totals.
_W_BUILT, _W_BARE = 0.934, 0.066

if SCHEME == "three":
    _merged = {}
    for pool in ("above", "below", "soil", "dead"):
        b = CARBON_POOLS_MG_C_PER_HA[0][pool]
        r = CARBON_POOLS_MG_C_PER_HA[3][pool]
        _merged[pool] = tuple(_W_BUILT * b[i] + _W_BARE * r[i] for i in range(3))
    CARBON_POOLS_MG_C_PER_HA = {
        0: _merged,
        1: CARBON_POOLS_MG_C_PER_HA[1],
        2: CARBON_POOLS_MG_C_PER_HA[2],
    }
    LEGACY_TOTAL_CARBON = {
        0: _W_BUILT * 28.0 + _W_BARE * 18.0,
        1: 150.0,
        2: 5.0,
    }


def total_carbon(bound: str = "best") -> dict[int, float]:
    """Total carbon density per class, summed over pools. bound in low/best/high."""
    idx = {"low": 0, "best": 1, "high": 2}[bound]
    return {
        cid: sum(pools[p][idx] for p in ("above", "below", "soil", "dead"))
        for cid, pools in CARBON_POOLS_MG_C_PER_HA.items()
    }


NODATA = 255
