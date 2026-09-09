"""Publication-quality map figures.

Layout principle: nothing overlaps the map. Legend, locator inset, scale bar and
north arrow live in dedicated margins created by the figure's grid, not floated
on top of the data in boxes. A box drawn over a map always covers something, and
which thing it covers changes between epochs, which is exactly what a reader
should never have to work around.

Aspect ratio matters more than it looks. The rasters are geographic (EPSG:4326),
so plotting degrees on a square grid stretches the district east-west by about
17% at Lahore's latitude. Every map axis is set to 1/cos(latitude) so shapes are
true.

The scale bar always lives in a strip that shares its x-limits with the map axis
above it, so its length is exact in degrees rather than inferred from figure
geometry.
"""
from __future__ import annotations

import json
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Polygon as MplPolygon, Rectangle

from config import (CLASS_COLOURS, CLASS_IDS, CLASSES, DATA, FIG_DIR,
                    total_carbon)

INK = "#1c1c1a"
INK_MUTED = "#6b6b66"
NEATLINE = "#3d3d39"
GRATICULE = "#d4d4cf"
SURFACE = "#ffffff"
PAPER = "#fcfcfb"

CMAP = ListedColormap([CLASS_COLOURS[c] for c in CLASS_IDS])
PANEL_LETTERS = "abcdefghijkl"

CAPTION_CRS = ("Geographic coordinates, WGS 84 (EPSG:4326); axis aspect "
               "corrected for latitude. Cell size 30 m.")


# ------------------------------------------------------------------ geometry
def extent_of(profile):
    """(left, right, bottom, top) in degrees, for imshow extent."""
    T = profile["transform"]
    left, top = T.c, T.f
    right = left + profile["width"] * T.a
    bottom = top + profile["height"] * T.e
    return left, right, bottom, top


def aspect_of(profile) -> float:
    _, _, bottom, top = extent_of(profile)
    return 1.0 / math.cos(math.radians((top + bottom) / 2.0))


def _km_per_degree_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def _nice_bar_km(profile, frac=0.28) -> int:
    left, right, bottom, top = extent_of(profile)
    span_km = (right - left) * _km_per_degree_lon((top + bottom) / 2.0)
    return min([1, 2, 5, 10, 20, 25, 50, 100],
               key=lambda v: abs(v - span_km * frac))


# ------------------------------------------------------------- map decoration
def neatline(ax):
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(True)
        ax.spines[side].set_color(NEATLINE)
        ax.spines[side].set_linewidth(0.8)


def graticule(ax, profile, step=0.1, left_labels=True, bottom_labels=True):
    lo, hi, bottom, top = extent_of(profile)
    xs = np.arange(math.ceil(lo / step) * step, hi, step)
    ys = np.arange(math.ceil(bottom / step) * step, top, step)

    ax.set_xticks(xs)
    ax.set_yticks(ys)
    ax.set_xticklabels([f"{v:.1f}°E" for v in xs] if bottom_labels else [],
                       fontsize=6.5)
    ax.set_yticklabels([f"{v:.1f}°N" for v in ys] if left_labels else [],
                       fontsize=6.5)
    ax.tick_params(colors=INK_MUTED, length=2.5, width=0.6, pad=1.5)

    for v in xs:
        ax.axvline(v, color=GRATICULE, lw=0.4, zorder=1.5)
    for v in ys:
        ax.axhline(v, color=GRATICULE, lw=0.4, zorder=1.5)


def district_outline(ax, mask, profile, lw=0.7):
    lo, hi, bottom, top = extent_of(profile)
    ax.contour(mask.astype(float), levels=[0.5], colors=[NEATLINE],
               linewidths=lw, extent=(lo, hi, bottom, top), origin="upper",
               zorder=5)


def _setup_map_axes(ax, profile):
    lo, hi, bottom, top = extent_of(profile)
    ax.set_facecolor(SURFACE)
    ax.set_xlim(lo, hi)
    ax.set_ylim(bottom, top)
    ax.set_aspect(aspect_of(profile))


def _draw_raster(ax, arr, profile, cmap, vmin, vmax):
    lo, hi, bottom, top = extent_of(profile)
    ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest",
              extent=(lo, hi, bottom, top), origin="upper", zorder=2)


