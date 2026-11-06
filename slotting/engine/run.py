"""Slotting engine: optimize, simulate, compare and explain.

Consumes only the input tables (never ground truth). Produces proposed slot
assignments (new PROPOSED records, nothing overwritten), baseline vs
optimized pick-path and replenishment comparisons, KPIs and exceptions.
"""
from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

from ..config import PARAMS, SEED
from ..generate.pipeline import slot_events, slot_frame
from .exceptions import ACTIONS, detect, slot_violations
from .pickpath import compute_routes
from .replenishment import demand_matrix, labour_minutes, shift_index, simulate
from .slotting import run_strategy


def training_velocity(prof_cur, skus, orders, lines) -> pd.DataFrame:
    """Re-derive velocity from training weeks only, so evaluation on later weeks is out-of-sample."""
    from ..generate.demand import abc
    p = PARAMS
    tr = lines[lines.line_status != "CANCELLED"].merge(orders[["order_id", "week_no"]], on="order_id")
    tr = tr[tr.week_no <= p.train_weeks]
    days = p.train_weeks * 7
    g = tr.groupby("sku_id")
    picks = g.size().reindex(skus.sku_id, fill_value=0)
    units = g.qty.sum().reindex(skus.sku_id, fill_value=0)
    home = skus.set_index("sku_id").home_warehouse_id
    out = prof_cur.copy().set_index("sku_id")
    out["picks_per_day"] = (picks / days).reindex(out.index)
    out["units_per_day"] = (units / days).reindex(out.index)
    out["velocity_class"] = abc(picks.astype(float), home).reindex(out.index)
    return out.reset_index()


def _labour_hours(dist_m: float, lines: int, units: int) -> float:
    p = PARAMS
    return (dist_m / p.walk_speed_mps + lines * p.pick_seconds_per_line + units * p.pick_seconds_per_unit) / 3600


