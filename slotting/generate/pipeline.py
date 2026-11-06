"""Dataset generator: master -> transactions -> events -> labelled anomalies.

Output = input tables (no labels) + a separate ground-truth table.
"""
from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

from .. import ids
from .. import config
from ..config import PARAMS, Scale, anomaly_target
from ..engine.pickpath import compute_routes
from ..engine.replenishment import demand_matrix, labour_minutes, shift_index, simulate
from ..engine.slotting import run_strategy
from .anomalies import GT, boundary_controls, inject_blocked_aisle, inject_slot_anomalies, temporary_blocks
from .demand import build_orders, derive_velocity
from .master import build_layout, build_skus, build_suppliers


def rng_for(step: int) -> np.random.Generator:
    """Independent, reproducible stream per generation step."""
    return np.random.default_rng([config.SEED, step])


def slot_frame(assign: pd.DataFrame, start_no: int, strategy: str, status: str, when: datetime,
               change_reason: str, supersedes: dict | None = None) -> pd.DataFrame:
    df = assign.copy()
    df.insert(0, "slot_id", [ids.slot_id(start_no + i) for i in range(len(df))])
    df["strategy"] = strategy
    df["status"] = status
    df["assigned_at"] = pd.Timestamp(when)
    df["released_at"] = pd.NaT
    df["supersedes_slot_id"] = df.sku_id.map(supersedes) if supersedes else None
    df["change_reason"] = change_reason
    return df[SLOT_COLS]


SLOT_COLS = ["slot_id", "sku_id", "location_id", "warehouse_id", "strategy", "status", "assigned_at", "released_at",
             "capacity_units", "min_units", "cost_s_per_day", "n_candidates", "candidate_rank", "reason",
             "supersedes_slot_id", "change_reason"]


