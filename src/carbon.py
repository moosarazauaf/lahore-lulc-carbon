"""Carbon stock accounting from LULC maps, with an explicit uncertainty band."""
from __future__ import annotations

import numpy as np

from config import (CLASS_IDS, CLASSES, LEGACY_TOTAL_CARBON, N_CLASSES,
                    PIXEL_AREA_HA, total_carbon)


def density_map(lulc: np.ndarray, mask: np.ndarray, bound: str = "best") -> np.ndarray:
    """Per-pixel carbon density, Mg C/ha."""
    table = total_carbon(bound)
    out = np.full(lulc.shape, np.nan, dtype="float32")
    for cid in CLASS_IDS:
        out[mask & (lulc == cid)] = table[cid]
    return out


def stock(lulc: np.ndarray, mask: np.ndarray, bound: str = "best") -> dict:
    """Total carbon stock in Mg C, and the per-class breakdown."""
    table = total_carbon(bound)
    counts = np.bincount(lulc[mask].astype(int), minlength=N_CLASSES)
    per_class = {c: float(counts[c] * PIXEL_AREA_HA * table[c]) for c in CLASS_IDS}
    return {"total_Mg_C": float(sum(per_class.values())), "per_class_Mg_C": per_class,
            "area_ha": {c: float(counts[c] * PIXEL_AREA_HA) for c in CLASS_IDS}}


def stock_with_bounds(lulc, mask) -> dict:
    lo = stock(lulc, mask, "low")["total_Mg_C"]
    be = stock(lulc, mask, "best")["total_Mg_C"]
    hi = stock(lulc, mask, "high")["total_Mg_C"]
    return {"low_Mg_C": lo, "best_Mg_C": be, "high_Mg_C": hi}


def legacy_stock(lulc, mask) -> float:
    """Stock using the original GEE script's single-value table.

    Kept so the thesis can state exactly how much the corrected cropland carbon
    density changes the result, rather than quietly replacing one number with
    another.
    """
    counts = np.bincount(lulc[mask].astype(int), minlength=N_CLASSES)
    return float(sum(counts[c] * PIXEL_AREA_HA * LEGACY_TOTAL_CARBON[c] for c in CLASS_IDS))


def change_by_transition(t0, t1, mask, bound: str = "best") -> list[dict]:
    """Attribute carbon change to each from-to transition, largest loss first."""
    table = total_carbon(bound)
    a, b = t0[mask].astype(int), t1[mask].astype(int)
    rows = []
    for i in CLASS_IDS:
        for j in CLASS_IDS:
            n = int(((a == i) & (b == j)).sum())
            if n == 0 or i == j:
                continue
            area = n * PIXEL_AREA_HA
            rows.append({
                "from": CLASSES[i], "to": CLASSES[j], "area_ha": area,
                "delta_Mg_C": area * (table[j] - table[i]),
            })
    return sorted(rows, key=lambda r: r["delta_Mg_C"])


def format_transition_table(rows) -> str:
    lines = [f"{'from':<14}{'to':<14}{'area ha':>12}{'ΔMg C':>16}"]
    for r in rows:
        lines.append(f"{r['from']:<14}{r['to']:<14}{r['area_ha']:>12,.0f}{r['delta_Mg_C']:>16,.0f}")
    net = sum(r["delta_Mg_C"] for r in rows)
    lines.append(f"{'NET':<28}{'':>12}{net:>16,.0f}")
    return "\n".join(lines)