def optimize(tables: dict) -> dict:
    p = PARAMS
    skus, locs, zones = tables["skus"], tables["locations"], tables["zones"]
    prof_cur = tables["sku_profiles"][tables["sku_profiles"].is_current].reset_index(drop=True)
    slots = tables["slot_assignments"]
    picks = tables["pick_events"]
    orders = tables["orders"]

    # ---- 1. optimized proposal (velocity learned on training weeks only) --
    train_prof = training_velocity(prof_cur, skus, orders, tables["order_lines"])
    active = slots[slots.status == "ACTIVE"]
    current = dict(zip(active.sku_id, active.location_id))
    opt, opt_exc = run_strategy("OPTIMIZED", train_prof, skus, locs, zones, np.random.default_rng([SEED, 100]),
                                current=current)
    supersedes = dict(zip(active.sku_id, active.slot_id))
    proposals = slot_frame(opt, len(slots) + 1, "OPTIMIZED", "PROPOSED",
                           datetime.combine(p.reslot_proposal_date, time(9, 0)), "RESLOT", supersedes)
    extra = opt.set_index("sku_id")[["cost_current_s_per_day", "is_move", "move_reason"]]
    proposals = proposals.join(extra, on="sku_id")
    proposals["saving_s_per_day"] = (proposals.cost_current_s_per_day - proposals.cost_s_per_day).round(2)
    proposals["train_velocity_class"] = proposals.sku_id.map(train_prof.set_index("sku_id").velocity_class)
    proposal_events = slot_events(proposals)
    proposal_events["event_id"] = [f"SEV-P{i + 1:06d}" for i in range(len(proposal_events))]

    # constraint check of the proposal as if it were activated
    as_active = proposals.assign(status="ACTIVE")
    viol = slot_violations(as_active, prof_cur, locs, zones)

    # ---- 2. pick paths: same orders, baseline vs optimized locations ------
    loc_xy = locs.set_index("location_id")[["aisle", "x_m", "y_m"]]
    base_lines = picks[["order_id", "order_line_id", "sku_id", "qty", "location_id", "warehouse_id"]].join(
        loc_xy, on="location_id")
    opt_loc = dict(zip(proposals.sku_id, proposals.location_id))
    opt_lines = base_lines.drop(columns=["aisle", "x_m", "y_m"]).assign(
        location_id=base_lines.sku_id.map(opt_loc)).join(loc_xy, on="location_id")
    if opt_lines.location_id.isna().any():
        opt_lines = opt_lines.dropna(subset=["location_id"])
    _, base_o = compute_routes(base_lines)
    _, opt_o = compute_routes(opt_lines)
    units = picks.groupby("order_id").qty.sum()
    cmp_ = base_o.merge(opt_o, on="order_id", suffixes=("_baseline", "_optimized"))
    cmp_ = cmp_.join(orders.set_index("order_id")[["warehouse_id", "week_no", "shift"]], on="order_id")
    cmp_["units"] = cmp_.order_id.map(units)
    cmp_["is_peak"] = cmp_.week_no.isin(p.peak_weeks)
    cmp_["is_holdout"] = cmp_.week_no > p.train_weeks
    cmp_ = cmp_.rename(columns={"lines_baseline": "lines"}).drop(columns=["lines_optimized"])
    cmp_["saving_m"] = (cmp_.distance_m_baseline - cmp_.distance_m_optimized).round(2)

    # ---- 3. replenishment: same demand, baseline vs optimized capacity ----
    sku_ids = list(skus.sku_id)
    pk = picks[["sku_id", "qty"]].assign(shift_idx=shift_index(picks.picked_at))
    D = demand_matrix(pk, sku_ids)
    case = prof_cur.set_index("sku_id").case_qty.reindex(sku_ids).to_numpy(float)
    home = skus.home_warehouse_id.to_numpy()
    roster = tables["labour_roster"]
    start = pd.Timestamp(p.horizon_start)
    T = D.shape[1]
    rid = np.array([[f"RST-{w[3:]}-{(start + pd.Timedelta(days=t // 2)).strftime('%Y%m%d')}-{'AM' if t % 2 == 0 else 'PM'}"
                     for t in range(T)] for w in sorted(set(home))])
    wh_pos = {w: i for i, w in enumerate(sorted(set(home)))}
    rep = {}
    for name, cap_src in (("baseline", active.set_index("sku_id").capacity_units),
                          ("optimized", proposals.set_index("sku_id").capacity_units)):
        cap = np.maximum(cap_src.reindex(sku_ids).fillna(0).to_numpy(float), case)
        trips, qty = simulate(D, cap)
        mins = labour_minutes(trips, qty)
        wl = np.zeros((len(wh_pos), T))
        tr = np.zeros((len(wh_pos), T))
        for w, i in wh_pos.items():
            m = home == w
            wl[i] = mins[m].sum(axis=0)
            tr[i] = trips[m].sum(axis=0)
        rep[name] = (wl, tr)
    rs = roster.set_index("roster_id")
    rows = []
    for w, i in wh_pos.items():
        for t in range(T):
            r = rid[i, t]
            rows.append((r, w, rs.at[r, "shift_date"], rs.at[r, "shift"], int(rs.at[r, "staffed_minutes"]),
                         int(rs.at[r, "planned_minutes"]), round(rep["baseline"][0][i, t], 2),
                         round(rep["optimized"][0][i, t], 2), int(rep["baseline"][1][i, t]),
                         int(rep["optimized"][1][i, t])))
    repl_cmp = pd.DataFrame(rows, columns=["roster_id", "warehouse_id", "shift_date", "shift", "staffed_minutes",
                                           "planned_minutes", "workload_baseline_min", "workload_optimized_min",
                                           "trips_baseline", "trips_optimized"])
    repl_cmp["overload_baseline"] = repl_cmp.workload_baseline_min > repl_cmp.staffed_minutes
    repl_cmp["overload_optimized"] = repl_cmp.workload_optimized_min > repl_cmp.staffed_minutes
    repl_cmp["week_no"] = (pd.to_datetime(repl_cmp.shift_date) - start).dt.days // 7 + 1
    repl_cmp["is_peak"] = repl_cmp.week_no.isin(p.peak_weeks)
    repl_cmp["is_holdout"] = repl_cmp.week_no > p.train_weeks

    # ---- 4. exceptions ---------------------------------------------------
    audit = detect(tables)
    opt_x = pd.DataFrame([dict(issue_type=e["issue_type"], entity_type="SKU", entity_id=e["sku_id"],
                               warehouse_id="", related_ids="", detail=e["detail"]) for e in opt_exc]
                         + [dict(issue_type="OPTIMIZED_RULE_VIOLATION", entity_type="SlotAssignment",
                                 entity_id=v["entity_id"], warehouse_id=v["warehouse_id"], related_ids="",
                                 detail=v["issue_type"] + ": " + v["detail"]) for v in viol],
                         columns=["issue_type", "entity_type", "entity_id", "warehouse_id", "related_ids", "detail"])
    if len(opt_x):
        opt_x["severity"] = opt_x.issue_type.map(lambda t: ACTIONS.get(t, ("HIGH", ""))[0])
        opt_x["suggested_action"] = opt_x.issue_type.map(lambda t: ACTIONS.get(t, ("", "Review optimizer"))[1])
        opt_x["source"] = "OPTIMIZER"
        opt_x.insert(0, "exception_id", [f"EXC-O{i + 1:05d}" for i in range(len(opt_x))])
        exceptions = pd.concat([audit, opt_x], ignore_index=True)
    else:
        exceptions = audit

    # ---- 5. KPIs ---------------------------------------------------------
    metrics = _metrics(cmp_, repl_cmp, proposals, active, prof_cur, locs, exceptions, viol, opt_exc)
    return {
        "slot_proposals": proposals, "slot_proposal_events": proposal_events,
        "pick_path_comparison": cmp_, "replenishment_comparison": repl_cmp,
        "exceptions": exceptions, "metrics": metrics,
    }


