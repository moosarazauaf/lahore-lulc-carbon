# Results, first complete run

District area recovered from the clip geometry: **1,735 km²** (published extent
~1,772 km², so the mask is within 2%).

## Observed land cover (hectares)

| Year | Built-up | Vegetation | Water | Bare land |
|---|---|---|---|---|
| 1993 | 35,485 | 116,495 | 8,019 | 13,503 |
| 2003 | 48,341 | 119,517 | 2,768 | 2,876 |
| 2013 | 61,382 | 101,224 | 2,097 | 8,799 |
| 2023 | 77,371 | 88,787 | 1,859 | 5,486 |

Built-up more than doubled, from 20% of the district to 45%. Vegetation fell
24%. Both are consistent with what is independently known about Lahore's
expansion over this period.

## Projection

| Year | Built-up | Vegetation | Water | Bare land |
|---|---|---|---|---|
| 2033 | 86,225 | 80,608 | 1,806 | 4,864 |
| 2043 | 91,784 | 75,151 | 1,794 | 4,773 |

Growth decelerates because the Markov chain is saturating: by 2043 there is
much less vegetation left to convert. This is a property of the model, not a
prediction that planning will slow expansion.

## Validation

| Test | Overall acc. | Null (persistence) | Kappa | **Figure of Merit** | Null FoM |
|---|---|---|---|---|---|
| calibrated 1993–2003, predicted 2013 | 0.718 | 0.771 | 0.429 | **0.215** | 0.000 |
| calibrated 2003–2013, predicted 2023 | 0.638 | 0.778 | 0.344 | **0.266** | 0.000 |

Figure of Merit of 0.22–0.27 sits at the upper end of the published CA-Markov
range, which is usually quoted as roughly 0.05–0.25. The model clearly carries
real spatial signal.

**But overall accuracy is below the null model in both tests.** That is not a
contradiction, it is the model's characteristic error: it predicts too much
change. In the 2023 test it simulated 76,895 ha of change against 38,523 ha
observed, generating 613,276 false-alarm pixels. Allocation disagreement (0.326)
dominates quantity disagreement (0.036), so the Markov step gets the *amounts*
close while the Random Forest scatters them into the wrong places.

Report both numbers. Quoting the Figure of Merit alone would be selective.

## Carbon

| Year | Low | Best | High | Original script's table |
|---|---|---|---|---|
| 1993 | 4,592,112 | 7,134,673 | 10,828,507 | 18,751,017 |
| 2003 | 4,757,300 | 7,421,792 | 11,288,601 | 19,346,723 |
| 2013 | 4,337,623 | 6,893,598 | 10,612,919 | 17,071,216 |
| 2023 | 4,080,076 | 6,600,563 | 10,274,643 | 15,592,427 |
| 2033 | 3,903,255 | 6,390,866 | 10,021,507 | 14,602,082 |
| 2043 | 3,783,701 | 6,247,365 | 9,846,139 | 13,937,537 |

All values Mg C.

**1993–2023 carbon change: −534,110 Mg C (corrected) against −3,158,590 Mg C
(original table). The original overstates the loss by a factor of 5.9.**

The factor is larger than the ~3× first estimated, because the forest value
inflates the *stock* as well as the per-hectare loss on conversion.

## Problems in the input maps that the run exposed

These are properties of the classification, not of the projection, and they cap
how much the projection can be worth.

**1. Water collapses between 1993 and 2003 (8,019 ha to 2,768 ha).** The Ravi
has genuinely declined, but not by 65% in one decade. The far more likely cause
is river stage and season: the median composite over 1992–1994 and the one over
2002–2004 do not represent the same hydrological moment. This propagates
directly into the 1993 carbon baseline.

**2. Bare land is unstable to the point of being unusable as a class.** The
share of bare-land pixels that change class each decade is 82% (1993–2003), 58%
(2003–2013) and 77% (2013–2023). Genuine land cover does not behave that way.
Bare land and built-up are spectrally similar in Landsat, particularly for dry
soil against concrete, and the classifier is flipping between them. Per-class
area error in validation is −88% then +106% for bare land, the worst of any
class by far.

**3. 2003 shows vegetation increasing while built-up also increases**, which is
only possible because water and bare land both collapsed. This is very likely a
classification artefact of the Landsat 7 composite rather than real change.

Consequences: some of what the Markov matrix reads as "transition" is
classification error. Since classification error is random with respect to
location while real urban growth is spatially structured, this mostly adds noise
and depresses the Figure of Merit rather than biasing the direction of change.
The direction of the headline result (built-up up, vegetation down, carbon down)
is robust. The exact magnitudes are not.

## What would most improve this

In order of how much they would change the answer:

1. **Merge bare land into a single non-vegetated class, or drop it.** With four
   classes where one is unstable, roughly a third of modelled transitions are
   noise. Three stable classes would very likely raise the Figure of Merit.
2. **Fix composite seasonality.** Restrict every year's composite to the same
   months (a dry-season window) so water extent and crop phenology are
   comparable across dates.
3. **Independent accuracy assessment**, replacing the random split of training
   pixels, which is spatially autocorrelated and optimistic.
4. **Cite the carbon densities** against IPCC and Pakistani literature.