# ----------------------------------------------------------------- furniture
def scale_strip(ax, profile, frac=0.28):
    """Scale bar in its own axis, sharing x-limits with the map above it.

    Sharing the x-limits is what makes the bar exact: its length is set in
    degrees, the same units the map is drawn in, so no figure-geometry
    arithmetic can drift it out of true.
    """
    lo, hi, bottom, top = extent_of(profile)
    km = _nice_bar_km(profile, frac)
    deg = km / _km_per_degree_lon((top + bottom) / 2.0)

    ax.set_xlim(lo, hi)
    ax.set_ylim(0, 1)
    ax.axis("off")

    y0, h = 0.08, 0.30
    for i in range(2):
        ax.add_patch(Rectangle((lo + i * deg / 2, y0), deg / 2, h,
                               facecolor=INK if i == 0 else SURFACE,
                               edgecolor=INK, lw=0.6, zorder=3))
    for pos, label in ((0.0, "0"), (0.5, f"{km // 2}"), (1.0, f"{km} km")):
        ax.text(lo + pos * deg, y0 + h + 0.12, label, ha="center", va="bottom",
                fontsize=6.5, color=INK)


def north_arrow(ax, x=0.5, y=0.0, size=0.30):
    """North arrow in the axes-fraction space of a furniture axis."""
    ax.annotate("", xy=(x, y + size), xytext=(x, y),
                xycoords=ax.transAxes, textcoords=ax.transAxes,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.1,
                                mutation_scale=10), zorder=4)
    ax.text(x, y + size + 0.015, "N", transform=ax.transAxes, ha="center",
            va="bottom", fontsize=8, color=INK, weight="bold")


