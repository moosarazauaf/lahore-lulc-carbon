"""Publication-quality map figures.

Everything here exists because a thesis map has to answer four questions a
matplotlib `imshow` does not: where is this, which way is north, how big is it,
and what is the projection. Panels carry a neatline, a graticule, a scale bar, a
north arrow and a locator inset, and the caption states the CRS and data source.

Aspect ratio matters more than it looks. The rasters are geographic (EPSG:4326),
so plotting degrees on a square grid stretches the district east-west by about
17% at Lahore's latitude. Every axis here is set to 1/cos(latitude) so shapes
are true.
"""
from __future__ import annotations

import json
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon, Rectangle

from config import (CLASS_COLOURS, CLASS_IDS, CLASSES, DATA, FIG_DIR,
                    total_carbon)

INK = "#1c1c1a"
INK_MUTED = "#6b6b66"
NEATLINE = "#3d3d39"
GRATICULE = "#c9c9c4"
SURFACE = "#ffffff"
PAPER = "#fcfcfb"

CMAP = ListedColormap([CLASS_COLOURS[c] for c in CLASS_IDS])

PANEL_LETTERS = "abcdefghijkl"


# ------------------------------------------------------------------ geometry
def extent_of(profile) -> tuple[float, float, float, float]:
    """(left, right, bottom, top) in degrees, for imshow extent."""
    T = profile["transform"]
    left, top = T.c, T.f
    right = left + profile["width"] * T.a
    bottom = top + profile["height"] * T.e
    return left, right, bottom, top


def aspect_of(profile) -> float:
    """Equirectangular aspect correction, 1/cos(mean latitude)."""
    _, _, bottom, top = extent_of(profile)
    return 1.0 / math.cos(math.radians((top + bottom) / 2.0))


def _km_per_degree_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


# ------------------------------------------------------------ map furniture
def neatline(ax):
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(True)
        ax.spines[side].set_color(NEATLINE)
        ax.spines[side].set_linewidth(0.8)


def graticule(ax, profile, step=0.1, labels=("left", "bottom")):
    """Latitude/longitude ticks with degree labels."""
    left, right, bottom, top = extent_of(profile)
    xs = np.arange(math.ceil(left / step) * step, right, step)
    ys = np.arange(math.ceil(bottom / step) * step, top, step)

    ax.set_xticks(xs)
    ax.set_yticks(ys)
    ax.set_xticklabels([f"{v:.1f}°E" for v in xs], fontsize=6.5)
    ax.set_yticklabels([f"{v:.1f}°N" for v in ys], fontsize=6.5)
    ax.tick_params(colors=INK_MUTED, length=2.5, width=0.6, pad=1.5)

    for v in xs:
        ax.axvline(v, color=GRATICULE, lw=0.4, zorder=1.5)
    for v in ys:
        ax.axhline(v, color=GRATICULE, lw=0.4, zorder=1.5)

    if "left" not in labels:
        ax.set_yticklabels([])
    if "bottom" not in labels:
        ax.set_xticklabels([])


def map_furniture(ax, profile, frac=0.26):
    """Scale bar and north arrow inside one white box, anchored to the axes.

    Anchoring in axes coordinates rather than data coordinates matters: the
    district fills most of the frame and its outline moves between epochs, so
    furniture placed in map units lands on top of data in some panels and
    outside the neatline in others. A backing box keeps it legible whatever is
    underneath.
    """
    left, right, bottom, top = extent_of(profile)
    lat = (top + bottom) / 2.0
    span_km = (right - left) * _km_per_degree_lon(lat)

    nice = [1, 2, 5, 10, 20, 25, 50, 100]
    length_km = min(nice, key=lambda v: abs(v - span_km * frac))
    bar_w = (length_km / _km_per_degree_lon(lat)) / (right - left)  # axes frac

    box_w = bar_w + 0.16
    box_h = 0.115
    bx, by = 0.018, 0.018

    ax.add_patch(Rectangle((bx, by), box_w, box_h, transform=ax.transAxes,
                           facecolor=SURFACE, edgecolor=NEATLINE, lw=0.6,
                           zorder=6))

    # scale bar, two alternating segments
    sx = bx + 0.030
    sy = by + 0.030
    sh = 0.020
    for i in range(2):
        ax.add_patch(Rectangle((sx + i * bar_w / 2, sy), bar_w / 2, sh,
                               transform=ax.transAxes,
                               facecolor=INK if i == 0 else SURFACE,
                               edgecolor=INK, lw=0.6, zorder=7))
    for pos, label in ((0.0, "0"), (0.5, f"{length_km // 2}"),
                       (1.0, f"{length_km} km")):
        ax.text(sx + pos * bar_w, sy + sh + 0.012, label,
                transform=ax.transAxes, ha="center", va="bottom",
                fontsize=6.2, color=INK, zorder=7)

    # north arrow at the right end of the same box
    nx = bx + box_w - 0.045
    ax.annotate("", xy=(nx, by + box_h - 0.028), xytext=(nx, by + 0.022),
                xycoords=ax.transAxes, textcoords=ax.transAxes,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.0,
                                mutation_scale=8), zorder=7)
    ax.text(nx, by + box_h - 0.026, "N", transform=ax.transAxes, ha="center",
            va="bottom", fontsize=7, color=INK, weight="bold", zorder=7)


