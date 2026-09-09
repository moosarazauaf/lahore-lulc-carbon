"""Carbon stock accounting from LULC maps, with an explicit uncertainty band."""
from __future__ import annotations

import numpy as np

from config import (CLASS_IDS, CLASSES, LEGACY_TOTAL_CARBON, N_CLASSES,
                    total_carbon)


def density_map(lulc: np.ndarray, mask: np.ndarray, bound: str = "best") -> np.ndarray:
    """Per-pixel carbon density, Mg C/ha."""
    table = total_carbon(bound)
    out = np.full(lulc.shape, np.nan, dtype="float32")
    for cid in CLASS_IDS:
        out[mask & (lulc == cid)] = table[cid]
    return out


def stock(lulc: np.ndarray, mask: np.ndarray, area: np.ndarray,
          bound: str = "best") -> dict:
    """Total carbon stock in Mg C, and the per-class breakdown."""
    table = total_carbon(bound)
    ha = np.bincount(lulc[mask].astype(int), weights=area[mask], minlength=N_CLASSES)
    per_class = {c: float(ha[c] * table[c]) for c in CLASS_IDS}
    return {"total_Mg_C": float(sum(per_class.values())), "per_class_Mg_C": per_class,
            "area_ha": {c: float(ha[c]) for c in CLASS_IDS}}


def stock_with_bounds(lulc, mask, area) -> dict:
    return {
        "low_Mg_C": stock(lulc, mask, area, "low")["total_Mg_C"],
        "best_Mg_C": stock(lulc, mask, area, "best")["total_Mg_C"],
        "high_Mg_C": stock(lulc, mask, area, "high")["total_Mg_C"],
    }


def legacy_stock(lulc, mask, area) -> float:
    """Stock using the original GEE script's single-value table.

    Kept so the thesis can state exactly how much the corrected cropland carbon
    density changes the result, rather than quietly replacing one number with
    another.
    """
    ha = np.bincount(lulc[mask].astype(int), weights=area[mask], minlength=N_CLASSES)
    return float(sum(ha[c] * LEGACY_TOTAL_CARBON[c] for c in CLASS_IDS))


def change_by_transition(t0, t1, mask, area, bound: str = "best") -> list[dict]:
    """Attribute carbon change to each from-to transition, largest loss first."""
    table = total_carbon(bound)
    a, b = t0[mask].astype(int), t1[mask].astype(int)
    rows = []
    for i in CLASS_IDS:
        for j in CLASS_IDS:
            sel = (a == i) & (b == j)
            if i == j or not sel.any():
                continue
            ha = float(area[mask][sel].sum())
            rows.append({
                "from": CLASSES[i], "to": CLASSES[j], "area_ha": ha,
                "delta_Mg_C": ha * (table[j] - table[i]),
            })
    return sorted(rows, key=lambda r: r["delta_Mg_C"])


def format_transition_table(rows) -> str:
    lines = [f"{'from':<14}{'to':<14}{'area ha':>12}{'delta Mg C':>16}"]
    for r in rows:
        lines.append(f"{r['from']:<14}{r['to']:<14}{r['area_ha']:>12,.0f}{r['delta_Mg_C']:>16,.0f}")
    net = sum(r["delta_Mg_C"] for r in rows)
    lines.append(f"{'NET':<28}{'':>12}{net:>16,.0f}")
    return "\n".join(lines)