def locator_axes(ax_host, profile, rect, geojson=None):
    """Pakistan locator drawn inside a furniture axis, never over the map."""
    path = geojson or (DATA / "pak_adm1.geojson")
    if not path.exists():
        return None
    try:
        gj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    ins = ax_host.inset_axes(rect)
    ins.set_facecolor(SURFACE)
    for feat in gj["features"]:
        geom = feat["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        punjab = feat["properties"].get("shapeName") == "Punjab"
        for poly in polys:
            ins.add_patch(MplPolygon(
                np.asarray(poly[0], dtype=float), closed=True,
                facecolor="#c3d4c3" if punjab else "#e2e5e1",
                edgecolor="#9a9a94", linewidth=0.35, zorder=2))

    lo, hi, bottom, top = extent_of(profile)
    ins.add_patch(Rectangle((lo, bottom), hi - lo, top - bottom,
                            facecolor="none", edgecolor="#c0392b", lw=1.1,
                            zorder=4))
    ins.set_xlim(60.5, 78.0)
    ins.set_ylim(23.0, 37.5)
    ins.set_aspect(1.0 / math.cos(math.radians(30.0)))
    ins.set_xticks([])
    ins.set_yticks([])
    for s in ins.spines.values():
        s.set_color(NEATLINE)
        s.set_linewidth(0.6)
    return ins


def _class_legend_labels(lulc, mask, area):
    if area is None:
        return [CLASSES[c] for c in CLASS_IDS]
    tot = float(area[mask].sum())
    out = []
    for c in CLASS_IDS:
        ha = float(area[mask][lulc[mask] == c].sum())
        out.append(f"{CLASSES[c]}\n{ha:,.0f} ha  ({100 * ha / tot:.1f}%)")
    return out


def _swatches(colours):
    return [Rectangle((0, 0), 1, 1, fc=c, ec=NEATLINE, lw=0.4) for c in colours]


# ------------------------------------------------------- single-map scaffold
def _single_figure(profile, title, caption, figsize=(9.4, 6.6)):
    """Map axis, scale-bar strip beneath it, furniture column to the right."""
    fig = plt.figure(figsize=figsize, facecolor=PAPER)
    gs = fig.add_gridspec(
        2, 2, width_ratios=[1.0, 0.30], height_ratios=[1.0, 0.075],
        wspace=0.04, hspace=0.06,
        left=0.062, right=0.985, top=0.920, bottom=0.105)

    ax = fig.add_subplot(gs[0, 0])
    ax_scale = fig.add_subplot(gs[1, 0])
    ax_side = fig.add_subplot(gs[:, 1])
    ax_side.axis("off")

    _setup_map_axes(ax, profile)
    graticule(ax, profile)
    neatline(ax)
    scale_strip(ax_scale, profile)

    fig.suptitle(title, x=0.062, y=0.972, ha="left", fontsize=13, color=INK)
    fig.text(0.062, 0.018, caption, ha="left", va="bottom", fontsize=7,
             color=INK_MUTED, linespacing=1.55)
    return fig, ax, ax_scale, ax_side


def _finish_side(ax_side, profile, handles, labels, legend_title=None):
    """Stack legend, locator and north arrow down the furniture column."""
    leg = ax_side.legend(handles, labels, loc="upper left",
                         bbox_to_anchor=(0.0, 1.0), frameon=False,
                         fontsize=7.5, handlelength=1.5, handleheight=1.2,
                         labelspacing=1.0, borderpad=0.0, title=legend_title)
    if legend_title:
        leg.get_title().set_fontsize(8.5)
        leg.get_title().set_color(INK)
        leg.get_title().set_ha("left")
    locator_axes(ax_side, profile, [0.0, 0.235, 0.92, 0.185])
    north_arrow(ax_side, x=0.46, y=0.075, size=0.085)


# ---------------------------------------------------------------- LULC panel
def lulc_panel(maps, mask, profile, area=None, observed=(), path=None,
               ncol=3, title="Land use / land cover, Lahore District, Pakistan"):
    """Multi-panel LULC figure. Furniture sits in a strip below the panels."""
    years = sorted(maps)
    n = len(years)
    nrow = int(math.ceil(n / ncol))

    fig = plt.figure(figsize=(4.15 * ncol, 3.9 * nrow + 1.25), facecolor=PAPER)
    gs = fig.add_gridspec(
        nrow + 2, ncol,
        height_ratios=[1.0] * nrow + [0.05, 0.20],
        wspace=0.08, hspace=0.12,
        left=0.052, right=0.986, top=0.928, bottom=0.075)

    for i, y in enumerate(years):
        ax = fig.add_subplot(gs[i // ncol, i % ncol])
        _setup_map_axes(ax, profile)
        _draw_raster(ax, np.ma.masked_where(~mask, maps[y]), profile, CMAP,
                     0, len(CLASS_IDS) - 1)
        district_outline(ax, mask, profile)
        graticule(ax, profile, left_labels=(i % ncol == 0),
                  bottom_labels=(i >= n - ncol))
        neatline(ax)
        tag = "" if (not observed or y in observed) else "  (projected)"
        ax.set_title(f"({PANEL_LETTERS[i]})  {y}{tag}", color=INK, fontsize=10,
                     pad=5, loc="left")

    # Scale bar under the first column only, so it shares that panel's x-limits
    # and is exact rather than inferred from figure geometry.
    scale_strip(fig.add_subplot(gs[nrow, 0]), profile)

    ax_bar = fig.add_subplot(gs[nrow + 1, :])
    ax_bar.axis("off")
    ax_bar.set_xlim(0, 1)
    ax_bar.set_ylim(0, 1)
    ax_bar.legend(_swatches([CLASS_COLOURS[c] for c in CLASS_IDS]),
                  [CLASSES[c] for c in CLASS_IDS],
                  loc="upper left", bbox_to_anchor=(0.0, 1.05), ncol=4,
                  frameon=False, fontsize=9.5, handlelength=1.6,
                  columnspacing=2.4)
    locator_axes(ax_bar, profile, [0.860, 0.02, 0.070, 1.02])
    north_arrow(ax_bar, x=0.968, y=0.28, size=0.42)

    fig.suptitle(title, x=0.052, y=0.972, ha="left", fontsize=13.5, color=INK)
    fig.text(0.052, 0.008,
             CAPTION_CRS + "  Classified from Landsat 5/7/8/9 surface "
             "reflectance by Random Forest.\nAll panels share one extent; the "
             "scale bar and north arrow apply to every panel.",
             ha="left", va="bottom", fontsize=7, color=INK_MUTED,
             linespacing=1.55)

    path = path or FIG_DIR / "lulc_panel.png"
    fig.savefig(path, dpi=300, facecolor=PAPER)
    plt.close(fig)
    return path


# --------------------------------------------------------------- single maps
def single_map(lulc, mask, profile, year, path=None, projected=False,
               area=None):
    tag = " (projected)" if projected else ""
    fig, ax, _, ax_side = _single_figure(
        profile, f"Land use / land cover, Lahore District, {year}{tag}",
        CAPTION_CRS)

    _draw_raster(ax, np.ma.masked_where(~mask, lulc), profile, CMAP, 0,
                 len(CLASS_IDS) - 1)
    district_outline(ax, mask, profile)

    _finish_side(ax_side, profile,
                 _swatches([CLASS_COLOURS[c] for c in CLASS_IDS]),
                 _class_legend_labels(lulc, mask, area),
                 legend_title="Land cover")

    path = path or FIG_DIR / f"lulc_{year}.png"
    fig.savefig(path, dpi=300, facecolor=PAPER)
    plt.close(fig)
    return path


def builtup_expansion_map(t0map, t1map, mask, profile, y0, y1, path=None,
                          area=None):
    b0 = (t0map == 0) & mask
    b1 = (t1map == 0) & mask
    sels = (mask & ~b0 & ~b1, b0 & b1, ~b0 & b1, b0 & ~b1)

    cat = np.full(t0map.shape, np.nan)
    for i, sel in enumerate(sels):
        cat[sel] = i

    colours = ["#eceee9", "#7f8c8d", "#c0392b", "#2874a6"]
    names = ["Not built-up,\nboth dates", "Built-up,\nboth dates",
             f"New built-up\n{y0}–{y1}", f"Built-up lost\n{y0}–{y1}"]
    if area is not None:
        tot = float(area[mask].sum())
        for i, sel in enumerate(sels):
            ha = float(area[sel].sum())
            names[i] += f"\n{ha:,.0f} ha ({100 * ha / tot:.1f}%)"

    fig, ax, _, ax_side = _single_figure(
        profile, f"Built-up expansion, Lahore District, {y0}–{y1}",
        "“Built-up lost” is largely classification instability "
        "between epochs, not genuine de-urbanisation; see docs/results.md.\n"
        + CAPTION_CRS)

    _draw_raster(ax, np.ma.masked_invalid(cat), profile,
                 ListedColormap(colours), 0, 3)
    district_outline(ax, mask, profile)

    _finish_side(ax_side, profile, _swatches(colours), names,
                 legend_title="Built-up change")

    path = path or FIG_DIR / f"builtup_expansion_{y0}_{y1}.png"
    fig.savefig(path, dpi=300, facecolor=PAPER)
    plt.close(fig)
    return path


def _carbon_shade(value, vmax):
    """Single-hue green, light to dark, positioned by carbon density."""
    stops = ["#eef4ea", "#d2e4c8", "#a9d0a0", "#7bb977", "#4b9c54",
             "#2d7d3e", "#185d2b"]
    frac = 0.0 if vmax <= 0 else min(max(value / vmax, 0.0), 1.0)
    return stops[min(int(frac * len(stops)), len(stops) - 1)]


def carbon_map(density, mask, profile, year, path=None, vmax=None, area=None):
    """Carbon density. Legend is discrete because density is assigned by class.

    Rendering this as a continuous ramp with a colourbar implies a measured
    field. Only four values ever occur, one per land-cover class, so the legend
    names the four and states each value.
    """
    table = total_carbon("best")
    top = vmax or max(table.values())
    order = sorted(CLASS_IDS, key=lambda c: table[c])
    colours = [_carbon_shade(table[c], top) for c in order]

    idx = np.full(density.shape, np.nan)
    for i, c in enumerate(order):
        idx[mask & np.isclose(density, table[c])] = i

    fig, ax, _, ax_side = _single_figure(
        profile, f"Carbon density, Lahore District, {year}",
        "Carbon density assigned per land-cover class (IPCC Tier 1 "
        "placeholders; see docs/carbon_sources.md);\nthe surface is piecewise "
        "constant by class, not a measured continuous field.\n" + CAPTION_CRS)

    _draw_raster(ax, np.ma.masked_invalid(idx), profile,
                 ListedColormap(colours), 0, len(order) - 1)
    district_outline(ax, mask, profile)

    labels = [f"{CLASSES[c]}\n{table[c]:.1f} Mg C ha⁻¹" for c in order]
    if area is not None:
        tot = float(area[mask].sum())
        for i, c in enumerate(order):
            ha = float(area[mask][np.isclose(density[mask], table[c])].sum())
            labels[i] += f"\n{100 * ha / tot:.1f}% of district"

    _finish_side(ax_side, profile, _swatches(colours), labels,
                 legend_title="Carbon density")

    path = path or FIG_DIR / f"carbon_density_{year}.png"
    fig.savefig(path, dpi=300, facecolor=PAPER)
    plt.close(fig)
    return path
