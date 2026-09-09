# Carbon density sources — ACTION REQUIRED

The values in `src/config.py` are defensible Tier 1 placeholders chosen for a
warm-temperate / tropical dry climate with irrigated annual cropland. They are
**not** transcribed from a specific IPCC table. Before submission, each cell
below must be replaced with a cited value.

| Class | Pool | Placeholder (low/best/high, Mg C/ha) | Citation to add |
|---|---|---|---|
| Built-up | above | 2.0 / 5.0 / 9.0 | IPCC 2006 Vol.4 Ch.8 Settlements |
| Built-up | below | 0.5 / 1.5 / 3.0 | |
| Built-up | soil | 10.0 / 18.0 / 30.0 | |
| Built-up | dead | 0.0 / 0.5 / 1.5 | |
| Vegetation | above | 3.0 / 6.0 / 14.0 | IPCC 2006 Vol.4 Ch.5 Cropland |
| Vegetation | below | 1.0 / 2.0 / 4.0 | |
| Vegetation | soil | 30.0 / 42.0 / 55.0 | SOC reference, 0–30 cm |
| Vegetation | dead | 0.5 / 1.5 / 3.0 | |
| Water | soil | 2.0 / 5.0 / 10.0 | sediment carbon |
| Bare land | above | 0.3 / 1.0 / 2.5 | |
| Bare land | below | 0.1 / 0.4 / 1.0 | |
| Bare land | soil | 8.0 / 14.0 / 22.0 | |
| Bare land | dead | 0.0 / 0.0 / 0.5 | |

## Why the vegetation value changed

The original Earth Engine script used 150 Mg C/ha total for Vegetation
(50 above + 20 below + 70 soil + 10 dead). That is a closed-forest figure.
Lahore District's vegetation class is overwhelmingly irrigated rice-wheat
cropland with a scattered orchard and urban-tree component. An annual crop is
harvested, so standing biomass at any given time is close to zero, and Tier 1
above-ground carbon for annual cropland is on the order of 5 Mg C/ha rather
than 50.

Because vegetation-to-built-up is the dominant transition in this district, the
per-hectare carbon loss booked by the original table (150 − 28 = 122 Mg C/ha)
is roughly three times the defensible figure. The pipeline reports both so the
magnitude of the correction is visible.

## What would make this Tier 2

Field sampling of SOC in Lahore cropland, or calibration against a spatial
biomass product. Either would replace the class-mean assumption with something
locally grounded. Worth flagging as further work rather than attempting here.
