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
transition, the forest value inflates the reported carbon loss roughly
threefold. `src/config.py` carries corrected pool values with uncertainty
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

## Layout

```
src/       pipeline modules
gee/       corrected Earth Engine script
data/lulc/ the four exported class maps (not committed; see below)
outputs/   maps, figures, tables, summary.json
docs/      method notes and carbon source tracking
```

## Running

```bash
.venv/Scripts/python.exe src/run_pipeline.py
```

Input rasters are not committed (they are Earth Engine exports and belong in
Drive). Place `Lahore_{1993,2003,2013,2023}_RF_LULC.tif` in `data/lulc/`.