def slot_events(slots: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in slots.itertuples(index=False):
        if r.status == "PROPOSED":
            rows.append((r.slot_id, "PROPOSED", r.assigned_at, "SYSTEM"))
            continue
        rows.append((r.slot_id, "CREATED", r.assigned_at, "PLANNER" if r.change_reason == "INITIAL" else "OPERATOR"))
        rows.append((r.slot_id, "ACTIVATED", r.assigned_at, "SYSTEM"))
        if pd.notna(r.released_at):
            rows.append((r.slot_id, "RELEASED", r.released_at, "OPERATOR"))
    ev = pd.DataFrame(rows, columns=["slot_id", "event_type", "event_at", "actor_role"])
    ev = ev.sort_values(["event_at", "slot_id"], kind="stable").reset_index(drop=True)
    ev.insert(0, "event_id", [f"SEV-{i + 1:07d}" for i in range(len(ev))])
    return ev


def generate(scale: Scale, log=print) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    p = PARAMS
    gt = GT()

    log("1/7 master data: suppliers, warehouses, zones, locations")
    suppliers = build_suppliers(scale, rng_for(1))
    warehouses, zones, locations, blocks = build_layout(scale, rng_for(2))
    skus, profiles = build_skus(scale, warehouses, suppliers, rng_for(3))
    compat = pd.DataFrame([{"rule_id": f"CMP-{i + 1:03d}", "class_a": a, "class_b": b, "scope": "SAME_BAY",
                            "rule": "SEGREGATE"} for i, (a, b) in enumerate(p.incompatible_pairs)])

    log("2/7 orders and order lines (Zipf velocity, peak-week shift)")
    orders, lines, _seasonal = build_orders(scale, skus, profiles, rng_for(4))
    profiles = derive_velocity(skus, profiles, orders, lines)
    prof_cur = profiles[profiles.is_current].reset_index(drop=True)

    log("3/7 legacy (baseline) slot assignments")
    base, excs = run_strategy("BASELINE", prof_cur, skus, locations, zones, rng_for(5))
    if excs:
        raise RuntimeError(f"baseline could not slot {len(excs)} SKUs; generator capacity mix needs tuning")
    slots = slot_frame(base, 1, "BASELINE", "ACTIVE",
                       datetime.combine(p.baseline_slot_date, time(6, 0)), "INITIAL")

    log("4/7 inject slot anomalies (capacity, incompatible, duplicate)")
    targets = {k: anomaly_target(k, scale) for k in p.anomalies_full}
    slots = inject_slot_anomalies(slots, prof_cur, locations, zones, targets, rng_for(6), gt)

    log("5/7 pick events (S-shape routes)")
    picks, orders = _pick_events(orders, lines, slots, locations, rng_for(7))
    picks = inject_blocked_aisle(picks, blocks, targets["PICK_PATH_USES_BLOCKED_AISLE"], rng_for(8), gt)
    blocks = temporary_blocks(blocks, locations, zones, picks, rng_for(10), gt)
    lines = lines.copy()
    lines.loc[lines.line_status == "OPEN", "line_status"] = "PICKED"

    log("6/7 replenishment workload and labour roster")
    repl, roster = _replenishment(picks, slots, prof_cur, skus, warehouses, rng_for(9), gt)

    log("7/7 slot events and negative controls")
    events = slot_events(slots)
    boundary_controls(slots, prof_cur, locations, roster, repl, gt)

    tables = {
        "suppliers": suppliers, "warehouses": warehouses, "zones": zones, "aisle_blocks": blocks,
        "locations": locations, "compatibility_rules": compat, "skus": skus, "sku_profiles": profiles,
        "orders": orders, "order_lines": lines, "slot_assignments": slots, "slot_events": events,
        "pick_events": picks, "replenishments": repl, "labour_roster": roster,
    }
    return tables, gt.frame()


def _pick_events(orders, lines, slots, locations, rng):
    p = PARAMS
    active = slots[slots.status == "ACTIVE"][["sku_id", "slot_id", "location_id"]]
    live = lines[lines.line_status == "OPEN"].merge(active, on="sku_id", how="left")
    if live.slot_id.isna().any():
        raise RuntimeError("order line references a SKU without an active slot")
    live = live.merge(locations[["location_id", "aisle", "x_m", "y_m", "warehouse_id"]], on="location_id")
    per_line, per_order = compute_routes(live)
    live = live.merge(per_line, on="order_line_id")
    live = live.sort_values(["order_id", "seq"], kind="stable").reset_index(drop=True)

    sec = live.travel_m / p.walk_speed_mps + p.pick_seconds_per_line + p.pick_seconds_per_unit * live.qty
    live["pick_seconds"] = sec.round(1)
    o = orders.set_index("order_id")
    shipped = o.status == "SHIPPED"
    rel = o.created_at + pd.to_timedelta(rng.integers(2, 20, len(o)), unit="m")
    o["released_at"] = rel.where(shipped)
    live["picked_at"] = (o.released_at.reindex(live.order_id).to_numpy()
                         + pd.to_timedelta(live.groupby("order_id").pick_seconds.cumsum(), unit="s").to_numpy())
    live["picked_at"] = pd.to_datetime(live.picked_at).dt.floor("s")
    live["pick_id"] = [ids.pick_id(oid, s) for oid, s in zip(live.order_id, live.seq)]
    n_pickers = 8
    pk = rng.integers(1, n_pickers + 1, len(o))
    o["picker_id"] = [f"PKR-{w[3:]}-{k:02d}" for w, k in zip(o.warehouse_id, pk)]
    live["picker_id"] = o.picker_id.reindex(live.order_id).to_numpy()
    live["status"] = "PICKED"

    po = per_order.set_index("order_id")
    o["pick_distance_m"] = po.distance_m
    o["return_leg_m"] = po.return_leg_m
    last = live.groupby("order_id").picked_at.max()
    o["picked_at"] = (last + pd.to_timedelta(po.return_leg_m / p.walk_speed_mps, unit="s")).dt.floor("s")
    o["shipped_at"] = o.picked_at + pd.to_timedelta(rng.integers(30, 240, len(o)), unit="m")
    o.loc[~shipped, ["picked_at", "shipped_at", "picker_id"]] = None
    orders = o.reset_index()[["order_id", "warehouse_id", "carrier_id", "priority", "created_at", "week_no", "shift",
                              "status", "line_count", "total_units", "released_at", "picker_id", "picked_at",
                              "shipped_at", "cancelled_at", "pick_distance_m", "return_leg_m"]]
    picks = live[["pick_id", "order_id", "order_line_id", "sku_id", "slot_id", "location_id", "warehouse_id",
                  "picker_id", "seq", "qty", "travel_m", "route_aisles", "pick_seconds", "picked_at", "status"]]
    return picks, orders


def _replenishment(picks, slots, prof_cur, skus, warehouses, rng, gt: GT):
    p = PARAMS
    active = slots[slots.status == "ACTIVE"].set_index("sku_id")
    sku_ids = list(skus.sku_id)
    pk = picks[["sku_id", "qty"]].copy()
    pk["shift_idx"] = shift_index(picks.picked_at)
    D = demand_matrix(pk, sku_ids)
    prof = prof_cur.set_index("sku_id").loc[sku_ids]
    cap = np.maximum(active.capacity_units.reindex(sku_ids).to_numpy(float), prof.case_qty.to_numpy(float))
    trips, qty = simulate(D, cap)
    mins = labour_minutes(trips, qty)

    s_idx, t_idx = np.nonzero(trips)
    home = skus.home_warehouse_id.to_numpy()
    start = pd.Timestamp(p.horizon_start)
    shift_start = start + pd.to_timedelta(t_idx // 2, unit="D") + pd.to_timedelta(np.where(t_idx % 2 == 0, 6, 14), unit="h")
    repl = pd.DataFrame({
        "warehouse_id": home[s_idx], "sku_id": np.array(sku_ids)[s_idx],
        "slot_id": active.slot_id.reindex(sku_ids).to_numpy()[s_idx],
        "to_location_id": active.location_id.reindex(sku_ids).to_numpy()[s_idx],
        "from_area": "RESERVE",
        "shift_date": shift_start.normalize().strftime("%Y-%m-%d"),
        "shift": np.where(t_idx % 2 == 0, "AM", "PM"),
        "qty_units": qty[s_idx, t_idx].astype(int), "trips": trips[s_idx, t_idx],
        "labour_minutes": mins[s_idx, t_idx],
        "priority": prof.velocity_class.to_numpy()[s_idx],
        "triggered_at": shift_start + pd.to_timedelta(rng.integers(5, 120, len(s_idx)), unit="m"),
    })
    repl["roster_id"] = [ids.roster_id(w, d, s) for w, d, s in zip(repl.warehouse_id, repl.shift_date, repl["shift"])]

    # labour roster: planned minutes from normal-period workload, plus injected staff shortages
    load = repl.groupby("roster_id").labour_minutes.sum()
    T = trips.shape[1]
    rows = []
    for wid in warehouses.warehouse_id:
        for t in range(T):
            d = (start + pd.Timedelta(days=t // 2)).strftime("%Y-%m-%d")
            sh = "AM" if t % 2 == 0 else "PM"
            week = t // 14 + 1
            rows.append((ids.roster_id(wid, d, sh), wid, d, sh, week in p.peak_weeks))
    roster = pd.DataFrame(rows, columns=["roster_id", "warehouse_id", "shift_date", "shift", "is_peak"])
    roster["workload"] = roster.roster_id.map(load).fillna(0.0)
    planned = roster[~roster.is_peak].groupby("warehouse_id").workload.quantile(0.90) * p.roster_headroom
    planned = (np.ceil(planned / 30) * 30).clip(lower=60)
    roster["planned_minutes"] = roster.warehouse_id.map(planned).astype(int)
    short = (rng.random(len(roster)) < p.staff_shortage_share) & (~roster.is_peak) & (roster.workload > 0)
    roster["staffed_minutes"] = np.where(short, np.floor(roster.planned_minutes * p.staff_shortage_factor),
                                         roster.planned_minutes).astype(int)
    roster["roster_status"] = np.where(short, "SHORT_STAFFED", "STAFFED")
    roster["team"] = "REPLENISHMENT"

    # task status: A first, then larger jobs; cumulative minutes beyond staffed capacity -> DEFERRED
    staffed = roster.set_index("roster_id").staffed_minutes
    repl["_p"] = repl.priority.map({"A": 0, "B": 1, "C": 2})
    repl = repl.sort_values(["roster_id", "_p", "labour_minutes", "sku_id"], ascending=[True, True, False, True],
                            kind="stable")
    cum = repl.groupby("roster_id").labour_minutes.cumsum()
    ok = cum <= repl.roster_id.map(staffed)
    repl["status"] = np.where(ok, "COMPLETED", "DEFERRED")
    repl["completed_at"] = (repl.triggered_at + pd.to_timedelta(repl.labour_minutes, unit="m")).dt.floor("s").where(ok)
    repl = repl.sort_values(["triggered_at", "sku_id"], kind="stable").reset_index(drop=True)
    repl.insert(0, "repl_id", [ids.repl_id(i + 1) for i in range(len(repl))])
    repl = repl[["repl_id", "warehouse_id", "sku_id", "slot_id", "to_location_id", "from_area", "roster_id",
                 "shift_date", "shift", "qty_units", "trips", "labour_minutes", "priority", "status",
                 "triggered_at", "completed_at"]]

    over = roster[roster.workload > roster.staffed_minutes]
    for r in over.itertuples(index=False):
        sub = "STAFF_SHORTAGE" if r.roster_status == "SHORT_STAFFED" else ("PEAK_DEMAND" if r.is_peak else "DEMAND_SPIKE")
        gt.add("REPLENISHMENT_EXCEEDS_LABOR_CAPACITY", "LabourRoster", r.roster_id, r.warehouse_id, subtype=sub,
               note=f"workload {r.workload:.0f} min vs staffed {r.staffed_minutes} min")
    roster = roster.drop(columns=["is_peak", "workload"])
    return repl, roster
