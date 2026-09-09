"""Transition potential (Random Forest) + competitive CA allocation."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from config import CLASS_IDS, N_CLASSES
import drivers as drv
import markov

MAX_SAMPLES_PER_CLASS = 120_000
RF_KW = dict(
    n_estimators=300,
    min_samples_leaf=20,
    max_features="sqrt",
    n_jobs=-1,
    class_weight="balanced_subsample",
)


class TransitionPotential:
    """One Random Forest per origin class, predicting the destination class.

    Modelling destinations per origin class (rather than one global model) keeps
    each forest focused on a real decision: given that this pixel is cropland
    today, does it stay cropland, become built-up, or go bare? Transitions that
    never occur in the calibration data are simply absent from that forest's
    classes and therefore get zero potential, which is the correct behaviour.
    """

    def __init__(self, seed: int = 42):
        self.models: dict[int, RandomForestClassifier] = {}
        self.oob: dict[int, float] = {}
        self.importances: dict[int, np.ndarray] = {}
        self.names: list[str] = []
        self.seed = seed

    def fit(self, lulc_t0, lulc_t1, mask):
        X, self.names = drv.build(lulc_t0, mask)
        origin = lulc_t0[mask].astype(int)
        dest = lulc_t1[mask].astype(int)
        rng = np.random.default_rng(self.seed)

        for c in CLASS_IDS:
            idx = np.flatnonzero(origin == c)
            if idx.size < 200:
                print(f"  class {c}: only {idx.size} pixels, no model fitted")
                continue
            if idx.size > MAX_SAMPLES_PER_CLASS:
                idx = rng.choice(idx, MAX_SAMPLES_PER_CLASS, replace=False)
            y = dest[idx]
            if np.unique(y).size == 1:
                print(f"  class {c}: no observed change, persistence only")
                continue
            rf = RandomForestClassifier(
                random_state=self.seed, oob_score=True, bootstrap=True, **RF_KW
            )
            rf.fit(X[idx], y)
            self.models[c] = rf
            self.oob[c] = float(rf.oob_score_)
            self.importances[c] = rf.feature_importances_
            changed = 100 * float((y != c).mean())
            print(f"  class {c}: n={idx.size:,}  changed={changed:5.2f}%  OOB={rf.oob_score_:.3f}")
        return self

    def potential(self, lulc, mask) -> np.ndarray:
        """(n_pixels, n_classes) probability of each destination class."""
        X, _ = drv.build(lulc, mask)
        origin = lulc[mask].astype(int)
        P = np.zeros((X.shape[0], N_CLASSES), dtype="float32")
        for c in CLASS_IDS:
            sel = origin == c
            if not sel.any():
                continue
            rf = self.models.get(c)
            if rf is None:
                P[sel, c] = 1.0
                continue
            probs = rf.predict_proba(X[sel])
            for j, cls in enumerate(rf.classes_):
                P[sel, int(cls)] = probs[:, j]
        return P


def allocate(lulc, mask, potential: np.ndarray, demand: np.ndarray) -> np.ndarray:
    """Assign each pixel a class so that class totals match `demand` exactly.

    Competitive greedy assignment: every (pixel, class) pair is ranked by its
    transition potential and taken in descending order, skipping pairs whose
    pixel is already assigned or whose class quota is exhausted. A pixel that
    loses every competition falls back to its current class, and any residual
    quota is filled by the highest remaining potential. This guarantees the
    Markov-derived areas are honoured to the pixel while the RF decides location.
    """
    n = potential.shape[0]
    current = lulc[mask].astype(int)
    out = np.full(n, -1, dtype=int)
    quota = demand.astype(int).copy()

    pix, cls = np.divmod(np.argsort(potential, axis=None)[::-1], N_CLASSES)
    for p, c in zip(pix, cls):
        if out[p] >= 0 or quota[c] <= 0:
            continue
        out[p] = c
        quota[c] -= 1
        if quota.sum() == 0:
            break

    leftover = np.flatnonzero(out < 0)
    if leftover.size:
        # Fill any remainder by best available class, preferring persistence.
        for p in leftover:
            order = np.argsort(-potential[p])
            for c in order:
                if quota[c] > 0:
                    out[p] = c
                    quota[c] -= 1
                    break
            if out[p] < 0:
                out[p] = current[p]

    result = np.full(lulc.shape, 255, dtype="uint8")
    result[mask] = out.astype("uint8")
    return result


def step(lulc, mask, model: TransitionPotential, P: np.ndarray) -> np.ndarray:
    """Advance the map one Markov interval."""
    demand = markov.demand_from_markov(lulc, mask, P)
    pot = model.potential(lulc, mask)
    return allocate(lulc, mask, pot, demand)
