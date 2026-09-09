# Lahore LULC and Carbon Projection

Projecting land use / land cover and terrestrial carbon stock for Lahore
District, Punjab, Pakistan, from four classified Landsat epochs (1993, 2003,
2013, 2023) forward to 2033 and 2043.

The classification itself is done in Google Earth Engine (Random Forest on
Landsat 5/7/8/9 surface reflectance plus NDVI, NDBI, NDWI). This repository
takes the four exported class maps and does everything after that: transition
analysis, machine-learning transition potential, cellular-automata allocation,
back-validation, projection, and carbon accounting.

## Method

**Not deep learning, and deliberately so.** Four time points is far too few to
train a temporal neural network. Anything presented as an LSTM or ConvLSTM over
four epochs would be fitting noise and dressing it up as sophistication. The
method here is CA-Markov with a Random Forest transition potential, which is the
standard defensible approach for this data density.

1. **Markov transition matrices** between consecutive epochs give the *quantity*
   of each class conversion per decade.
2. **Random Forest transition potential** (one forest per origin class, trained
   on distance and neighbourhood drivers) gives the *location* — where each
   conversion is most likely.
3. **Competitive cellular-automata allocation** assigns pixels so that class
   totals match the Markov demand exactly while the forests decide placement.
   Drivers are recomputed at every step, so new built-up created in 2033 shapes
   where growth goes in 2043.
4. **Carbon accounting** applies per-class IPCC-style carbon densities across
   four pools, with a low/best/high band on every figure.

## Validation

The projection is produced only after the same method is tested against years we
can actually check:

- calibrate on 1993 to 2003, predict 2013, compare against observed 2013
- calibrate on 2003 to 2013, predict 2023, compare against observed 2023

The headline metric is the **Figure of Merit**, not overall accuracy. In a
district where most pixels do not change in a decade, a model predicting no
change anywhere scores around 90% overall accuracy while being useless. Figure
of Merit ignores correctly predicted persistence entirely. Every metric is
reported alongside the null persistence model, and the pipeline refuses to
produce a projection if the model cannot beat that null.

## Two corrections to the original Earth Engine workflow

**Carbon densities.** The original script assigned the Vegetation class
150 Mg C/ha total (50 above-ground + 20 below + 70 soil + 10 dead). That is a
closed-forest value. Lahore District's vegetation class is dominated by
irrigated rice-wheat cropland, which is harvested annually and stores very
little standing biomass. Since vegetation-to-built-up is the dominant
transition, the forest value inflates the reported carbon loss. Measured on the
actual maps, it overstates the 1993-2023 loss by a factor of 5.9. `src/config.py` carries corrected pool values with uncertainty
ranges, and the pipeline reports the original table alongside so the size of the
correction is explicit rather than silent.

**Change map construction.** The original `lulc2023.subtract(lulc1993)` is not
interpretable, because class codes are nominal labels rather than quantities: a
difference of 2 could be built-up to water or vegetation to bare land, and they
render identically. This repository uses a from-to crosstab instead, which is
also what the Markov step consumes.

## Known limitations

- **Accuracy of the input maps is unverified.** The Earth Engine script split
  pixels sampled from the same digitised training points, so training and test
  pixels are spatially autocorrelated and the reported overall accuracy is
  optimistic, typically by 10 to 15 points. Classification error propagates into
  the transition matrix as fictitious change. An independent stratified random
  validation is needed, and is genuinely hard for 1993 and 2003 given the lack
  of high-resolution reference imagery for that period.
- **Landsat 7 SLC failure** (May 2003) means the 2003 composite draws on
  scan-line-corrector-off scenes. Median compositing over 2002 to 2004 fills
  most gaps but not uniformly.
- **2043 is two steps beyond the last observation.** It is reported with its
  uncertainty band, not as a crisp forecast.
- **Carbon densities are Tier 1 placeholders** pending citation against the IPCC
  guidelines and Pakistani literature. See `docs/carbon_sources.md`.

## Figures

Map figures are publication-ready rather than plain rasters: neatline,
latitude/longitude graticule, segmented scale bar, north arrow, locator inset,
panel letters, and a caption stating the CRS, cell size and data source.

**Nothing is drawn on top of the map.** Legend, inset, scale bar and north arrow
occupy margins created by the figure grid: a furniture column to the right and a
scale strip beneath. Floating them over the data in boxes covers something in
every panel, and which thing changes between epochs. The scale strip shares its
x-limits with the map axis, so the bar's length is exact in degrees rather than
inferred from figure geometry.

One detail worth knowing if you regenerate them. The rasters are geographic
(EPSG:4326), so plotting degrees on a square grid stretches the district
east-west by about 17% at Lahore's latitude. Every axis sets an aspect of
1/cos(latitude) so the shape is true. A map drawn without that correction is
subtly the wrong shape, which is the sort of thing an examiner notices without
being able to say why.

Produced per run:

- `lulc_panel.png` — all six epochs, panels (a) to (f), projected ones labelled
- `lulc_<year>.png` — each epoch full page, with class areas and percentages
- `builtup_expansion_<y0>_<y1>.png` — persistent, new and lost built-up
- `carbon_density_<year>.png` — carbon surface, colourbar ticked at the four
  values that actually occur, since density is assigned per class

Regenerate the maps alone, without re-running the model:

```bash
.venv/Scripts/python.exe src/make_maps.py
```

## Layout

```
src/       pipeline modules (cartography.py holds the map figures)
gee/       corrected Earth Engine script
data/lulc/ the four exported class maps (not committed; see below)
outputs/   maps, figures, tables, summary.json
docs/      method notes and carbon source tracking
```

## Class schemes

Two schemes are supported and both are kept, selected by an environment
variable so every module agrees on one of them:

- **four** (default) - Built-up / Vegetation / Water / Bare land, as classified.
  Outputs to `outputs/`.
- **three** - bare land merged into built-up as one non-vegetated class.
  Outputs to `outputs_3class/`.

**Four classes is the reported result; three is the sensitivity test.** Bare
land is kept because it is a real and planning-relevant category in a peri-urban
district and because its carbon density genuinely differs from built-up.

That choice has a measurable cost and the cost is disclosed rather than hidden:
bare land changes class in 58-82% of its pixels each decade, which is Landsat
confusing dry soil with concrete rather than land change. Merging it away raises
the Figure of Merit from 0.266 to 0.286 and cuts wrong hits by three quarters.
`docs/scheme_comparison.md` carries the full table and the argument on both
sides.

## Running

```bash
.venv/Scripts/python.exe src/run_pipeline.py
```

```bash
LULC_SCHEME=three .venv/Scripts/python.exe src/run_pipeline.py
```

Input rasters are not committed (they are Earth Engine exports and belong in
Drive). Place `Lahore_{1993,2003,2013,2023}_RF_LULC.tif` in `data/lulc/`.

## Data hazard in the Earth Engine exports

The exported GeoTIFFs carry no nodata value. Earth Engine writes masked pixels
as 0, and 0 is the Built-up class code, so everything outside the district
polygon reads as built-up city - 1.80 million pixels, 44% of each raster.

Statistics printed inside Earth Engine are unaffected, because `reduceRegion`
was bounded by `lahore.geometry()`. Anything computed from the exported files
in QGIS, ArcGIS or InVEST is affected. `rasters.district_mask()` recovers the
clip geometry; the fix at source is to set a real nodata value on export.

The rasters are also in EPSG:4326, where a 0.000269 degree pixel at Lahore is
about 766 m2, not the 900 m2 of a nominal 30 m grid. Counting pixels and
multiplying by 0.09 ha overstates every area by 17%.
