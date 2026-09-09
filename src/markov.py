"""Markov transition analysis: how much of each class converts, per interval."""
from __future__ import annotations

import numpy as np

from config import CLASS_IDS, CLASSES, N_CLASSES


def crosstab(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Pixel counts for every from-to pair. Rows = from-class, cols = to-class."""
    av, bv = a[mask].astype(int), b[mask].astype(int)
    flat = np.bincount(av * N_CLASSES + bv, minlength=N_CLASSES ** 2)
    return flat.reshape(N_CLASSES, N_CLASSES)


def transition_probabilities(counts: np.ndarray) -> np.ndarray:
    """Row-normalise a crosstab into a Markov transition probability matrix.

    A class with no pixels at the start of the interval gets an identity row:
    with no observations there is no evidence for any transition, and inventing
    a uniform distribution would fabricate change out of an empty class.
    """
    P = np.zeros((N_CLASSES, N_CLASSES), dtype=float)
    totals = counts.sum(axis=1)
    for i in range(N_CLASSES):
        if totals[i] > 0:
            P[i] = counts[i] / totals[i]
        else:
            P[i, i] = 1.0
    return P


def area_hectares(arr: np.ndarray, mask: np.ndarray, area: np.ndarray) -> dict[int, float]:
    """Area per class, summing true per-pixel areas rather than a nominal constant."""
    ha = np.bincount(arr[mask].astype(int), weights=area[mask], minlength=N_CLASSES)
    return {c: float(ha[c]) for c in CLASS_IDS}


def crosstab_area(a: np.ndarray, b: np.ndarray, mask: np.ndarray,
                  area: np.ndarray) -> np.ndarray:
    """From-to matrix in hectares."""
    av, bv = a[mask].astype(int), b[mask].astype(int)
    flat = np.bincount(av * N_CLASSES + bv, weights=area[mask],
                       minlength=N_CLASSES ** 2)
    return flat.reshape(N_CLASSES, N_CLASSES)


def project_shares(shares: np.ndarray, P: np.ndarray, steps: int = 1) -> np.ndarray:
    """Advance a class-share vector `steps` intervals through the Markov chain."""
    out = np.asarray(shares, dtype=float).copy()
    for _ in range(steps):
        out = out @ P
    return out


def demand_from_markov(current: np.ndarray, mask: np.ndarray, P: np.ndarray) -> np.ndarray:
    """Target pixel count per class after one Markov step from the current map."""
    counts = np.bincount(current[mask].astype(int), minlength=N_CLASSES).astype(float)
    target = counts @ P
    # Integerise while preserving the exact total pixel count, so allocation
    # neither creates nor destroys land.
    floor = np.floor(target).astype(int)
    remainder = int(counts.sum()) - floor.sum()
    if remainder > 0:
        order = np.argsort(-(target - floor))
        floor[order[:remainder]] += 1
    return floor


def annualise(P: np.ndarray, interval_years: int, step_years: int) -> np.ndarray:
    """Rescale a transition matrix from one interval length to another.

    Uses eigendecomposition to take the matrix root. Falls back to the raw
    matrix when the root is not a valid stochastic matrix (complex eigenvalues
    or negative entries), which happens for strongly non-Markovian data; the
    caller is told rather than being handed a silently invalid matrix.
    """
    power = step_years / interval_years
    if abs(power - 1.0) < 1e-9:
        return P
    vals, vecs = np.linalg.eig(P)
    if np.any(np.abs(vals.imag) > 1e-8) or np.any(vals.real <= 0):
        return None
    rooted = vecs @ np.diag(vals.real ** power) @ np.linalg.inv(vecs)
    rooted = rooted.real
    if rooted.min() < -1e-6:
        return None
    rooted = np.clip(rooted, 0, None)
    rooted /= rooted.sum(axis=1, keepdims=True)
    return rooted


def format_matrix(values: np.ndarray, unit: str = "ha") -> str:
    """Human-readable from-to table for the thesis appendix."""
    counts = values
    names = [CLASSES[c] for c in CLASS_IDS]
    w = max(len(n) for n in names) + 2
    head = " " * w + "".join(f"{n:>14}" for n in names) + f"{'total':>14}"
    lines = [head]
    for i, n in enumerate(names):
        row = counts[i]
        lines.append(f"{n:<{w}}" + "".join(f"{v:>14,.0f}" for v in row) + f"{row.sum():>14,.0f}")
    tot = counts.sum(axis=0)
    lines.append(f"{'total':<{w}}" + "".join(f"{v:>14,.0f}" for v in tot) + f"{tot.sum():>14,.0f}")
    lines.append(f"(values in {unit}; rows = 'from', columns = 'to')")
    return "\n".join(lines)