def _kpis(c: pd.DataFrame, r: pd.DataFrame) -> dict:
    lines, units = int(c.lines.sum()), int(c.units.sum())
    db, do = float(c.distance_m_baseline.sum()), float(c.distance_m_optimized.sum())
    hb, ho = _labour_hours(db, lines, units), _labour_hours(do, lines, units)
    rb, ro = float(r.workload_baseline_min.sum()) / 60, float(r.workload_optimized_min.sum()) / 60
    return {
        "orders": int(len(c)), "lines": lines, "units": units,
        "distance_baseline_km": round(db / 1000, 2), "distance_optimized_km": round(do / 1000, 2),
        "distance_saving_pct": round(100 * (db - do) / db, 2) if db else 0.0,
        "avg_distance_baseline_m": round(db / max(len(c), 1), 1),
        "avg_distance_optimized_m": round(do / max(len(c), 1), 1),
        "avg_aisles_baseline": round(float(c.aisles_visited_baseline.mean()), 2) if len(c) else 0,
        "avg_aisles_optimized": round(float(c.aisles_visited_optimized.mean()), 2) if len(c) else 0,
        "pick_hours_baseline": round(hb, 1), "pick_hours_optimized": round(ho, 1),
        "lines_per_hour_baseline": round(lines / hb, 1) if hb else 0,
        "lines_per_hour_optimized": round(lines / ho, 1) if ho else 0,
        "throughput_gain_pct": round(100 * (hb / ho - 1), 2) if ho else 0,
        "repl_trips_baseline": int(r.trips_baseline.sum()), "repl_trips_optimized": int(r.trips_optimized.sum()),
        "repl_hours_baseline": round(rb, 1), "repl_hours_optimized": round(ro, 1),
        "overloaded_shifts_baseline": int(r.overload_baseline.sum()),
        "overloaded_shifts_optimized": int(r.overload_optimized.sum()),
        "total_labour_hours_baseline": round(hb + rb, 1), "total_labour_hours_optimized": round(ho + ro, 1),
    }


def _metrics(cmp_, repl_cmp, proposals, active, prof_cur, locs, exceptions, viol, opt_exc) -> dict:
    overall = _kpis(cmp_, repl_cmp)
    hc, hr = cmp_[cmp_.is_holdout], repl_cmp[repl_cmp.is_holdout]
    holdout = _kpis(hc, hr)
    per_wh = {w: {"all": _kpis(cmp_[cmp_.warehouse_id == w], repl_cmp[repl_cmp.warehouse_id == w]),
                  "holdout": _kpis(hc[hc.warehouse_id == w], hr[hr.warehouse_id == w])}
              for w in sorted(cmp_.warehouse_id.unique())}
    peak = {"peak": _kpis(cmp_[cmp_.is_peak], repl_cmp[repl_cmp.is_peak]),
            "normal": _kpis(cmp_[~cmp_.is_peak], repl_cmp[~repl_cmp.is_peak])}
    # move budget curve: proposed moves ranked by modelled daily saving
    mv = proposals[proposals.is_move].sort_values("saving_s_per_day", ascending=False)
    sv = mv.saving_s_per_day.fillna(0).clip(lower=0).cumsum().to_numpy() / 3600
    steps = sorted({int(x) for x in np.linspace(0, len(mv), 21)})
    move_curve = [{"moves": k, "saving_hours_per_day": round(float(sv[k - 1]) if k else 0.0, 2)} for k in steps]
    ld = locs.set_index("location_id")
    vc = prof_cur.set_index("sku_id").velocity_class

    def slot_profile(df):
        d = df.assign(cls=df.sku_id.map(vc), dist=df.location_id.map(ld.dist_from_dock_m),
                      level=df.location_id.map(ld.level))
        return {c: {"skus": int((d.cls == c).sum()),
                    "avg_dist_m": round(float(d[d.cls == c].dist.mean()), 1) if (d.cls == c).any() else 0,
                    "golden_zone_pct": round(100 * float((d[d.cls == c].level <= 2).mean()), 1) if (d.cls == c).any() else 0}
                for c in ("A", "B", "C")}

    changed = prof_cur[prof_cur.velocity_class != prof_cur.peak_velocity_class]
    return {
        "overall": overall, "holdout": holdout, "per_warehouse": per_wh, "peak_vs_normal": peak,
        "evaluation_window": {"train_weeks": f"1-{PARAMS.train_weeks}",
                              "holdout_weeks": f"{PARAMS.train_weeks + 1}-{PARAMS.horizon_weeks}",
                              "peak_weeks": list(PARAMS.peak_weeks)},
        "move_curve": move_curve,
        "moves_by_reason": proposals.move_reason.value_counts().sort_index().to_dict(),
        "velocity_slotting": {"baseline": slot_profile(active), "optimized": slot_profile(proposals)},
        "peak_class_shift_skus": int(len(changed)),
        "constraint_violations_optimized": len(viol),
        "unslotted_skus_optimized": len(opt_exc),
        "skus_moved": int(proposals.is_move.sum()),
        "skus_total": int(len(proposals)),
        "exceptions_by_type": exceptions.issue_type.value_counts().sort_index().to_dict(),
    }
