"""Slot assignment strategies.

BASELINE  - legacy practice: SKUs placed in a random compatible free slot,
            not velocity-aware (still physically feasible).
OPTIMIZED - velocity-based greedy: SKUs are processed by constraint tier
            (oversized, hazmat, rest) then by pick frequency; each takes the
            free feasible slot with the lowest expected daily labour cost:

    cost(s, l) = picks/day(s) * 2 * (dist_from_dock(l) + level_penalty(l)) / walk_speed
               + replen_trips/day(s, l) * replen_seconds_per_trip
    - stay_bonus  (only for the SKU's current location)
    replen_trips/day = units/day(s) / (capacity(s, l) * (1 - min_fill))
    stay_bonus = move_cost_minutes * 60 / move_payback_days, so a SKU only
    moves when the daily saving pays back the move within the payback window.

Both strategies enforce the same hard constraints (candidates.py) plus
bay-level hazard segregation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PARAMS
from .candidates import capacity_matrix, compat_matrix, loc_arrays, sku_arrays


def incompatible_with(cls: str) -> set[str]:
    out = set()
    for a, b in PARAMS.incompatible_pairs:
        if cls == a:
            out.add(b)
        if cls == b:
            out.add(a)
    return out


def _tier(prof: pd.DataFrame) -> np.ndarray:
    return np.where(prof.is_oversized, 0, np.where(prof.hazard_class != "NONE", 1, 2))


def assign_warehouse(prof: pd.DataFrame, locs: pd.DataFrame, zones: pd.DataFrame,
                     strategy: str, rng: np.random.Generator, current: dict | None = None):
    """Return (assignments df, exceptions list) for one warehouse."""
    p = PARAMS
    S, L = sku_arrays(prof), loc_arrays(locs, zones)
    cap = capacity_matrix(S, L)
    feas = compat_matrix(S, L) & (cap >= S["case"][:, None])
    n_cand = feas.sum(axis=1)

    lvl_pen = np.array(p.level_penalty_m)[locs.level.to_numpy() - 1]
    walk = 2 * (locs.dist_from_dock_m.to_numpy() + lvl_pen) / p.walk_speed_mps          # s per pick
    repl_s = p.repl_minutes_per_trip * 60
    picks = prof.picks_per_day.to_numpy(float)
    units = prof.units_per_day.to_numpy(float)
    with np.errstate(divide="ignore"):
        trips = units[:, None] / np.maximum(cap * (1 - p.repl_min_fill), 1.0)
    cost = picks[:, None] * walk[None, :] + trips * repl_s
    loc_pos = pd.Series(np.arange(len(locs)), index=locs.location_id)
    cur_idx = np.array([loc_pos.get(current.get(s, ""), -1) if current else -1 for s in prof.sku_id])
    cur_cost = np.array([cost[i, c] if c >= 0 else np.nan for i, c in enumerate(cur_idx)])
    eff = cost.copy()
    if strategy == "OPTIMIZED" and current:
        bonus = p.move_cost_minutes * 60 / p.move_payback_days
        has = cur_idx >= 0
        eff[np.flatnonzero(has), cur_idx[has]] -= bonus

    tier = _tier(prof)
    if strategy == "OPTIMIZED":
        order = np.lexsort((prof.sku_id.to_numpy(), -picks, tier))
    else:
        order = np.lexsort((prof.sku_id.to_numpy(), tier))

    cur_owner = {int(c): i for i, c in enumerate(cur_idx) if c >= 0}
    taken_by_other: dict[int, bool] = {}
    bay_key = (locs.aisle.to_numpy() * 1000 + locs.bay.to_numpy())
    bay_haz: dict[int, set] = {}
    free = np.ones(len(locs), dtype=bool)
    rows, exc = [], []
    for s in order:
        ok = feas[s] & free
        haz = S["haz"][s]
        if haz != "NONE" and ok.any():
            bad = incompatible_with(haz)
            cand = np.flatnonzero(ok)
            keep = [not (bay_haz.get(bay_key[c], set()) & bad) for c in cand]
            ok = np.zeros_like(ok)
            ok[cand[np.array(keep, dtype=bool)]] = True
        if not ok.any():
            exc.append({"sku_id": prof.sku_id.iat[s], "strategy": strategy, "issue_type": "NO_FEASIBLE_SLOT",
                        "detail": f"{n_cand[s]} physically feasible locations, none free/compatible"})
            continue
        cand = np.flatnonzero(ok)
        if strategy == "OPTIMIZED":
            c = cand[np.argmin(eff[s, cand])]
        else:
            c = cand[rng.integers(0, len(cand))]
        free[c] = False
        holder = cur_owner.get(c)
        if holder is not None and holder != s:
            taken_by_other[holder] = True
        if haz != "NONE":
            bay_haz.setdefault(bay_key[c], set()).add(haz)
        rows.append((s, c, int(n_cand[s]), int(np.sum(cost[s, cand] < cost[s, c]) + 1)))

    out = []
    for s, c, nc, rank in rows:
        lr = locs.iloc[c]
        cu = int(cap[s, c])
        cover_days = cu / units[s] if units[s] > 0 else float("inf")
        stay = cur_idx[s] == c
        if strategy == "OPTIMIZED" and stay:
            reason = (f"{prof.velocity_class.iat[s]}-class, {picks[s]:.2f} picks/day: stays in place; no free feasible "
                      f"slot saves more than the move cost within {p.move_payback_days:.0f} days")
        elif strategy == "OPTIMIZED":
            reason = (f"{prof.velocity_class.iat[s]}-class, {picks[s]:.2f} picks/day: lowest labour-cost free slot "
                      f"of {nc} feasible ({lr.dist_from_dock_m:.0f} m from dock, level {lr.level}); "
                      f"holds {cu} units, {('%.1f' % cover_days) if np.isfinite(cover_days) else 'n/a'} days of cover")
        else:
            reason = f"Legacy placement: random compatible free slot ({nc} feasible), not velocity-aware"
        out.append({
            "sku_id": prof.sku_id.iat[s], "location_id": lr.location_id, "warehouse_id": lr.warehouse_id,
            "capacity_units": cu, "min_units": int(np.ceil(cu * p.repl_min_fill)),
            "cost_s_per_day": round(float(cost[s, c]), 2), "n_candidates": nc,
            "candidate_rank": rank, "reason": reason,
            "cost_current_s_per_day": round(float(cur_cost[s]), 2) if np.isfinite(cur_cost[s]) else np.nan,
            "is_move": bool(not stay),
            "move_reason": ("STAY" if stay else
                            "FORCED_CURRENT_INFEASIBLE" if (cur_idx[s] < 0 or not feas[s, cur_idx[s]]) else
                            "FORCED_CURRENT_TAKEN" if np.isfinite(cur_cost[s]) and taken_by_other.get(s, False) else
                            "LABOUR_SAVING"),
        })
    return pd.DataFrame(out), exc


def run_strategy(strategy: str, prof_cur: pd.DataFrame, skus: pd.DataFrame, locs: pd.DataFrame,
                 zones: pd.DataFrame, rng: np.random.Generator, current: dict | None = None):
    prof = prof_cur.merge(skus[["sku_id", "home_warehouse_id"]], on="sku_id")
    frames, excs = [], []
    for wid in sorted(prof.home_warehouse_id.unique()):
        pw = prof[prof.home_warehouse_id == wid].sort_values("sku_id").reset_index(drop=True)
        lw = locs[locs.warehouse_id == wid].reset_index(drop=True)
        df, exc = assign_warehouse(pw, lw, zones, strategy, rng, current)
        frames.append(df)
        excs.extend(exc)
    return pd.concat(frames, ignore_index=True), excs
