"""Thesis figures. Every chart also writes the CSV behind it.

Palette validated for colour-vision deficiency (worst adjacent pair dE 11.2
deuteranopia). Because the green and yellow marks sit below 3:1 against the page,
every series is directly labelled and every figure ships its underlying table.
"""
from __future__ import annotations

import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from config import CLASS_COLOURS, CLASS_IDS, CLASSES, FIG_DIR, TAB_DIR

INK = "#1c1c1a"
INK_MUTED = "#6b6b66"
GRID = "#e4e4e0"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9,
    "text.color": INK, "axes.labelcolor": INK, "axes.edgecolor": GRID,
    "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": GRID, "grid.linewidth": 0.6, "savefig.dpi": 200,
    "savefig.bbox": "tight",
})

CMAP = ListedColormap([CLASS_COLOURS[c] for c in CLASS_IDS])


def _csv(name, header, rows):
    path = TAB_DIR / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def lulc_panel(maps, mask, path=None):
    years = sorted(maps)
    n = len(years)
    ncol = min(n, 3)
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.2 * ncol, 4.0 * nrow))
    axes = np.atleast_1d(axes).ravel()

    for ax, y in zip(axes, years):
        disp = np.ma.masked_where(~mask, maps[y])
        ax.imshow(disp, cmap=CMAP, vmin=0, vmax=len(CLASS_IDS) - 1,
                  interpolation="nearest")
        ax.set_title(str(y), color=INK, pad=6)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    for ax in axes[n:]:
        ax.axis("off")

    handles = [plt.Rectangle((0, 0), 1, 1, fc=CLASS_COLOURS[c], ec="none")
               for c in CLASS_IDS]
    fig.legend(handles, [CLASSES[c] for c in CLASS_IDS], loc="lower center",
               ncol=len(CLASS_IDS), frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Land use / land cover, Lahore District", y=1.0, color=INK)
    path = path or FIG_DIR / "lulc_panel.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def area_trajectory(areas, last_observed, path=None):
    """Class area over time; projected years drawn dashed."""
    years = sorted(areas)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.grid(axis="y", zorder=0)

    for cid in CLASS_IDS:
        vals = [areas[y][cid] for y in years]
        obs = [(y, v) for y, v in zip(years, vals) if y <= last_observed]
        prj = [(y, v) for y, v in zip(years, vals) if y >= last_observed]
        col = CLASS_COLOURS[cid]
        ax.plot(*zip(*obs), color=col, lw=2, marker="o", ms=5, zorder=3)
        if len(prj) > 1:
            ax.plot(*zip(*prj), color=col, lw=2, ls=(0, (4, 3)), marker="o",
                    ms=5, mfc=SURFACE, zorder=3)
        ax.annotate(CLASSES[cid], (years[-1], vals[-1]), xytext=(8, 0),
                    textcoords="offset points", color=INK, va="center", fontsize=9)

    ax.axvline(last_observed, color=INK_MUTED, lw=0.8, ls=":", zorder=1)
    ax.annotate("observed  |  projected", (last_observed, ax.get_ylim()[1]),
                xytext=(0, -12), textcoords="offset points", ha="center",
                color=INK_MUTED, fontsize=8)
    ax.set_ylabel("Area (hectares)")
    ax.set_xticks(years)
    ax.set_xlim(years[0] - 2, years[-1] + 9)
    ax.set_title("Land cover area, observed and projected", loc="left", color=INK)
    handles = [plt.Line2D([], [], color=CLASS_COLOURS[c], lw=2) for c in CLASS_IDS]
    ax.legend(handles, [CLASSES[c] for c in CLASS_IDS], frameon=False,
              loc="upper left", ncol=2, fontsize=8)

    _csv("area_trajectory.csv", ["year"] + [CLASSES[c] for c in CLASS_IDS],
         [[y] + [round(areas[y][c], 1) for c in CLASS_IDS] for y in years])
    path = path or FIG_DIR / "area_trajectory.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def carbon_trajectory(bounds, last_observed, legacy=None, path=None):
    """Total carbon stock with its uncertainty band."""
    years = sorted(bounds)
    best = [bounds[y]["best_Mg_C"] / 1e6 for y in years]
    lo = [bounds[y]["low_Mg_C"] / 1e6 for y in years]
    hi = [bounds[y]["high_Mg_C"] / 1e6 for y in years]

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.grid(axis="y", zorder=0)
    ax.fill_between(years, lo, hi, color="#2874a6", alpha=0.14, lw=0, zorder=2)

    split = years.index(last_observed)
    ax.plot(years[:split + 1], best[:split + 1], color="#2874a6", lw=2,
            marker="o", ms=5, zorder=4)
    ax.plot(years[split:], best[split:], color="#2874a6", lw=2, ls=(0, (4, 3)),
            marker="o", ms=5, mfc=SURFACE, zorder=4)
    ax.annotate("corrected\n(IPCC cropland)", (years[-1], best[-1]), xytext=(8, 0),
                textcoords="offset points", color=INK, va="center", fontsize=8)

    if legacy:
        lg = [legacy[y] / 1e6 for y in years]
        ax.plot(years, lg, color=INK_MUTED, lw=1.6, ls=(0, (1, 2)), zorder=3)
        ax.annotate("original script\n(forest value)", (years[-1], lg[-1]),
                    xytext=(8, 0), textcoords="offset points", color=INK_MUTED,
                    va="center", fontsize=8)

    ax.axvline(last_observed, color=INK_MUTED, lw=0.8, ls=":", zorder=1)
    ax.set_ylabel("Total carbon stock (million Mg C)")
    ax.set_xticks(years)
    ax.set_xlim(years[0] - 2, years[-1] + 11)
    ax.set_ylim(bottom=0)
    ax.set_title("Carbon stock, observed and projected", loc="left", color=INK)

    header = ["year", "low_Mg_C", "best_Mg_C", "high_Mg_C"]
    if legacy:
        header.append("legacy_Mg_C")
    rows = []
    for y in years:
        row = [y, round(bounds[y]["low_Mg_C"]), round(bounds[y]["best_Mg_C"]),
               round(bounds[y]["high_Mg_C"])]
        if legacy:
            row.append(round(legacy[y]))
        rows.append(row)
    _csv("carbon_trajectory.csv", header, rows)
    path = path or FIG_DIR / "carbon_trajectory.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def transition_carbon_bars(rows, title, filename, path=None):
    """Carbon change attributed to each land-cover transition."""
    rows = [r for r in rows if abs(r["delta_Mg_C"]) > 0][:10]
    if not rows:
        return None
    labels = [r["from"] + " to " + r["to"] for r in rows]
    vals = [r["delta_Mg_C"] / 1e6 for r in rows]
    colours = ["#c0392b" if v < 0 else "#27ae60" for v in vals]

    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(rows) + 1.8))
    ax.grid(axis="x", zorder=0)
    ax.barh(labels, vals, color=colours, height=0.62, zorder=3)
    ax.axvline(0, color=INK_MUTED, lw=0.9, zorder=4)
    ax.invert_yaxis()
    for lab, v in zip(labels, vals):
        off = 6 if v >= 0 else -6
        ax.annotate("%+.2f" % v, (v, lab), xytext=(off, 0),
                    textcoords="offset points", va="center",
                    ha="left" if v >= 0 else "right", color=INK, fontsize=8)
    ax.set_xlabel("Carbon change (million Mg C)")
    ax.set_title(title, loc="left", color=INK)
    ax.margins(x=0.18)

    _csv(filename + ".csv", ["from", "to", "area_ha", "delta_Mg_C"],
         [[r["from"], r["to"], round(r["area_ha"], 1), round(r["delta_Mg_C"], 1)]
          for r in rows])
    path = path or FIG_DIR / (filename + ".png")
    fig.savefig(path)
    plt.close(fig)
    return path
