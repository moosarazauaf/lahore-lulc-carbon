"""Web assets for the portfolio site.

Produces three things from the same rasters the thesis figures use:

  hero_banner.jpg   ultra-wide cinematic plate for the site hero
  tile_<year>.png   clean district silhouettes, transparent, for the scrubber
  lahore_lulc.json  per-year areas and carbon, so the page can state numbers

The banner is composition, not analysis. Six epochs run left to right across a
21:9 frame; the past is dim, the present sits bright at the golden-section point
(width / 1.618), and the projected years fade out ahead of it. The site draws a
scrim and its type over this, so it stays atmospheric rather than information
dense - the numbers are the scrubber's job.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

import carbon
import markov
import rasters
from config import CLASS_IDS, CLASSES, OBSERVED_YEARS, PROJECTION_YEARS, ROOT, MAP_DIR, NODATA

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WEB = ROOT / "web"
WEB.mkdir(exist_ok=True)

# Site brand tokens, so the plate belongs to the page rather than sitting on it.
FOREST_DEEP = (0x16, 0x26, 0x1F)
FOREST = (0x24, 0x3E, 0x36)
SAGE = (0x7C, 0xA9, 0x82)
MEADOW = (0xE0, 0xEE, 0xC6)
GOLD = (0xC2, 0xA8, 0x3E)
PAPER = (0xF1, 0xF7, 0xED)

# Class colours adapted for a dark plate: built-up reads as warm gold-red glow,
# vegetation as sage, water as a cool light, bare as muted gold.
DARK_CLASS_RGB = {
    0: (0xE2, 0x6D, 0x4B),
    1: (0x5E, 0x9A, 0x6E),
    2: (0x6F, 0xB6, 0xD6),
    3: (0xC2, 0xA8, 0x3E),
}
PHI = 1.618033988749895


def _rgba_tile(lulc, mask, palette, scale=1.0):
    """District as an RGBA array, everything outside the district transparent."""
    h, w = lulc.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for cid in CLASS_IDS:
        sel = mask & (lulc == cid)
        r, g, b = palette[cid]
        out[sel] = (r, g, b, 255)
    img = Image.fromarray(out, mode="RGBA")
    if scale != 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                         Image.LANCZOS)
    return img


def _aspect_correct(img, profile):
    """Undo the geographic-CRS stretch so the district is the right shape."""
    import math
    T = profile["transform"]
    lat = T.f + (profile["height"] * T.e) / 2.0
    factor = math.cos(math.radians(lat))
    w, h = img.size
    return img.resize((max(1, int(w * factor)), h), Image.LANCZOS)


def _vertical_gradient(size, top, bottom):
    w, h = size
    ramp = np.linspace(0.0, 1.0, h)[:, None]
    arr = np.zeros((h, w, 3), dtype=np.float64)
    for i in range(3):
        arr[:, :, i] = top[i] * (1 - ramp) + bottom[i] * ramp
    return Image.fromarray(arr.astype(np.uint8), mode="RGB")


def _glow(img, radius=26, strength=0.85):
    """Soft bloom behind a tile, which is what makes it read as cinematic."""
    from PIL import ImageFilter
    a = img.split()[-1]
    blur = img.filter(ImageFilter.GaussianBlur(radius))
    blur.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(
        lambda v: int(v * strength)))
    return blur


def _two_tone(lulc, mask, built_rgb, land_rgb):
    """Silhouette in two tones: built-up bright, everything else recessive.

    Used for the epochs either side of the present. Rendering them in full class
    colour made six competing maps; reducing them to a built-up/not-built-up
    silhouette keeps the growth story legible while letting the measured present
    hold the eye.
    """
    h, w = lulc.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    land = mask & (lulc != 0)
    built = mask & (lulc == 0)
    out[land] = (*land_rgb, 255)
    out[built] = (*built_rgb, 255)
    return Image.fromarray(out, mode="RGBA")


def build_banner(maps, mask, profile, width=3840, height=1646, present=2023):
    """21:9 cinematic plate: a filmstrip of epochs, present on the golden point.

    Composition rules, in case this is ever retuned:
      - the present epoch sits at width / phi, which is where the eye lands
      - past epochs run left in sage, future epochs run right in gold, both as
        two-tone silhouettes so they read as context rather than as data
      - the site draws a scrim and its type over the lower third, so the frame
        stays quiet down there
    """
    from PIL import ImageFilter

    years = sorted(maps)
    canvas = _vertical_gradient((width, height), (0x08, 0x12, 0x0E),
                                FOREST_DEEP).convert("RGBA")

    grid = np.zeros((height, width, 4), dtype=np.uint8)
    for x in range(0, width, 180):
        grid[:, x] = (*SAGE, 10)
    for y in range(0, height, 180):
        grid[y, :] = (*SAGE, 10)
    canvas = Image.alpha_composite(canvas, Image.fromarray(grid, mode="RGBA"))

    focus_x = width / PHI
    idx_present = years.index(present)

    probe = _aspect_correct(_rgba_tile(maps[present], mask, DARK_CLASS_RGB),
                            profile)
    tile_h = int(height * 0.60)
    scale = tile_h / probe.size[1]
    tile_w = int(probe.size[0] * scale)
    step = int(width * 0.148)

    # Past: sage. Future: gold. Both two-tone, dimming away from the present.
    PAST = ((0xA6, 0xD4, 0xB1), (0x2E, 0x52, 0x40))
    FUTURE = ((0xE4, 0xC9, 0x66), (0x46, 0x42, 0x28))

    plan = []
    for i, year in enumerate(years):
        offset = i - idx_present
        if offset == 0:
            tile = _rgba_tile(maps[year], mask, DARK_CLASS_RGB)
            alpha, glow_r, glow_s = 1.0, 34, 0.60
        else:
            built, land = PAST if offset < 0 else FUTURE
            tile = _two_tone(maps[year], mask, built, land)
            steps = abs(offset)
            # The site lays a heavy scrim over this plate for text legibility,
            # so the context epochs are pitched brighter than they would need
            # to be on their own; under the scrim they land about right.
            alpha = max(0.40, (0.82 if offset < 0 else 0.76) - 0.14 * (steps - 1))
            glow_r, glow_s = 18, 0.22
        plan.append((abs(offset), offset, tile, alpha, glow_r, glow_s))

    # Draw furthest first so the present composites last and stays on top.
    for _, offset, tile, alpha, glow_r, glow_s in sorted(plan, key=lambda t: -t[0]):
        tile = _aspect_correct(tile, profile).resize((tile_w, tile_h),
                                                     Image.LANCZOS)
        tile.putalpha(tile.split()[-1].point(lambda v: int(v * alpha)))
        x = int(focus_x + offset * step - tile_w / 2)
        y = int((height - tile_h) / 2)
        canvas = Image.alpha_composite(
            canvas, _pad(_glow(tile, radius=glow_r, strength=glow_s),
                         (width, height), (x, y)))
        canvas = Image.alpha_composite(canvas, _pad(tile, (width, height), (x, y)))

    yy, xx = np.mgrid[0:height, 0:width]
    d = np.sqrt(((xx - focus_x) / (width * 0.80)) ** 2 +
                ((yy - height / 2) / (height * 0.92)) ** 2)
    v = np.clip((d - 0.50) / 0.90, 0, 1) ** 1.3
    vig = np.zeros((height, width, 4), dtype=np.uint8)
    vig[:, :, 0], vig[:, :, 1], vig[:, :, 2] = 0x06, 0x0D, 0x0A
    vig[:, :, 3] = (v * 240).astype(np.uint8)
    canvas = Image.alpha_composite(canvas, Image.fromarray(vig, mode="RGBA"))

    out = canvas.convert("RGB").filter(ImageFilter.SMOOTH)
    path = WEB / "hero_banner.jpg"
    out.save(path, quality=88, optimize=True, progressive=True)
    out.resize((1920, int(1920 * height / width)), Image.LANCZOS).save(
        WEB / "hero_banner_1920.jpg", quality=86, optimize=True, progressive=True)
    return path


def _pad(tile, size, xy):
    """Place a tile onto a transparent canvas of `size` at `xy`."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(tile, xy, tile)
    return layer


