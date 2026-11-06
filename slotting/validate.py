"""Dataset validation: integrity checks must PASS; business-rule findings must
match the labelled anomalies (reported as FINDING, reconciled to ground truth)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ids
from .config import PARAMS, Scale

PK = {
    "suppliers": "supplier_id", "warehouses": "warehouse_id", "zones": "zone_id", "aisle_blocks": "block_id",
    "locations": "location_id", "compatibility_rules": "rule_id", "skus": "sku_id", "sku_profiles": "profile_id",
    "orders": "order_id", "order_lines": "order_line_id", "slot_assignments": "slot_id", "slot_events": "event_id",
    "pick_events": "pick_id", "replenishments": "repl_id", "labour_roster": "roster_id",
}
FK = [  # child, column, parent, nullable
    ("zones", "warehouse_id", "warehouses", False), ("aisle_blocks", "warehouse_id", "warehouses", False),
    ("aisle_blocks", "zone_id", "zones", False), ("locations", "zone_id", "zones", False),
    ("locations", "warehouse_id", "warehouses", False), ("skus", "supplier_id", "suppliers", False),
    ("skus", "home_warehouse_id", "warehouses", False), ("sku_profiles", "sku_id", "skus", False),
    ("orders", "warehouse_id", "warehouses", False), ("order_lines", "order_id", "orders", False),
    ("order_lines", "sku_id", "skus", False), ("slot_assignments", "sku_id", "skus", False),
    ("slot_assignments", "location_id", "locations", False), ("slot_assignments", "warehouse_id", "warehouses", False),
    ("slot_assignments", "supersedes_slot_id", "slot_assignments", True), ("slot_events", "slot_id", "slot_assignments", False),
    ("pick_events", "order_id", "orders", False), ("pick_events", "order_line_id", "order_lines", False),
    ("pick_events", "sku_id", "skus", False), ("pick_events", "slot_id", "slot_assignments", False),
    ("pick_events", "location_id", "locations", False), ("replenishments", "sku_id", "skus", False),
    ("replenishments", "slot_id", "slot_assignments", False), ("replenishments", "to_location_id", "locations", False),
    ("replenishments", "roster_id", "labour_roster", False), ("labour_roster", "warehouse_id", "warehouses", False),
]
ENUMS = {
    ("zones", "zone_type"): {"AMBIENT", "BULK", "CHILLED", "FROZEN", "HAZMAT"},
    ("zones", "temp_class"): {"AMBIENT", "CHILLED", "FROZEN"},
    ("locations", "status"): {"ACTIVE", "BLOCKED"},
    ("locations", "level"): {1, 2, 3},
    ("sku_profiles", "temp_class"): {"AMBIENT", "CHILLED", "FROZEN"},
    ("sku_profiles", "hazard_class"): {"NONE", *PARAMS.hazard_classes},
    ("orders", "status"): {"SHIPPED", "CANCELLED"},
    ("orders", "priority"): {"STANDARD", "EXPRESS"},
    ("orders", "shift"): {"AM", "PM"},
    ("order_lines", "line_status"): {"PICKED", "CANCELLED"},
    ("slot_assignments", "status"): {"ACTIVE", "RELEASED", "PROPOSED"},
    ("slot_assignments", "strategy"): {"BASELINE", "OPTIMIZED"},
    ("slot_assignments", "change_reason"): {"INITIAL", "LEGACY_MOVE", "RESLOT"},
    ("slot_events", "event_type"): {"CREATED", "ACTIVATED", "RELEASED", "PROPOSED"},
    ("replenishments", "status"): {"COMPLETED", "DEFERRED"},
    ("replenishments", "shift"): {"AM", "PM"},
    ("labour_roster", "roster_status"): {"STAFFED", "SHORT_STAFFED"},
}
ID_COLS = {
    ("warehouses", "warehouse_id"): "warehouse_id", ("zones", "zone_id"): "zone_id",
    ("locations", "location_id"): "location_id", ("skus", "sku_id"): "sku_id",
    ("sku_profiles", "profile_id"): "profile_id", ("orders", "order_id"): "order_id",
    ("order_lines", "order_line_id"): "order_line_id", ("pick_events", "pick_id"): "pick_id",
    ("slot_assignments", "slot_id"): "slot_id", ("replenishments", "repl_id"): "repl_id",
}
LEAK_WORDS = ("issue_type", "ground_truth", "is_anomaly", "label", "gt_id")


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, category, name, bad, detail="", status=None, sample=None):
        bad = int(bad)
        self.rows.append({"category": category, "check": name, "status": status or ("PASS" if bad == 0 else "FAIL"),
                          "violations": bad, "detail": detail, "sample": [str(x) for x in (list(sample) if sample is not None else [])][:5]})


def validate(t: dict[str, pd.DataFrame], gt: pd.DataFrame, scale: Scale, results: dict | None = None) -> dict:
    c = Checks()

    # ---- volume ----------------------------------------------------------
    for tbl, want in (("warehouses", scale.warehouses), ("locations", scale.locations),
                      ("skus", scale.skus), ("order_lines", scale.order_lines)):
        c.add("volume", f"{tbl}: exactly {want:,} rows", len(t[tbl]) != want, f"actual {len(t[tbl]):,}")

    # ---- primary keys and ID formats ------------------------------------
    for tbl, pk in PK.items():
        dup = t[tbl][pk].duplicated()
        c.add("primary_key", f"{tbl}.{pk} unique and not null", dup.sum() + t[tbl][pk].isna().sum(),
              sample=t[tbl][pk][dup])
    for (tbl, col), pat in ID_COLS.items():
        bad = ~t[tbl][col].astype(str).str.match(ids.PATTERNS[pat])
        c.add("id_format", f"{tbl}.{col} matches {ids.PATTERNS[pat].pattern}", bad.sum(), sample=t[tbl][col][bad])
    pk_ord = t["pick_events"]
    bad = ~(pk_ord.pick_id.str.slice(5, 20) == pk_ord.order_id)
    c.add("id_format", "pick_id embeds its parent order_id (PICK-<order-id>-NNN)", bad.sum(), sample=pk_ord.pick_id[bad])
    lz = t["locations"]
    bad = ~(lz.location_id.str.slice(4, 13) == lz.zone_id)
    c.add("id_format", "location_id embeds its zone_id (LOC-<zone-id>-NNNNNN)", bad.sum(), sample=lz.location_id[bad])

    # ---- foreign keys ----------------------------------------------------
    for child, col, parent, nullable in FK:
        v = t[child][col]
        if nullable:
            v = v.dropna()
        bad = ~v.isin(t[parent][PK[parent]])
        c.add("foreign_key", f"{child}.{col} -> {parent}.{PK[parent]}", bad.sum(), sample=v[bad])
    loc_wh = t["locations"].set_index("location_id").warehouse_id
    for tbl, col in (("slot_assignments", "location_id"), ("pick_events", "location_id")):
        bad = t[tbl][col].map(loc_wh) != t[tbl].warehouse_id
        c.add("join", f"{tbl}: warehouse_id consistent with location's warehouse", bad.sum())
    home = t["skus"].set_index("sku_id").home_warehouse_id
    ol = t["order_lines"].merge(t["orders"][["order_id", "warehouse_id"]], on="order_id")
    c.add("join", "order_lines: SKU stocked in the order's warehouse", (ol.sku_id.map(home) != ol.warehouse_id).sum())

    # ---- enums -----------------------------------------------------------
    for (tbl, col), allowed in ENUMS.items():
        bad = ~t[tbl][col].isin(allowed)
        c.add("enum", f"{tbl}.{col} in {sorted(map(str, allowed))}", bad.sum(), sample=t[tbl][col][bad])

    # ---- date ordering ---------------------------------------------------
    o = t["orders"]
    s = o[o.status == "SHIPPED"]
    c.add("date_order", "orders: created <= released <= picked <= shipped",
          (~((s.created_at <= s.released_at) & (s.released_at <= s.picked_at) & (s.picked_at <= s.shipped_at))).sum())
    cx = o[o.status == "CANCELLED"]
    c.add("date_order", "cancelled orders: cancelled_at >= created_at", (cx.cancelled_at < cx.created_at).sum())
    start = pd.Timestamp(PARAMS.horizon_start)
    end = start + pd.Timedelta(weeks=PARAMS.horizon_weeks)
    c.add("date_order", "orders created inside the 12-week horizon", (~o.created_at.between(start, end)).sum())
    pe = t["pick_events"].merge(o[["order_id", "released_at", "picked_at"]], on="order_id", suffixes=("", "_o"))
    c.add("date_order", "pick_events: order released <= picked_at <= order picked",
          (~((pe.released_at <= pe.picked_at) & (pe.picked_at <= pe.picked_at_o))).sum())
    sa = t["slot_assignments"]
    r = sa.dropna(subset=["released_at"])
    c.add("date_order", "slot_assignments: assigned_at < released_at", (r.assigned_at >= r.released_at).sum())
    pr = t["sku_profiles"].dropna(subset=["effective_to"])
    c.add("date_order", "sku_profiles: effective_from < effective_to", (pr.effective_from >= pr.effective_to).sum())
    rp = t["replenishments"].dropna(subset=["completed_at"])
    c.add("date_order", "replenishments: triggered_at <= completed_at", (rp.triggered_at > rp.completed_at).sum())

    # ---- arithmetic reconciliation --------------------------------------
    lines = t["order_lines"]
    agg = lines.groupby("order_id").agg(n=("qty", "size"), u=("qty", "sum"))
    oo = o.join(agg, on="order_id")
    c.add("reconciliation", "orders.line_count = count(order_lines)", (oo.line_count != oo.n).sum())
    c.add("reconciliation", "orders.total_units = sum(order_lines.qty)", (oo.total_units != oo.u).sum())
    pt = t["pick_events"].groupby("order_id").travel_m.sum()
    so = s.join(pt.rename("legs"), on="order_id")
    c.add("reconciliation", "orders.pick_distance_m = sum(pick travel_m) + return_leg_m (±0.05 m)",
          (abs(so.legs + so.return_leg_m - so.pick_distance_m) > 0.05).sum())
    pq = t["pick_events"].merge(lines[["order_line_id", "qty"]], on="order_line_id", suffixes=("", "_l"))
    c.add("reconciliation", "pick_events.qty = order_lines.qty", (pq.qty != pq.qty_l).sum())
    rp = t["replenishments"]
    calc = (rp.trips * PARAMS.repl_minutes_per_trip + rp.qty_units * PARAMS.repl_minutes_per_unit).round(2)
    c.add("reconciliation", "replenishments.labour_minutes = trips x 6 + units x 0.05 (±0.05)",
          (abs(calc - rp.labour_minutes) > 0.05).sum())
    lc = t["locations"].groupby("warehouse_id").size()
    c.add("reconciliation", "warehouses.location_count = count(locations)",
          (t["warehouses"].set_index("warehouse_id").location_count != lc).sum())
    zc = t["locations"].groupby("zone_id").size()
    c.add("reconciliation", "zones.location_count = count(locations)",
          (t["zones"].set_index("zone_id").location_count != zc.reindex(t["zones"].zone_id).values).sum())
    cur = t["sku_profiles"][t["sku_profiles"].is_current].set_index("sku_id")
    live = lines[lines.line_status != "CANCELLED"].groupby("sku_id").size().reindex(cur.index, fill_value=0)
    c.add("reconciliation", "sku_profiles.picks_total = count(non-cancelled order lines)", (cur.picks_total != live).sum())
    c.add("reconciliation", "labour_roster.staffed_minutes <= planned_minutes",
          (t["labour_roster"].staffed_minutes > t["labour_roster"].planned_minutes).sum())

    # ---- lifecycle -------------------------------------------------------
    act = sa[(sa.status == "ACTIVE") & (sa.strategy == "BASELINE")]
    c.add("lifecycle", "exactly one ACTIVE baseline slot per SKU", (act.sku_id.value_counts() != 1).sum()
          + (~t["skus"].sku_id.isin(act.sku_id)).sum())
    rel = sa[sa.status == "RELEASED"]
    c.add("lifecycle", "every RELEASED slot is superseded by a later slot",
          (~rel.slot_id.isin(sa.supersedes_slot_id)).sum())
    ev = t["slot_events"]
    order_ok = ev.groupby("slot_id").event_type.agg(lambda x: "|".join(x))
    allowed = {"CREATED|ACTIVATED", "CREATED|ACTIVATED|RELEASED", "PROPOSED"}
    c.add("lifecycle", "slot event sequence in {CREATED>ACTIVATED[>RELEASED], PROPOSED}",
          (~order_ok.isin(allowed)).sum(), sample=order_ok[~order_ok.isin(allowed)].index)
    cancelled_picks = t["pick_events"].order_id.isin(cx.order_id).sum()
    c.add("lifecycle", "cancelled orders have no pick events", cancelled_picks)
    picked_lines = lines[lines.line_status == "PICKED"]
    c.add("lifecycle", "every PICKED order line has exactly one pick event",
          (~picked_lines.order_line_id.isin(t["pick_events"].order_line_id)).sum()
          + t["pick_events"].order_line_id.duplicated().sum())
    d = t["replenishments"]
    c.add("lifecycle", "DEFERRED replenishments have no completed_at; COMPLETED ones do",
          (d[d.status == "DEFERRED"].completed_at.notna().sum() + d[d.status == "COMPLETED"].completed_at.isna().sum()))

    # ---- duplicates ------------------------------------------------------
    c.add("duplicates", "order_lines unique per (order_id, sku_id)", lines.duplicated(["order_id", "sku_id"]).sum())
    c.add("duplicates", "one current profile per SKU", (t["sku_profiles"][t["sku_profiles"].is_current]
                                                       .sku_id.value_counts() != 1).sum())
    c.add("duplicates", "pick_events unique per (order_id, seq)", t["pick_events"].duplicated(["order_id", "seq"]).sum())

    # ---- ground-truth isolation -----------------------------------------
    leaks = [f"{k}.{col}" for k, df in t.items() for col in df.columns if any(w in col.lower() for w in LEAK_WORDS)]
    c.add("leakage", "no label/ground-truth columns in any input table", len(leaks), sample=leaks)
    exist = {"SlotAssignment": set(sa.slot_id), "PickEvent": set(t["pick_events"].pick_id),
             "LabourRoster": set(t["labour_roster"].roster_id)}
    miss = gt[[e not in exist.get(tp, set()) for tp, e in zip(gt.entity_type, gt.entity_id)]]
    c.add("leakage", "every ground-truth entity_id exists in its input table", len(miss), sample=miss.entity_id)

    # ---- business-rule findings (expected = labelled anomalies) ---------
    if results is not None:
        ex = results["exceptions"]
        for it in sorted(set(gt.issue_type) - {"NONE"}):
            n_det = int((ex[(ex.source == "DATA_AUDIT")].issue_type == it).sum())
            n_gt = int((gt.issue_type == it).sum())
            c.add("business_rule", f"{it}: detected findings reconcile to labelled anomalies", abs(n_det - n_gt),
                  detail=f"detected {n_det}, labelled {n_gt}", status="FINDING" if n_det == n_gt else "FAIL")
        m = results["metrics"]
        c.add("physical_constraints", "optimized proposal: 0 capacity / compatibility / duplicate / zone violations",
              m["constraint_violations_optimized"])
        c.add("physical_constraints", "optimized proposal: every SKU slotted", m["unslotted_skus_optimized"])
        c.add("physical_constraints", "optimized proposal never uses BLOCKED locations",
              results["slot_proposals"].location_id.map(t["locations"].set_index("location_id").status).eq("BLOCKED").sum())

    df = pd.DataFrame(c.rows)
    summary = {
        "total": len(df), "passed": int((df.status == "PASS").sum()), "failed": int((df.status == "FAIL").sum()),
        "findings": int((df.status == "FINDING").sum()),
        "by_category": df.groupby(["category", "status"]).size().unstack(fill_value=0).to_dict("index"),
        "checks": df.to_dict("records"),
    }
    return summary
