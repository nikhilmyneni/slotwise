"""Transactions: Order and OrderLine, plus velocity metrics derived from them.

Demand model
* SKU popularity inside each warehouse follows a Zipf curve (fast and slow movers).
* Weeks 9-10 are a peak: volume x1.8 and a seasonal cohort (10% of SKUs) surges x8.
* Oversized items are ordered less often; quantities shrink with item size.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .. import ids
from ..config import PARAMS, Scale

CARRIERS = ["CARRIER-01", "CARRIER-02", "CARRIER-03", "CARRIER-04", "CARRIER-05"]
DOW_W = np.array([1.1, 1.0, 1.0, 1.0, 1.2, 0.6, 0.3])
HOUR_W = np.array([0.4, 0.8, 1.2, 1.5, 1.4, 1.0, 0.8, 0.9, 1.2, 1.4, 1.3, 1.0, 0.7, 0.5, 0.3])  # 06..20


def horizon_days() -> int:
    return PARAMS.horizon_weeks * 7


def build_orders(scale: Scale, skus: pd.DataFrame, profiles: pd.DataFrame, rng: np.random.Generator):
    p = PARAMS
    cur = profiles[profiles.is_current].set_index("sku_id").loc[skus.sku_id]
    n_target = scale.order_lines
    n_orders = int(n_target / 3.0 * 1.10)

    lpo = (1 + rng.poisson(2.0, n_orders)).clip(1, 12)
    wh_ids = np.sort(skus.home_warehouse_id.unique())
    wh_w = skus.home_warehouse_id.value_counts().reindex(wh_ids).to_numpy().astype(float)
    o_wh = rng.choice(len(wh_ids), size=n_orders, p=wh_w / wh_w.sum())

    week_w = np.array([p.peak_volume_multiplier if (k + 1) in p.peak_weeks else 1.0
                       for k in range(p.horizon_weeks)])
    week = rng.choice(p.horizon_weeks, size=n_orders, p=week_w / week_w.sum())
    dow = rng.choice(7, size=n_orders, p=DOW_W / DOW_W.sum())
    hour = 6 + rng.choice(len(HOUR_W), size=n_orders, p=HOUR_W / HOUR_W.sum())
    secs = rng.integers(0, 3600, n_orders)
    start = datetime.combine(p.horizon_start, datetime.min.time())
    created = (np.datetime64(start) + ((week * 7 + dow) * 86400 + hour * 3600 + secs).astype("timedelta64[s]"))
    is_peak = np.isin(week + 1, p.peak_weeks)

    # ---- SKU popularity --------------------------------------------------
    sku_idx_by_wh, w_norm, w_peak = {}, {}, {}
    seasonal = rng.random(len(skus)) < p.seasonal_cohort_share
    for k, wid in enumerate(wh_ids):
        idx = np.flatnonzero(skus.home_warehouse_id.to_numpy() == wid)
        rank = rng.permutation(len(idx))
        w = 1.0 / (rank + 1.0) ** p.zipf_exponent
        w = np.where(cur.is_oversized.to_numpy()[idx], w * 0.3, w)
        wp = np.where(seasonal[idx], w * p.seasonal_boost, w)
        sku_idx_by_wh[k], w_norm[k], w_peak[k] = idx, w / w.sum(), wp / wp.sum()

    line_order = np.repeat(np.arange(n_orders), lpo)
    line_sku = np.empty(len(line_order), dtype=int)
    l_wh, l_peak = o_wh[line_order], is_peak[line_order]
    for k in range(len(wh_ids)):
        for peak, w in ((False, w_norm[k]), (True, w_peak[k])):
            m = (l_wh == k) & (l_peak == peak)
            line_sku[m] = sku_idx_by_wh[k][rng.choice(len(w), size=int(m.sum()), p=w)]

    lines = pd.DataFrame({"o": line_order, "s": line_sku})
    lines = lines[~lines.duplicated(["o", "s"])]                       # one line per SKU per order

    # chronological order numbering, then cut at exactly n_target lines
    o_rank = np.empty(n_orders, dtype=int)
    o_rank[np.lexsort((np.arange(n_orders), created))] = np.arange(n_orders)
    lines["r"] = o_rank[lines.o.to_numpy()]
    lines = lines.sort_values(["r"], kind="stable").iloc[:n_target].reset_index(drop=True)
    kept = np.sort(lines.r.unique())
    new_num = {r: i + 1 for i, r in enumerate(kept)}
    rank_to_o = np.empty(n_orders, dtype=int)
    rank_to_o[o_rank] = np.arange(n_orders)

    oi = rank_to_o[kept]
    order_ids = [ids.order_id(i + 1) for i in range(len(kept))]
    n_ord = len(kept)
    cancelled = rng.random(n_ord) < p.cancel_share
    created_k = pd.to_datetime(created[oi])
    orders = pd.DataFrame({
        "order_id": order_ids,
        "warehouse_id": wh_ids[o_wh[oi]],
        "carrier_id": rng.choice(CARRIERS, n_ord),
        "priority": np.where(rng.random(n_ord) < 0.15, "EXPRESS", "STANDARD"),
        "created_at": created_k,
        "week_no": week[oi] + 1,
        "shift": np.where(created_k.hour < 14, "AM", "PM"),
        "status": np.where(cancelled, "CANCELLED", "SHIPPED"),
        "cancelled_at": pd.NaT,
    })
    orders.loc[cancelled, "cancelled_at"] = orders.loc[cancelled, "created_at"] + pd.to_timedelta(
        rng.integers(5, 60, int(cancelled.sum())), unit="m")

    lines["order_id"] = [order_ids[new_num[r] - 1] for r in lines.r]
    lines["line_no"] = lines.groupby("r").cumcount() + 1
    lines["order_line_id"] = [ids.order_line_id(o, n) for o, n in zip(lines.order_id, lines.line_no)]
    lines["sku_id"] = skus.sku_id.to_numpy()[lines.s.to_numpy()]
    vol = (cur.length_cm * cur.width_cm * cur.height_cm).to_numpy()[lines.s.to_numpy()]
    lam = np.where(vol < 1000, 3.0, np.where(vol < 8000, 1.2, 0.3))
    qty = 1 + rng.poisson(lam)
    qty = np.where(cur.is_oversized.to_numpy()[lines.s.to_numpy()], 1, qty)
    lines["qty"] = qty
    o_status = dict(zip(orders.order_id, orders.status))
    lines["line_status"] = np.where(lines.order_id.map(o_status) == "CANCELLED", "CANCELLED", "OPEN")
    lines = lines[["order_line_id", "order_id", "line_no", "sku_id", "qty", "line_status"]]

    agg = lines.groupby("order_id").agg(line_count=("qty", "size"), total_units=("qty", "sum"))
    orders = orders.join(agg, on="order_id")
    return orders, lines, pd.Series(seasonal, index=skus.sku_id)


def abc(picks: pd.Series, groups: pd.Series) -> pd.Series:
    """A/B/C by cumulative pick share inside each warehouse."""
    a_cut, b_cut = PARAMS.abc_cutoffs
    out = pd.Series("C", index=picks.index)
    for _, idx in groups.groupby(groups).groups.items():
        s = picks.loc[idx].sort_values(ascending=False, kind="stable")
        tot = s.sum()
        if tot <= 0:
            continue
        cum = s.cumsum() / tot
        prev = cum.shift(fill_value=0.0)          # share before this SKU
        out.loc[s.index[prev < a_cut]] = "A"
        out.loc[s.index[(prev >= a_cut) & (prev < b_cut)]] = "B"
    return out


def derive_velocity(skus: pd.DataFrame, profiles: pd.DataFrame, orders: pd.DataFrame,
                    lines: pd.DataFrame) -> pd.DataFrame:
    """Velocity metrics on the current profile row, derived only from order lines."""
    p = PARAMS
    live = lines[lines.line_status != "CANCELLED"].merge(orders[["order_id", "week_no"]], on="order_id")
    live["peak"] = live.week_no.isin(p.peak_weeks)
    days = horizon_days()
    peak_days = len(p.peak_weeks) * 7
    g = live.groupby("sku_id")
    picks = g.size().reindex(skus.sku_id, fill_value=0)
    units = g.qty.sum().reindex(skus.sku_id, fill_value=0)
    peak_picks = live[live.peak].groupby("sku_id").size().reindex(skus.sku_id, fill_value=0)
    norm_picks = picks - peak_picks
    home = skus.set_index("sku_id").home_warehouse_id

    vel = pd.DataFrame({
        "picks_total": picks,
        "units_total": units,
        "picks_per_day": (picks / days).round(4),
        "units_per_day": (units / days).round(4),
        "peak_picks_per_day": (peak_picks / peak_days).round(4),
        "normal_picks_per_day": (norm_picks / (days - peak_days)).round(4),
        "velocity_class": abc(picks.astype(float), home),
        "peak_velocity_class": abc(peak_picks.astype(float), home),
    })
    prof = profiles.copy()
    prof = prof.join(vel, on="sku_id")
    hist = ~prof.is_current
    for c in vel.columns:
        prof.loc[hist, c] = None
    return prof