def district_outline(ax, mask, profile, lw=0.7):
    left, right, bottom, top = extent_of(profile)
    ax.contour(mask.astype(float), levels=[0.5], colors=[NEATLINE],
               linewidths=lw, extent=(left, right, bottom, top),
               origin="upper", zorder=5)


def locator_inset(ax, profile, geojson=None):
    """Small Pakistan map with the study area marked."""
    path = geojson or (DATA / "pak_adm1.geojson")
    if not path.exists():
        return None
    try:
        gj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    ins = ax.inset_axes([0.700, 0.640, 0.290, 0.290])
    ins.set_facecolor(SURFACE)

    for feat in gj["features"]:
        geom = feat["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        is_punjab = feat["properties"].get("shapeName") == "Punjab"
        for poly in polys:
            ring = np.asarray(poly[0], dtype=float)
            ins.add_patch(MplPolygon(
                ring, closed=True,
                facecolor="#dfe3df" if not is_punjab else "#c3d4c3",
                edgecolor="#9a9a94", linewidth=0.35, zorder=2))

    left, right, bottom, top = extent_of(profile)
    ins.add_patch(Rectangle((left, bottom), right - left, top - bottom,
                            facecolor="none", edgecolor="#c0392b",
                            linewidth=1.0, zorder=4))
    ins.plot([(left + right) / 2], [(bottom + top) / 2], marker="o", ms=3.0,
             color="#c0392b", zorder=5)

    ins.set_xlim(60.5, 78.0)
    ins.set_ylim(23.0, 37.5)
    ins.set_aspect(1.0 / math.cos(math.radians(30.0)))
    ins.set_xticks([])
    ins.set_yticks([])
    for s in ins.spines.values():
        s.set_color(NEATLINE)
        s.set_linewidth(0.6)
    ins.text(0.04, 0.04, "Pakistan", transform=ins.transAxes, ha="left",
             va="bottom", fontsize=5.8, color=INK_MUTED, zorder=6)
    ins.set_zorder(6)
    ins.patch.set_alpha(1.0)
    return ins


# ---------------------------------------------------------------- LULC panel
def lulc_panel(maps, mask, profile, area=None, observed=(), path=None,
               ncol=3, title="Land use / land cover, Lahore District, Pakistan"):
    """Multi-panel LULC figure with full cartographic furniture."""
    years = sorted(maps)
    n = len(years)
    nrow = int(math.ceil(n / ncol))
    asp = aspect_of(profile)
    left, right, bottom, top = extent_of(profile)

    fig, axes = plt.subplots(nrow, ncol, figsize=(4.1 * ncol, 4.0 * nrow),
                             facecolor=PAPER)
    axes = np.atleast_1d(axes).ravel()

    for i, (ax, y) in enumerate(zip(axes, years)):
        disp = np.ma.masked_where(~mask, maps[y])
        ax.set_facecolor(SURFACE)
        ax.imshow(disp, cmap=CMAP, vmin=0, vmax=len(CLASS_IDS) - 1,
                  interpolation="nearest", extent=(left, right, bottom, top),
                  origin="upper", zorder=2)
        ax.set_xlim(left, right)
        ax.set_ylim(bottom, top)
        ax.set_aspect(asp)

        district_outline(ax, mask, profile)
        graticule(ax, profile,
                  labels=(("left",) if i % ncol == 0 else ())
                         + (("bottom",) if i >= n - ncol else ()))
        neatline(ax)

        tag = "" if (not observed or y in observed) else "  (projected)"
        ax.set_title(f"({PANEL_LETTERS[i]})  {y}{tag}", color=INK,
                     fontsize=10, pad=5, loc="left")

        if i == 0:
            map_furniture(ax, profile)
            locator_inset(ax, profile)

    for ax in axes[n:]:
        ax.axis("off")

    handles = [Rectangle((0, 0), 1, 1, fc=CLASS_COLOURS[c], ec=NEATLINE, lw=0.4)
               for c in CLASS_IDS]
    # No areas in the shared legend: it sits under six panels with different
    # class shares, so a single percentage would be read as applying to all of
    # them. Per-panel areas belong on the single-year maps and in
    # outputs/tables/area_trajectory.csv.
    labels = [CLASSES[c] for c in CLASS_IDS]

    fig.legend(handles, labels, loc="lower center", ncol=len(CLASS_IDS),
               frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.035))
    fig.suptitle(title, y=0.975, fontsize=12.5, color=INK)

    fig.text(0.5, 0.005,
             "Geographic coordinates, WGS 84 (EPSG:4326); axes corrected for "
             "latitude. Cell size 30 m.\nClassified from Landsat 5/7/8/9 "
             "surface reflectance by Random Forest. Scale bar and north arrow "
             "in panel (a) apply to all panels.",
             ha="center", va="bottom", fontsize=7, color=INK_MUTED)

    fig.subplots_adjust(bottom=0.10, top=0.93, wspace=0.06, hspace=0.02)
    path = path or FIG_DIR / "lulc_panel.png"
    fig.savefig(path, dpi=300, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    return path


# --------------------------------------------------------------- single maps
def single_map(lulc, mask, profile, year, path=None, projected=False,
               area=None):
    """One year at full page width, for a thesis figure of its own."""
    asp = aspect_of(profile)
    left, right, bottom, top = extent_of(profile)

    fig, ax = plt.subplots(figsize=(7.0, 6.6), facecolor=PAPER)
    ax.set_facecolor(SURFACE)
    disp = np.ma.masked_where(~mask, lulc)
    ax.imshow(disp, cmap=CMAP, vmin=0, vmax=len(CLASS_IDS) - 1,
              interpolation="nearest", extent=(left, right, bottom, top),
              origin="upper", zorder=2)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect(asp)

    district_outline(ax, mask, profile)
    graticule(ax, profile)
    neatline(ax)
    map_furniture(ax, profile)
    locator_inset(ax, profile)

    tag = " (projected)" if projected else ""
    ax.set_title(f"Land use / land cover, Lahore District, {year}{tag}",
                 fontsize=12, color=INK, pad=8, loc="left")

    handles = [Rectangle((0, 0), 1, 1, fc=CLASS_COLOURS[c], ec=NEATLINE, lw=0.4)
               for c in CLASS_IDS]
    if area is not None:
        tot = float(area[mask].sum())
        labels = []
        for c in CLASS_IDS:
            ha = float(area[mask][lulc[mask] == c].sum())
            labels.append(f"{CLASSES[c]}   {ha:,.0f} ha  ({100 * ha / tot:.1f}%)")
    else:
        labels = [CLASSES[c] for c in CLASS_IDS]

    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.005, 0.995),
              frameon=True, facecolor=SURFACE, edgecolor=NEATLINE,
              fontsize=7.5, framealpha=0.92, borderpad=0.6)

    fig.text(0.5, 0.012,
             "Geographic coordinates, WGS 84 (EPSG:4326); axes corrected for "
             "latitude. Cell size 30 m.",
             ha="center", va="bottom", fontsize=7, color=INK_MUTED)
    path = path or FIG_DIR / f"lulc_{year}.png"
    fig.savefig(path, dpi=300, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- change map
def builtup_expansion_map(t0map, t1map, mask, profile, y0, y1, path=None):
    """Where built-up appeared, persisted, and was lost between two dates."""
    asp = aspect_of(profile)
    left, right, bottom, top = extent_of(profile)

    b0 = (t0map == 0) & mask
    b1 = (t1map == 0) & mask

    cat = np.full(t0map.shape, np.nan)
    cat[mask & ~b0 & ~b1] = 0     # never built
    cat[b0 & b1] = 1              # persistent
    cat[~b0 & b1] = 2             # new
    cat[b0 & ~b1] = 3             # lost

    colours = ["#eceee9", "#7f8c8d", "#c0392b", "#2874a6"]
    names = [f"Not built-up in {y0} or {y1}", f"Built-up in both",
             f"New built-up, {y0}–{y1}", f"Built-up lost, {y0}–{y1}"]

    fig, ax = plt.subplots(figsize=(7.0, 6.6), facecolor=PAPER)
    ax.set_facecolor(SURFACE)
    ax.imshow(np.ma.masked_invalid(cat), cmap=ListedColormap(colours),
              vmin=0, vmax=3, interpolation="nearest",
              extent=(left, right, bottom, top), origin="upper", zorder=2)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect(asp)

    district_outline(ax, mask, profile)
    graticule(ax, profile)
    neatline(ax)
    map_furniture(ax, profile)
    locator_inset(ax, profile)

    ax.set_title(f"Built-up expansion, Lahore District, {y0}–{y1}",
                 fontsize=12, color=INK, pad=8, loc="left")
    handles = [Rectangle((0, 0), 1, 1, fc=c, ec=NEATLINE, lw=0.4) for c in colours]
    ax.legend(handles, names, loc="upper left", bbox_to_anchor=(0.005, 0.995),
              frameon=True, facecolor=SURFACE, edgecolor=NEATLINE,
              fontsize=7.5, framealpha=0.92, borderpad=0.6)

    fig.text(0.5, 0.012,
             "Geographic coordinates, WGS 84 (EPSG:4326); axes corrected for "
             "latitude. Cell size 30 m.\n\"Built-up lost\" is largely "
             "classification instability between epochs, not genuine "
             "de-urbanisation; see docs/results.md.",
             ha="center", va="bottom", fontsize=7, color=INK_MUTED)
    path = path or FIG_DIR / f"builtup_expansion_{y0}_{y1}.png"
    fig.savefig(path, dpi=300, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- carbon map
def carbon_map(density, mask, profile, year, path=None, vmax=None):
    """Carbon density surface. Sequential single-hue ramp, light to dark."""
    asp = aspect_of(profile)
    left, right, bottom, top = extent_of(profile)

    ramp = ListedColormap(["#f4f7f2", "#dbe8d4", "#b9d6ae", "#8fbf85",
                           "#63a662", "#3d8c47", "#256d34", "#134f24"])
    vmax = vmax or float(np.nanmax(density[mask]))

    fig, ax = plt.subplots(figsize=(7.0, 6.6), facecolor=PAPER)
    ax.set_facecolor(SURFACE)
    im = ax.imshow(np.ma.masked_where(~mask, density), cmap=ramp,
                   norm=Normalize(0, vmax), interpolation="nearest",
                   extent=(left, right, bottom, top), origin="upper", zorder=2)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect(asp)

    district_outline(ax, mask, profile)
    graticule(ax, profile)
    neatline(ax)
    map_furniture(ax, profile)

    ax.set_title(f"Carbon density, Lahore District, {year}", fontsize=12,
                 color=INK, pad=8, loc="left")

    cb = fig.colorbar(im, ax=ax, fraction=0.036, pad=0.02)
    cb.set_label("Mg C ha⁻¹", fontsize=8, color=INK)

    # Density is assigned per class, so only four values ever occur. Ticking
    # the bar at exactly those values stops it reading as a continuous field
    # that was measured rather than assigned.
    table = total_carbon("best")
    ticks = sorted(set(table.values()))
    cb.set_ticks(ticks)
    lookup = {}
    for cid, v in table.items():
        lookup.setdefault(v, []).append(CLASSES[cid])
    cb.set_ticklabels([f"{v:.1f}  {' / '.join(lookup[v])}" for v in ticks])
    cb.ax.tick_params(labelsize=6.5, color=INK_MUTED, labelcolor=INK)
    cb.outline.set_edgecolor(NEATLINE)
    cb.outline.set_linewidth(0.6)

    fig.text(0.5, 0.012,
             "Carbon density assigned per land-cover class (IPCC Tier 1 "
             "placeholders; see docs/carbon_sources.md).\nThe surface is "
             "therefore piecewise constant by class, not a measured "
             "continuous field.",
             ha="center", va="bottom", fontsize=7, color=INK_MUTED)
    path = path or FIG_DIR / f"carbon_density_{year}.png"
    fig.savefig(path, dpi=300, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    return path
