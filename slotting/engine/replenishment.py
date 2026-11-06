"""Forward-slot replenishment simulation (min/max per shift).

Each SKU's pick slot starts full (capacity units). Each shift the picked units
are drawn down; whenever stock falls below min_fill x capacity, it is topped
back up to capacity from reserve. If demand inside a shift exceeds what one
fill covers, several trips are needed: trips = ceil(deficit / capacity).
Labour minutes = trips x minutes_per_trip + units x minutes_per_unit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PARAMS
from ..generate.demand import horizon_days


def shift_index(ts: pd.Series) -> np.ndarray:
    start = pd.Timestamp(PARAMS.horizon_start)
    day = (ts.dt.normalize() - start).dt.days.to_numpy()
    return day * 2 + (ts.dt.hour.to_numpy() >= 14)


def demand_matrix(picks: pd.DataFrame, sku_ids: list[str]) -> np.ndarray:
    """picks needs sku_id, qty, shift_idx. Returns SKU x shift units."""
    T = horizon_days() * 2
    pos = pd.Series(np.arange(len(sku_ids)), index=sku_ids)
    m = np.zeros((len(sku_ids), T))
    np.add.at(m, (pos.loc[picks.sku_id].to_numpy(), picks.shift_idx.to_numpy()), picks.qty.to_numpy())
    return m


def simulate(demand: np.ndarray, cap: np.ndarray):
    p = PARAMS
    cap = np.maximum(cap.astype(float), 1.0)
    stock = cap.copy()
    trips = np.zeros_like(demand, dtype=np.int64)
    qty = np.zeros_like(demand)
    lo = cap * p.repl_min_fill
    for t in range(demand.shape[1]):
        stock -= demand[:, t]
        need = stock < lo
        if need.any():
            deficit = cap[need] - stock[need]
            trips[need, t] = np.maximum(1, np.ceil(deficit / cap[need])).astype(np.int64)
            qty[need, t] = np.round(deficit)
            stock[need] = cap[need]
    return trips, qty


def labour_minutes(trips, qty):
    p = PARAMS
    return np.round(trips * p.repl_minutes_per_trip + qty * p.repl_minutes_per_unit, 2)
