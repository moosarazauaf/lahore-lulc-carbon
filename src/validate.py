"""Validation of a simulated map against the observed map for the same date.

Overall accuracy on its own is misleading for land-change models: in a district
where ~90% of pixels do not change in a decade, a model that predicts no change
anywhere scores ~90%. Everything here is therefore reported against that null
model, and the headline metric is the Figure of Merit, which ignores correctly
predicted persistence entirely.
"""
from __future__ import annotations

import numpy as np

from config import CLASSES, CLASS_IDS, N_CLASSES, PIXEL_AREA_HA


def kappa(obs: np.ndarray, sim: np.ndarray) -> tuple[float, float]:
    n = obs.size
    cm = np.bincount(obs * N_CLASSES + sim, minlength=N_CLASSES ** 2).reshape(N_CLASSES, N_CLASSES)
    po = np.trace(cm) / n
    pe = float((cm.sum(0) * cm.sum(1)).sum()) / (n * n)
    k = (po - pe) / (1 - pe) if pe < 1 else 0.0
    return float(po), float(k)


def figure_of_merit(t0: np.ndarray, obs: np.ndarray, sim: np.ndarray) -> dict:
    """Pontius Figure of Merit and its four components."""
    obs_change = obs != t0
    sim_change = sim != t0

    hits = int((obs_change & sim_change & (sim == obs)).sum())
    wrong_hits = int((obs_change & sim_change & (sim != obs)).sum())
    misses = int((obs_change & ~sim_change).sum())
    false_alarms = int((~obs_change & sim_change).sum())

    denom = hits + wrong_hits + misses + false_alarms
    fom = hits / denom if denom else 0.0
    return {
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "wrong_hits": wrong_hits,
        "figure_of_merit": fom,
        "observed_change_px": int(obs_change.sum()),
        "simulated_change_px": int(sim_change.sum()),
    }


def disagreement(obs: np.ndarray, sim: np.ndarray) -> tuple[float, float]:
    """Pontius quantity vs allocation disagreement, as proportions.

    Quantity disagreement means the model got the *amount* of each class wrong.
    Allocation disagreement means it got the amounts right but put them in the
    wrong places. Separating them tells you whether the Markov step or the
    Random Forest is the weak link.
    """
    n = obs.size
    cm = np.bincount(obs * N_CLASSES + sim, minlength=N_CLASSES ** 2).reshape(N_CLASSES, N_CLASSES) / n
    obs_tot, sim_tot = cm.sum(1), cm.sum(0)
    quantity = float(np.abs(obs_tot - sim_tot).sum() / 2)
    total = float(1 - np.trace(cm))
    allocation = max(total - quantity, 0.0)
    return quantity, allocation


def report(t0: np.ndarray, obs: np.ndarray, sim: np.ndarray, mask: np.ndarray,
           label: str) -> dict:
    a, b, c = t0[mask].astype(int), obs[mask].astype(int), sim[mask].astype(int)

    oa, k = kappa(b, c)
    null_oa, null_k = kappa(b, a)          # persistence: predict "no change"
    fom = figure_of_merit(a, b, c)
    null_fom = figure_of_merit(a, b, a)
    q, al = disagreement(b, c)

    res = {
        "label": label,
        "overall_accuracy": oa,
        "kappa": k,
        "null_overall_accuracy": null_oa,
        "null_kappa": null_k,
        "quantity_disagreement": q,
        "allocation_disagreement": al,
        "null_figure_of_merit": null_fom["figure_of_merit"],
        **fom,
    }

    print(f"\n  VALIDATION — {label}")
    print(f"    overall accuracy      {oa:6.3f}   (null / persistence: {null_oa:6.3f})")
    print(f"    kappa                 {k:6.3f}   (null: {null_k:6.3f})")
    print(f"    FIGURE OF MERIT       {fom['figure_of_merit']:6.3f}   (null: {null_fom['figure_of_merit']:.3f})")
    print(f"      hits {fom['hits']:,}  misses {fom['misses']:,}  "
          f"false alarms {fom['false_alarms']:,}  wrong hits {fom['wrong_hits']:,}")
    print(f"    observed change  {fom['observed_change_px'] * PIXEL_AREA_HA:>12,.0f} ha")
    print(f"    simulated change {fom['simulated_change_px'] * PIXEL_AREA_HA:>12,.0f} ha")
    print(f"    quantity disagreement {q:6.3f} | allocation disagreement {al:6.3f}")

    if fom["figure_of_merit"] <= 0.0:
        print("    -> model adds nothing over predicting no change. Do not project.")
    elif fom["figure_of_merit"] < 0.10:
        print("    -> weak. Typical of published CA-Markov work, but report it plainly.")
    return res


def per_class_area_error(obs, sim, mask) -> str:
    lines = [f"{'class':<14}{'observed ha':>14}{'simulated ha':>14}{'error %':>10}"]
    b, c = obs[mask].astype(int), sim[mask].astype(int)
    for cid in CLASS_IDS:
        o = float((b == cid).sum()) * PIXEL_AREA_HA
        s = float((c == cid).sum()) * PIXEL_AREA_HA
        e = 100 * (s - o) / o if o else float("nan")
        lines.append(f"{CLASSES[cid]:<14}{o:>14,.0f}{s:>14,.0f}{e:>10.2f}")
    return "\n".join(lines)
