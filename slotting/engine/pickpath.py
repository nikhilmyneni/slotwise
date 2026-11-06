"""S-shape (traversal) pick-path model.

The dock is at (0, 0); aisle a sits at x = a * pitch and runs from the front
cross-aisle (y = 0) to the back cross-aisle (y = aisle_len). A picker visits
the aisles holding picks in ascending order, travelling up the first aisle,
down the next and so on. Distance is Manhattan along aisles/cross-aisles.
Blocked aisles never hold active slots, so a valid route never enters one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PARAMS


def route(aisles: np.ndarray, xs: np.ndarray, ys: np.ndarray, aisle_len: float):
    """Return (visit order, leg distances, leg route-aisle strings, return leg)."""
    order, legs, via = [], [], []
    cur_a, cur_x, cur_y, up = None, 0.0, 0.0, True
    for k, a in enumerate(np.unique(aisles)):
        idx = np.flatnonzero(aisles == a)
        up = (k % 2 == 0)
        idx = idx[np.argsort(ys[idx] if up else -ys[idx], kind="stable")]
        for j, i in enumerate(idx):
            if j == 0:
                if cur_a is None:
                    d = xs[i] + ys[i]
                    v = f"{a}"
                elif up:   # previous aisle went down, we are at the front
                    d = cur_y + abs(xs[i] - cur_x) + ys[i]
                    v = f"{cur_a}>{a}"
                else:      # previous aisle went up, we are at the back
                    d = (aisle_len - cur_y) + abs(xs[i] - cur_x) + (aisle_len - ys[i])
                    v = f"{cur_a}>{a}"
            else:
                d = abs(ys[i] - cur_y)
                v = f"{a}"
            order.append(i)
            legs.append(round(float(d), 2))
            via.append(v)
            cur_a, cur_x, cur_y = a, xs[i], ys[i]
    ret = round(float(cur_y + cur_x), 2) if cur_a is not None else 0.0
    return order, legs, via, ret


def compute_routes(lines: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """lines needs order_id, order_line_id, aisle, x_m, y_m.

    Returns (per-line: order_line_id, seq, travel_m, route_aisles) and
            (per-order: order_id, lines, aisles_visited, return_leg_m, distance_m).
    """
    aisle_len = PARAMS.bays_per_aisle * PARAMS.bay_width_m
    df = lines.sort_values(["order_id", "order_line_id"], kind="stable").reset_index(drop=True)
    o = df.order_id.to_numpy()
    a = df.aisle.to_numpy()
    x = df.x_m.to_numpy(float)
    y = df.y_m.to_numpy(float)
    bounds = np.flatnonzero(np.r_[True, o[1:] != o[:-1], True])
    seq = np.zeros(len(df), dtype=int)
    leg = np.zeros(len(df))
    via = np.empty(len(df), dtype=object)
    o_rows = []
    for b0, b1 in zip(bounds[:-1], bounds[1:]):
        ordr, legs, vias, ret = route(a[b0:b1], x[b0:b1], y[b0:b1], aisle_len)
        pos = b0 + np.array(ordr)
        seq[pos] = np.arange(1, len(ordr) + 1)
        leg[pos] = legs
        via[pos] = vias
        o_rows.append((o[b0], b1 - b0, len(np.unique(a[b0:b1])), ret, round(sum(legs) + ret, 2)))
    per_line = pd.DataFrame({"order_line_id": df.order_line_id, "seq": seq, "travel_m": leg, "route_aisles": via})
    per_order = pd.DataFrame(o_rows, columns=["order_id", "lines", "aisles_visited", "return_leg_m", "distance_m"])
    return per_line, per_order
