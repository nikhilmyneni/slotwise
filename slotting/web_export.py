"""Compact JSON bundle for the static web dashboard (web/public/data/<scale>/)."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PARAMS
from .export import _clean
from .schema import TABLE_INFO, dictionary
from .validate import FK, PK

AISLE_LEN = PARAMS.bays_per_aisle * PARAMS.bay_width_m


def route_points(pts: list[tuple[int, float, float]]) -> list[list[float]]:
    """Polyline of the S-shape route (same rules as engine.pickpath.route)."""
    if not pts:
        return []
    line = [[0.0, 0.0]]
    aisles = sorted({a for a, _, _ in pts})
    cur_y = 0.0
    for k, a in enumerate(aisles):
        up = k % 2 == 0
        ys = sorted([y for aa, _, y in pts if aa == a], reverse=not up)
        x = [x for aa, x, _ in pts if aa == a][0]
        edge = 0.0 if up else AISLE_LEN
        if k > 0:
            line.append([line[-1][0], edge])
        line.append([x, edge])
        for y in ys:
            line.append([x, y])
        cur_y = ys[-1]
    line.append([line[-1][0], 0.0])
    line.append([0.0, 0.0])
    _ = cur_y
    return [[round(a, 2), round(b, 2)] for a, b in line]


def _num(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else round(float(v), 3)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    d = _clean(df)
    return [{k: _num(v) for k, v in r.items()} for r in d.to_dict("records")]


def _dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), default=_num), encoding="utf-8")


def build(out_root: Path, web_dir: Path, scale_name: str, tables, gt, results, validation, evaluation,
          manifest, repro: dict | None = None):
    dest = web_dir / scale_name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    m = results["metrics"]
    t = tables
    locs, zones = t["locations"], t["zones"]
    prof = t["sku_profiles"][t["sku_profiles"].is_current].set_index("sku_id")
    skus = t["skus"].set_index("sku_id")
    slots = t["slot_assignments"]
    active = slots[slots.status == "ACTIVE"]
    props = results["slot_proposals"].set_index("sku_id")
    exc = results["exceptions"]
    cmp_ = results["pick_path_comparison"]
    rc = results["replenishment_comparison"]

    # ---------------- summary ------------------------------------------------
    weekly = cmp_.groupby("week_no").agg(orders=("order_id", "size"), base=("distance_m_baseline", "mean"),
                                         opt=("distance_m_optimized", "mean")).reset_index()
    wk_repl = rc.groupby("week_no").agg(rb=("workload_baseline_min", "sum"), ro=("workload_optimized_min", "sum"),
                                       ob=("overload_baseline", "sum"), oo=("overload_optimized", "sum")).reset_index()
    weekly = weekly.merge(wk_repl, on="week_no")
    wh_rows = []
    for w in t["warehouses"].itertuples(index=False):
        k = m["per_warehouse"].get(w.warehouse_id, {})
        wh_rows.append({"id": w.warehouse_id, "name": w.warehouse_name, "city": w.city, "region": w.region,
                        "locations": w.location_count, "skus": int((skus.home_warehouse_id == w.warehouse_id).sum()),
                        "blocked": bool(((t["aisle_blocks"].warehouse_id == w.warehouse_id) & t["aisle_blocks"].blocked_to.isna()).any()),
                        "exceptions": int((exc.warehouse_id == w.warehouse_id).sum()), "kpi": k})
    fk_rel = [{"child": c, "col": col, "parent": p, "nullable": n} for c, col, p, n in FK]
    eval_small = json.loads(json.dumps(evaluation, default=_num))
    summary = {
        "scale": scale_name, "manifest": {k: v for k, v in manifest.items() if k != "files"},
        "files": manifest["files"], "repro": repro,
        "row_counts": {k: int(len(v)) for k, v in t.items()},
        "metrics": m, "evaluation": eval_small,
        "validation": {k: v for k, v in validation.items()},
        "warehouses": wh_rows,
        "weekly": _records(weekly),
        "exceptions_by_type": exc.groupby(["issue_type", "severity"]).size().reset_index(name="n").to_dict("records"),
        "dictionary": dictionary(t), "tables": {k: {"purpose": a, "cardinality": b, "pk": PK[k]}
                                                for k, (a, b) in TABLE_INFO.items()},
        "relationships": fk_rel,
        "params": {"walk_speed_mps": PARAMS.walk_speed_mps, "repl_minutes_per_trip": PARAMS.repl_minutes_per_trip,
                   "move_cost_minutes": PARAMS.move_cost_minutes, "move_payback_days": PARAMS.move_payback_days,
                   "max_cases_per_slot": PARAMS.max_cases_per_slot, "repl_min_fill": PARAMS.repl_min_fill,
                   "abc_cutoffs": list(PARAMS.abc_cutoffs), "incompatible_pairs": [list(x) for x in PARAMS.incompatible_pairs],
                   "aisle_len_m": AISLE_LEN, "aisle_pitch_m": PARAMS.aisle_pitch_m, "bays": PARAMS.bays_per_aisle,
                   "levels": PARAMS.levels},
    }
    _dump(dest / "summary.json", summary)

    # ---------------- exceptions (operational: no ground truth) ---------------
    _dump(dest / "exceptions.json", _records(exc))
    # ---------------- ground truth (evaluation page only) ---------------------
    _dump(dest / "ground_truth.json", _records(gt))

    # ---------------- per warehouse ------------------------------------------
    base_loc = dict(zip(active.sku_id, active.location_id))
    dup_count = active.location_id.value_counts()
    for w in t["warehouses"].warehouse_id:
        lw = locs[locs.warehouse_id == w]
        sw = skus[skus.home_warehouse_id == w].index
        base_by_loc = active[active.warehouse_id == w].groupby("location_id").sku_id.apply(list).to_dict()
        opt_by_loc = props[props.warehouse_id == w].reset_index().groupby("location_id").sku_id.apply(list).to_dict()
        loc_rows = [[r.location_id, r.zone_id[-3:], int(r.aisle), int(r.bay), int(r.level), r.side, r.location_type,
                     r.status, base_by_loc.get(r.location_id, []), opt_by_loc.get(r.location_id, []),
                     float(r.dist_from_dock_m), int(r.width_cm), int(r.depth_cm), int(r.height_cm), int(r.max_weight_kg)]
                    for r in lw.itertuples(index=False)]
        sku_rows = []
        for s in sw:
            pr, pp = prof.loc[s], props.loc[s] if s in props.index else None
            bl = base_loc.get(s)
            bslot = active[active.sku_id == s].iloc[0]
            sku_rows.append({
                "id": s, "name": skus.at[s, "sku_name"], "cat": skus.at[s, "category"],
                "temp": pr.temp_class, "haz": pr.hazard_class, "over": bool(pr.is_oversized),
                "cls": pr.velocity_class, "peak_cls": pr.peak_velocity_class,
                "train_cls": None if pp is None else pp.train_velocity_class,
                "ppd": round(float(pr.picks_per_day), 3), "upd": round(float(pr.units_per_day), 3),
                "case": int(pr.case_qty), "dims": [pr.length_cm, pr.width_cm, pr.height_cm], "kg": pr.unit_weight_kg,
                "base_loc": bl, "base_slot": bslot.slot_id, "base_cap": int(bslot.capacity_units),
                "base_dup": bool(dup_count.get(bl, 0) > 1),
                "opt_loc": None if pp is None else pp.location_id, "opt_slot": None if pp is None else pp.slot_id,
                "opt_cap": None if pp is None else int(pp.capacity_units),
                "move": None if pp is None else pp.move_reason,
                "saving_s": None if pp is None else _num(pp.saving_s_per_day),
                "cost_s": None if pp is None else _num(pp.cost_s_per_day),
                "cost_cur_s": None if pp is None else _num(pp.cost_current_s_per_day),
                "ncand": None if pp is None else _num(pp.n_candidates),
                "reason": None if pp is None else pp.reason,
            })
        # sample orders: holdout, mixed sizes, plus every order with a flagged blocked-aisle pick
        cw = cmp_[(cmp_.warehouse_id == w) & cmp_.is_holdout]
        sample = pd.concat([cw[cw.lines >= 4].head(12), cw[(cw.lines >= 2) & (cw.lines < 4)].head(10),
                            cw.sort_values("saving_m", ascending=False).head(6)]).drop_duplicates("order_id")
        bad_orders = exc[(exc.issue_type == "PICK_PATH_USES_BLOCKED_AISLE") & (exc.warehouse_id == w)].related_ids.head(8)
        extra = cmp_[cmp_.order_id.isin(bad_orders)]
        sample = pd.concat([sample, extra]).drop_duplicates("order_id")
        pk = t["pick_events"]
        lxy = locs.set_index("location_id")
        orders_out = []
        for o in sample.itertuples(index=False):
            pl = pk[pk.order_id == o.order_id].sort_values("seq")
            b_pts = [(int(lxy.at[l, "aisle"]), float(lxy.at[l, "x_m"]), float(lxy.at[l, "y_m"])) for l in pl.location_id]
            o_locs = [props.at[s, "location_id"] for s in pl.sku_id]
            o_pts = [(int(lxy.at[l, "aisle"]), float(lxy.at[l, "x_m"]), float(lxy.at[l, "y_m"])) for l in o_locs]
            orders_out.append({
                "id": o.order_id, "week": int(o.week_no), "lines": int(o.lines), "units": int(o.units),
                "base_m": float(o.distance_m_baseline), "opt_m": float(o.distance_m_optimized),
                "base_route": route_points(b_pts), "opt_route": route_points(o_pts),
                "picks": [{"pick": r.pick_id, "sku": r.sku_id, "qty": int(r.qty), "base_loc": r.location_id,
                           "opt_loc": props.at[r.sku_id, "location_id"], "via": r.route_aisles, "leg": float(r.travel_m)}
                          for r in pl.itertuples(index=False)],
            })
        rw = rc[rc.warehouse_id == w]
        _dump(dest / "wh" / f"{w}.json", {
            "id": w, "zones": _records(zones[zones.warehouse_id == w]),
            "blocks": _records(t["aisle_blocks"][t["aisle_blocks"].warehouse_id == w]),
            "loc_cols": ["id", "zone", "aisle", "bay", "level", "side", "type", "status", "base", "opt", "dist",
                         "w", "d", "h", "kg"],
            "locations": loc_rows, "skus": sku_rows, "orders": orders_out,
            "repl": {"date": list(rw.shift_date), "shift": list(rw["shift"]), "staffed": [int(x) for x in rw.staffed_minutes],
                     "base": [round(float(x), 1) for x in rw.workload_baseline_min],
                     "opt": [round(float(x), 1) for x in rw.workload_optimized_min]},
            "exceptions": _records(exc[exc.warehouse_id == w]),
            "kpi": m["per_warehouse"].get(w),
        })

    # ---------------- table samples for the data explorer ---------------------
    samples = {k: {"columns": list(v.columns), "rows": _records(v.head(60)), "total": int(len(v))}
               for k, v in {**t, "slot_proposals": results["slot_proposals"]}.items()}
    _dump(dest / "samples.json", samples)

    # ---------------- downloadable dataset ------------------------------------
    zpath = dest / f"slotting-{scale_name}-dataset.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("data/csv", "ground_truth", "results"):
            for f in sorted((out_root / sub).glob("*.csv")):
                z.write(f, f"{sub}/{f.name}")
        for f in ("README.md", "manifest.json", "validation_summary.json", "DATA_DICTIONARY.md", "results/metrics.json",
                  "results/evaluation.json"):
            if (out_root / f).exists():
                z.write(out_root / f, f)
        if repro is not None and (out_root / "repro_report.json").exists():
            z.write(out_root / "repro_report.json", "repro_report.json")
    shutil.copyfile(out_root / "results" / "slot_proposals.csv", dest / "slot_proposals.csv")
    return dest
