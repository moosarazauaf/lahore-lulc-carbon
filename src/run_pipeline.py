"""End-to-end run: transition analysis, back-validation, projection, carbon.

Order matters here. The projection is only produced after the same method has
been tested against a year we can actually check, so the thesis can state how
much the 2033 and 2043 maps are worth rather than presenting them on faith.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

import carbon
import cartography as carto
import figures
import markov
import rasters
import validate
from config import (CLASSES, CLASS_IDS, FIG_DIR, MAP_DIR, OBSERVED_YEARS,
                    PROJECTION_YEARS, TAB_DIR, OUT)
from simulate import TransitionPotential, step

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BANNER = "=" * 78


def header(text):
    print(f"\n{BANNER}\n{text}\n{BANNER}")


def calibrate_and_simulate(maps, mask, cal_from, cal_to, start_year, targets, seed=42):
    """Fit on cal_from -> cal_to, then roll the map forward to each target year."""
    counts = markov.crosstab(maps[cal_from], maps[cal_to], mask)
    P = markov.transition_probabilities(counts)

    print(f"\n  calibrating transition potential on {cal_from} -> {cal_to}")
    model = TransitionPotential(seed=seed).fit(maps[cal_from], maps[cal_to], mask)

    interval = cal_to - cal_from
    current = maps[start_year]
    out = {}
    year = start_year
    for target in targets:
        gap = target - year
        Pstep = P if gap == interval else markov.annualise(P, interval, gap)
        if Pstep is None:
            print(f"  warning: cannot rescale matrix from {interval}y to {gap}y; "
                  f"using the {interval}y matrix unchanged")
            Pstep = P
        print(f"  simulating {year} -> {target}")
        current = step(current, mask, model, Pstep)
        out[target] = current
        year = target
    return out, model, P, counts


def main():
    header("1. LOADING CLASSIFIED MAPS")
    maps, profile, mask = rasters.load_all(OBSERVED_YEARS)
    area = rasters.pixel_area_ha(profile)
    print(f"  pixel area: {area.min() * 1e4:.1f}-{area.max() * 1e4:.1f} m2 "
          f"(a 30 m nominal grid would be 900 m2)")
    print(f"  district area: {area[mask].sum() / 100:,.1f} km2")

    header("2. OBSERVED AREA AND TRANSITIONS")
    areas = {y: markov.area_hectares(maps[y], mask, area) for y in OBSERVED_YEARS}
    print(f"\n{'year':<8}" + "".join(f"{CLASSES[c]:>14}" for c in CLASS_IDS))
    for y in OBSERVED_YEARS:
        print(f"{y:<8}" + "".join(f"{areas[y][c]:>14,.0f}" for c in CLASS_IDS))
    print("  (hectares)")

    matrices = {}
    for a, b in zip(OBSERVED_YEARS, OBSERVED_YEARS[1:]):
        counts = markov.crosstab(maps[a], maps[b], mask)
        ha = markov.crosstab_area(maps[a], maps[b], mask, area)
        matrices[f"{a}_{b}"] = counts.tolist()
        print(f"\n  TRANSITIONS {a} -> {b}")
        print(markov.format_matrix(ha))

    header("3. BACK-VALIDATION (does the method work on a year we can check?)")
    results = []

    sim13, *_ = calibrate_and_simulate(maps, mask, 1993, 2003, 2003, [2013])
    results.append(validate.report(maps[2003], maps[2013], sim13[2013], mask, area,
                                   "calibrated 1993-2003, predicted 2013"))
    print("\n" + validate.per_class_area_error(maps[2013], sim13[2013], mask, area))

    sim23, *_ = calibrate_and_simulate(maps, mask, 2003, 2013, 2013, [2023])
    results.append(validate.report(maps[2013], maps[2023], sim23[2023], mask, area,
                                   "calibrated 2003-2013, predicted 2023"))
    print("\n" + validate.per_class_area_error(maps[2023], sim23[2023], mask, area))

    rasters.write(MAP_DIR / "hindcast_2013.tif", sim13[2013], profile)
    rasters.write(MAP_DIR / "hindcast_2023.tif", sim23[2023], profile)

    best_fom = max(r["figure_of_merit"] for r in results)
    if best_fom <= 0:
        print("\n  STOPPING: the model never beat a no-change prediction.")
        print("  Projecting from a model with zero skill would be dishonest.")
        return

    header("4. PROJECTION TO 2033 AND 2043")
    print("  Calibrated on the most recent observed interval (2013 -> 2023).")
    proj, model, P, _ = calibrate_and_simulate(
        maps, mask, 2013, 2023, 2023, PROJECTION_YEARS)

    print("\n  transition probability matrix, 2013 -> 2023 (per 10-year step)")
    names = [CLASSES[c] for c in CLASS_IDS]
    print(" " * 14 + "".join(f"{n:>13}" for n in names))
    for i, n in enumerate(names):
        print(f"{n:<14}" + "".join(f"{v:>13.4f}" for v in P[i]))

    all_maps = dict(maps)
    all_maps.update(proj)
    for y, arr in proj.items():
        rasters.write(MAP_DIR / f"projected_{y}.tif", arr, profile)
        areas[y] = markov.area_hectares(arr, mask, area)

    all_years = OBSERVED_YEARS + PROJECTION_YEARS
    print(f"\n{'year':<8}" + "".join(f"{CLASSES[c]:>14}" for c in CLASS_IDS))
    for y in all_years:
        tag = "" if y in OBSERVED_YEARS else "  (projected)"
        print(f"{y:<8}" + "".join(f"{areas[y][c]:>14,.0f}" for c in CLASS_IDS) + tag)

    header("5. CARBON STOCK")
    bounds = {y: carbon.stock_with_bounds(all_maps[y], mask, area) for y in all_years}
    legacy = {y: carbon.legacy_stock(all_maps[y], mask, area) for y in all_years}

    print(f"\n{'year':<8}{'low':>16}{'best':>16}{'high':>16}{'original script':>18}")
    for y in all_years:
        b = bounds[y]
        print(f"{y:<8}{b['low_Mg_C']:>16,.0f}{b['best_Mg_C']:>16,.0f}"
              f"{b['high_Mg_C']:>16,.0f}{legacy[y]:>18,.0f}")
    print("  (Mg C)")

    d_best = bounds[2023]["best_Mg_C"] - bounds[1993]["best_Mg_C"]
    d_legacy = legacy[2023] - legacy[1993]
    print(f"\n  1993-2023 carbon change, corrected table: {d_best:>16,.0f} Mg C")
    print(f"  1993-2023 carbon change, original table:  {d_legacy:>16,.0f} Mg C")
    if d_legacy != 0:
        print(f"  the original table overstates the loss by a factor of "
              f"{d_legacy / d_best:.2f}" if d_best != 0 else "")

    for a, b in ((1993, 2023), (2023, 2043)):
        rows = carbon.change_by_transition(all_maps[a], all_maps[b], mask, area)
        print(f"\n  CARBON CHANGE BY TRANSITION, {a} -> {b}")
        print(carbon.format_transition_table(rows))
        figures.transition_carbon_bars(
            rows, f"Carbon change by transition, {a} to {b}",
            f"transition_carbon_{a}_{b}")

    for y in all_years:
        rasters.write(MAP_DIR / f"carbon_density_{y}.tif",
                      np.nan_to_num(carbon.density_map(all_maps[y], mask), nan=-9999),
                      profile, dtype="float32", nodata=-9999)

    header("6. FIGURES")
    print("  " + str(carto.lulc_panel(all_maps, mask, profile, area=area,
                                      observed=OBSERVED_YEARS)))
    for y in all_years:
        print("  " + str(carto.single_map(all_maps[y], mask, profile, y,
                                          area=area,
                                          projected=y not in OBSERVED_YEARS)))
    for a, b in ((1993, 2023), (2023, 2043)):
        print("  " + str(carto.builtup_expansion_map(all_maps[a], all_maps[b],
                                                     mask, profile, a, b, area=area)))
    cvmax = max(float(np.nanmax(carbon.density_map(all_maps[y], mask)))
                for y in all_years)
    for y in (all_years[0], 2023, all_years[-1]):
        print("  " + str(carto.carbon_map(carbon.density_map(all_maps[y], mask),
                                          mask, profile, y, vmax=cvmax, area=area)))
    print("  " + str(figures.area_trajectory(areas, 2023)))
    print("  " + str(figures.carbon_trajectory(bounds, 2023, legacy)))

    summary = {
        "observed_years": OBSERVED_YEARS,
        "projection_years": PROJECTION_YEARS,
        "areas_ha": {str(y): areas[y] for y in all_years},
        "carbon_Mg_C": {str(y): bounds[y] for y in all_years},
        "carbon_legacy_table_Mg_C": {str(y): legacy[y] for y in all_years},
        "transition_counts_px": matrices,
        "district_area_km2": float(area[mask].sum() / 100),
        "validation": results,
        "rf_oob_by_origin_class": model.oob,
        "driver_names": model.names,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n  {OUT / 'summary.json'}")
    header("DONE")


if __name__ == "__main__":
    main()