def _to_palette_png(rgba, path, colours=15):
    """Save an RGBA tile as a paletted PNG with a transparent index.

    These tiles carry four flat class colours over transparency, so a truecolour
    PNG spends about a megabyte encoding information that is not there. Indexing
    them drops each file by roughly an order of magnitude, which matters when six
    of them load on one page.
    """
    alpha = np.array(rgba.split()[-1])
    pal_img = rgba.convert("RGB").quantize(colors=colours,
                                           method=Image.MEDIANCUT)
    idx = np.array(pal_img)
    idx[alpha < 128] = colours                       # reserve the last index
    palette = pal_img.getpalette()[: colours * 3] + [0, 0, 0]

    out = Image.fromarray(idx, mode="P")
    out.putpalette(palette)
    out.info["transparency"] = colours
    out.save(path, optimize=True, transparency=colours)
    return path


def build_tiles(maps, mask, profile, target_w=900):
    """Clean per-year district tiles for the scrubber, transparent background."""
    paths = []
    for year in sorted(maps):
        tile = _aspect_correct(_rgba_tile(maps[year], mask, DARK_CLASS_RGB),
                               profile)
        w, h = tile.size
        tile = tile.resize((target_w, int(h * target_w / w)), Image.LANCZOS)
        p = _to_palette_png(tile, WEB / f"tile_{year}.png")
        paths.append(p)
    return paths


def build_stats(maps, mask, area):
    years = sorted(maps)
    payload = {
        "district": "Lahore District, Punjab, Pakistan",
        "districtAreaHa": round(float(area[mask].sum()), 1),
        "observedYears": [y for y in years if y in OBSERVED_YEARS],
        "projectedYears": [y for y in years if y in PROJECTION_YEARS],
        "classes": {str(c): CLASSES[c] for c in CLASS_IDS},
        "years": {},
    }
    for y in years:
        areas = markov.area_hectares(maps[y], mask, area)
        bounds = carbon.stock_with_bounds(maps[y], mask, area)
        payload["years"][str(y)] = {
            "areaHa": {str(c): round(areas[c], 1) for c in CLASS_IDS},
            "sharePct": {str(c): round(100 * areas[c] / sum(areas.values()), 2)
                         for c in CLASS_IDS},
            "carbonMgC": {k: round(v) for k, v in bounds.items()},
            "projected": y in PROJECTION_YEARS,
        }
    path = WEB / "lahore_lulc.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main():
    import rasterio
    maps, profile, mask = rasters.load_all(OBSERVED_YEARS)
    area = rasters.pixel_area_ha(profile)

    for y in PROJECTION_YEARS:
        p = MAP_DIR / f"projected_{y}.tif"
        if not p.exists():
            print(f"  missing {p.name}; run src/run_pipeline.py first")
            continue
        with rasterio.open(p) as src:
            arr = src.read(1).astype("uint8")
        arr[~mask] = NODATA
        maps[y] = arr

    print("\nweb assets")
    print("  " + str(build_banner(maps, mask, profile)))
    for p in build_tiles(maps, mask, profile):
        print("  " + str(p))
    print("  " + str(build_stats(maps, mask, area)))


if __name__ == "__main__":
    main()
