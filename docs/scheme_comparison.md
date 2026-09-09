# Four classes or three: sensitivity analysis

Both runs are kept. `outputs/` is the four-class scheme as originally
classified and is **the reported result**; `outputs_3class/` merges bare land
into built-up as a single non-vegetated class and serves as **a sensitivity
test**. Select the latter with `LULC_SCHEME=three`.

## Why the question arises

Bare land is not behaving like a land cover class in these maps. The share of
bare-land pixels that change class each decade is 82% (1993–2003), 58%
(2003–2013) and 77% (2013–2023). Real land cover does not turn over at that
rate. Bare, dry soil and concrete are close in Landsat's spectral space, so the
Random Forest classifier flips pixels between built-up and bare between epochs.

That churn enters the Markov matrix as if it were land conversion, and the
transition-potential forests then try to learn where it happens — but it has no
spatial logic to learn, because it is measurement error.

## What merging changed

| Metric | 4-class | 3-class | |
|---|---|---|---|
| **FoM**, predicting 2013 | 0.215 | **0.252** | better |
| **FoM**, predicting 2023 | 0.266 | **0.286** | better |
| Overall accuracy, 2013 | 0.718 | **0.738** | better |
| Overall accuracy, 2023 | 0.638 | **0.714** | much better |
| Kappa, 2013 | 0.429 | **0.451** | better |
| Kappa, 2023 | 0.344 | **0.439** | much better |
| Wrong hits, 2013 | 65,362 | **19,621** | 70% fewer |
| Wrong hits, 2023 | 91,968 | **20,323** | 78% fewer |
| Quantity disagreement, 2023 | 0.036 | **0.004** | near-zero |
| Allocation disagreement, 2023 | 0.326 | **0.282** | better |
| Built-up area error, 2023 | −8.11% | **−0.81%** | ten-fold better |

Every metric improves, and two improve dramatically.

**The wrong-hits collapse is the clearest evidence.** A wrong hit is a pixel the
model correctly identified as changing but assigned to the wrong destination
class. Merging removed roughly three quarters of them, which is what you would
expect if most were built-up/bare confusion rather than genuine misallocation.

**Quantity disagreement falling to 0.004** means the three-class Markov step
predicts the 2023 class totals almost exactly. The four-class version could not,
because it was trying to forecast a quantity of bare land that is largely noise.

## What did not improve

The model still over-predicts change: 60,273 ha simulated against 30,833 ha
observed in the 2023 test, and overall accuracy is still below the null
persistence model (0.714 against 0.822). Merging fixed the class-confusion
problem. It did not fix the tendency to allocate too much change, which comes
from the Markov matrix carrying every remaining source of inter-epoch
inconsistency, including the seasonal water and vegetation instability.

## Decision: four classes is the reported result

**The four-class scheme is the primary result. The three-class run is retained
as a sensitivity test.**

The metrics above favour three classes, so this choice has to be argued rather
than assumed. The arguments for keeping four:

- **Bare land is a real category in a peri-urban district.** Vacant plots held
  for speculation, brick-kiln land, and abandoned agricultural land are
  planning-relevant and physically distinct from built structures. Merging them
  into "built-up" erases a category that a land-use thesis may legitimately need
  to discuss.
- **The carbon densities genuinely differ.** Built-up carries 25.0 Mg C/ha
  against bare land's 15.4. Merging assigns former bare pixels the denser
  blended value, which overstates their carbon. The three-class 1993 stock is
  7.23M Mg C against the four-class 7.13M for that reason alone.
- **Comparability.** Four-class schemes (built-up / vegetation / water / bare)
  are the convention in published Pakistani LULC work, and an InVEST carbon
  workflow expects distinct land-use categories.

**What this costs, and what must therefore be disclosed.** Retaining bare land
means retaining its instability: 58 to 82% of bare-land pixels change class each
decade, which is spectral confusion with built-up rather than land change.
Figure of Merit falls from 0.286 to 0.266 predicting 2023, overall accuracy from
0.714 to 0.638, and wrong hits rise from 20,323 to 91,968.

The defensible way to write this is to report the four-class result, state the
bare-land instability as a known limitation with the numbers above, and cite
this comparison as the sensitivity analysis showing how much it costs. That is
honest. Reporting four classes without acknowledging the instability is not,
because the first examiner to plot bare-land area across the four epochs will
see it oscillate.

## One caution on comparing carbon between schemes

Absolute carbon totals are not directly comparable across the two schemes. Under
merging, former bare-land pixels inherit the blended non-vegetated density
(24.4 Mg C/ha) instead of the bare-land value (15.4 Mg C/ha), which raises the
stock slightly. 1993 total goes from 7.13M to 7.23M Mg C for that reason alone,
not because of any change in land cover.

Compare trajectories, transition attributions and validation metrics between
schemes. Do not compare the absolute stock figures.

## Projections under each scheme

| Scheme | 2023 built-up | 2033 | 2043 |
|---|---|---|---|
| 4-class (built-up only) | 77,371 | 86,225 | 91,784 |
| 3-class (built-up + bare) | 82,857 | 91,417 | 97,207 |

Vegetation lands in nearly the same place either way — 75,151 ha against
74,554 ha by 2043 — which is reassuring. The vegetation signal is what the
carbon result depends on, and it does not hinge on how the non-vegetated
classes are split.

## What the merged series makes visible

Collapsing built-up and bare into one line exposes something the four-class
chart hid. Non-vegetated area by decade:

| Interval | Change |
|---|---|
| 1993 to 2003 | **+2,229 ha** |
| 2003 to 2013 | +18,964 ha |
| 2013 to 2023 | +12,676 ha |

Lahore did not almost stop growing during the 1990s and then grow ninefold
faster in the 2000s. The 1993-2003 figure is too low, which points again at the
2003 Landsat 7 composite: vegetation is over-classified that year, at the
expense of both bare land and built-up.

This matters for the projection because the 1993-2003 matrix is what calibrates
the first back-validation. It is the weaker of the two tests for exactly this
reason, and it is consistent with that test scoring the lower Figure of Merit
(0.252 against 0.286).

For the thesis, the honest framing is that the 2003 epoch is the least reliable
of the four, and that the 2013-2023 interval used to drive the projection is the
most reliable, being the most recent, the most spectrally consistent (Landsat 8
and 9 share band definitions) and free of the SLC-off problem.
