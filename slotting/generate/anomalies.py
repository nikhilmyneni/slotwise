"""Labelled edge-case injection.

All anomalies are created as *new* records (history is never overwritten):
a legacy "manual move" creates a new ACTIVE SlotAssignment and RELEASES the
previous one. Every injected case is written to ground truth with the rule
that makes it an anomaly; input tables carry no label columns.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .. import ids
from ..config import PARAMS
from ..engine.candidates import capacity_matrix, loc_arrays, sku_arrays
from ..engine.slotting import incompatible_with

RULES = {
    "SKU_EXCEEDS_LOCATION_CAPACITY": "Active slot where the SKU does not fit: dimensions exceed the location or capacity_units < case_qty",
    "INCOMPATIBLE_PRODUCTS_CO_LOCATED": "Two active slots in the same warehouse/aisle/bay hold hazard classes listed in compatibility_rules",
    "DUPLICATE_ACTIVE_LOCATION": "More than one ACTIVE slot assignment references the same location",
    "PICK_PATH_USES_BLOCKED_AISLE": "A pick-event route traverses an aisle with an ACTIVE aisle block at picked_at",
    "REPLENISHMENT_EXCEEDS_LABOR_CAPACITY": "Replenishment labour minutes in a warehouse shift exceed staffed minutes in labour_roster",
    "NONE": "Negative control: boundary case that satisfies every rule and must NOT be flagged",
}
DECISIONS = {
    "SKU_EXCEEDS_LOCATION_CAPACITY": "RESLOT_TO_FEASIBLE_LOCATION",
    "INCOMPATIBLE_PRODUCTS_CO_LOCATED": "SEGREGATE_RESLOT_LATER_ASSIGNMENT",
    "DUPLICATE_ACTIVE_LOCATION": "RELEASE_DUPLICATE_AND_RESLOT",
    "PICK_PATH_USES_BLOCKED_AISLE": "REROUTE_VIA_CROSS_AISLE",
    "REPLENISHMENT_EXCEEDS_LABOR_CAPACITY": "ADD_LABOUR_OR_DEFER_LOW_PRIORITY",
    "NONE": "NO_ACTION",
}


class GT:
    def __init__(self):
        self.rows = []

    def add(self, issue, entity_type, entity_id, wh, related="", subtype="", note=""):
        self.rows.append({
            "gt_id": f"GT-{len(self.rows) + 1:06d}", "issue_type": issue, "issue_subtype": subtype or issue,
            "entity_type": entity_type, "entity_id": entity_id, "related_ids": related, "warehouse_id": wh,
            "rule": RULES[issue], "expected_decision": DECISIONS[issue], "note": note,
        })

    def frame(self):
        return pd.DataFrame(self.rows, columns=["gt_id", "issue_type", "issue_subtype", "entity_type", "entity_id",
                                                "related_ids", "warehouse_id", "rule", "expected_decision", "note"])


def _move_time(rng) -> datetime:
    d = datetime(2025, 12, 16) + timedelta(days=int(rng.integers(0, 19)), hours=int(rng.integers(8, 18)),
                                          minutes=int(rng.integers(0, 60)))
    return d


def inject_slot_anomalies(slots: pd.DataFrame, prof_cur: pd.DataFrame, locs: pd.DataFrame,
                          zones: pd.DataFrame, targets: dict, rng: np.random.Generator, gt: GT) -> pd.DataFrame:
    prof = prof_cur.set_index("sku_id")
    locs_i = locs.set_index("location_id")
    zone_t = zones.set_index("zone_id")
    slots = slots.copy()
    new_rows = []
    active = slots[slots.status == "ACTIVE"]
    sku_slot = dict(zip(active.sku_id, active.slot_id))
    sku_loc = dict(zip(active.sku_id, active.location_id))
    occupied = set(active.location_id)
    used_skus, used_locs, used_bays = set(), set(), set()
    next_no = len(slots) + 1

    def cap_of(sku, loc_ids):
        S = sku_arrays(prof.loc[[sku]].reset_index())
        L = loc_arrays(locs_i.loc[loc_ids].reset_index(), zones)
        return capacity_matrix(S, L)[0]

    def move(sku, new_loc, issue, related=""):
        nonlocal next_no
        when = _move_time(rng)
        old = sku_slot[sku]
        slots.loc[slots.slot_id == old, ["status", "released_at"]] = ["RELEASED", when]
        sid = ids.slot_id(next_no)
        next_no += 1
        cu = int(cap_of(sku, [new_loc])[0])
        new_rows.append({
            "slot_id": sid, "sku_id": sku, "location_id": new_loc, "warehouse_id": locs_i.at[new_loc, "warehouse_id"],
            "strategy": "BASELINE", "status": "ACTIVE", "assigned_at": when, "released_at": pd.NaT,
            "capacity_units": cu, "min_units": int(np.ceil(cu * PARAMS.repl_min_fill)),
            "cost_s_per_day": np.nan, "n_candidates": np.nan, "candidate_rank": np.nan,
            "reason": "Legacy manual move by operator", "supersedes_slot_id": old, "change_reason": "LEGACY_MOVE",
        })
        sku_slot[sku] = sid
        used_skus.add(sku)
        used_locs.add(new_loc)
        gt.add(issue, "SlotAssignment", sid, locs_i.at[new_loc, "warehouse_id"], related=related,
               note=f"{sku} moved from {sku_loc[sku]} to {new_loc}")
        occupied.discard(sku_loc[sku])
        sku_loc[sku] = new_loc
        occupied.add(new_loc)
        return sid

    normal = prof[(prof.hazard_class == "NONE") & (~prof.is_oversized)].index.to_numpy()
    loc_zone_haz = zone_t.allows_hazmat.reindex(locs.zone_id).to_numpy(bool)
    loc_temp = zone_t.temp_class.reindex(locs.zone_id).to_numpy()

    # 1) SKU exceeds location capacity -----------------------------------
    n_done = 0
    for sku in rng.permutation(normal):
        if n_done >= targets["SKU_EXCEEDS_LOCATION_CAPACITY"]:
            break
        if sku in used_skus or sku not in sku_slot:
            continue
        wh = locs_i.at[sku_loc[sku], "warehouse_id"]
        m = ((locs.warehouse_id == wh) & (locs.status == "ACTIVE")).to_numpy() & ~loc_zone_haz \
            & (loc_temp == prof.at[sku, "temp_class"])
        cand = locs.location_id.to_numpy()[m]
        cand = np.array([c for c in cand if c not in occupied and c not in used_locs])
        if len(cand) == 0:
            continue
        caps = cap_of(sku, list(cand))
        bad = cand[caps < prof.at[sku, "case_qty"]]
        if len(bad) == 0:
            continue
        move(sku, bad[rng.integers(0, len(bad))], "SKU_EXCEEDS_LOCATION_CAPACITY")
        n_done += 1

    # 2) incompatible products co-located (same bay) ----------------------
    haz = prof[prof.hazard_class != "NONE"].index
    haz = [s for s in haz if s in sku_slot]
    n_done = 0
    pairs = []
    for a in haz:
        for b in haz:
            if a < b and prof.at[b, "hazard_class"] in incompatible_with(prof.at[a, "hazard_class"]) \
                    and locs_i.at[sku_loc[a], "warehouse_id"] == locs_i.at[sku_loc[b], "warehouse_id"]:
                pairs.append((a, b))
    for k in rng.permutation(len(pairs)):
        if n_done >= targets["INCOMPATIBLE_PRODUCTS_CO_LOCATED"]:
            break
        a, b = pairs[k]
        if rng.random() < 0.5:
            a, b = b, a
        if a in used_skus or b in used_skus:
            continue
        la = locs_i.loc[sku_loc[a]]
        bay = (la.warehouse_id, la.aisle, la.bay)
        if bay in used_bays:
            continue
        m = ((locs.warehouse_id == la.warehouse_id) & (locs.aisle == la.aisle) & (locs.bay == la.bay)
             & (locs.status == "ACTIVE")).to_numpy() & loc_zone_haz
        cand = [c for c in locs.location_id.to_numpy()[m] if c not in occupied and c not in used_locs]
        if not cand:
            continue
        caps = cap_of(b, cand)
        fits = [c for c, cu in zip(cand, caps) if cu >= prof.at[b, "case_qty"]]
        if not fits:
            continue
        used_skus.add(a)
        move(b, fits[rng.integers(0, len(fits))], "INCOMPATIBLE_PRODUCTS_CO_LOCATED", related=sku_slot[a])
        used_bays.add(bay)
        n_done += 1

    # 3) slot assignment duplicates an active location -------------------
    n_done = 0
    pool = [s for s in normal if s in sku_slot]
    loc_wh = locs_i.warehouse_id
    groups: dict = {}
    for y in pool:
        groups.setdefault((loc_wh.at[sku_loc[y]], prof.at[y, "temp_class"]), []).append(y)
    for x in rng.permutation(pool):
        if n_done >= targets["DUPLICATE_ACTIVE_LOCATION"]:
            break
        if x in used_skus:
            continue
        key = (loc_wh.at[sku_loc[x]], prof.at[x, "temp_class"])
        same = [y for y in groups[key] if y != x and y not in used_skus and sku_loc[y] not in used_locs]
        if not same:
            continue
        rng.shuffle(same)
        for y in same[:15]:
            if cap_of(x, [sku_loc[y]])[0] >= prof.at[x, "case_qty"]:
                used_skus.add(y)
                move(x, sku_loc[y], "DUPLICATE_ACTIVE_LOCATION", related=sku_slot[y])
                n_done += 1
                break

    return pd.concat([slots, pd.DataFrame(new_rows)], ignore_index=True)


def inject_blocked_aisle(picks: pd.DataFrame, blocks: pd.DataFrame, target: int,
                         rng: np.random.Generator, gt: GT) -> pd.DataFrame:
    picks = picks.copy()
    blk = dict(zip(blocks.warehouse_id, blocks.aisle))
    cand = []
    for i, (wh, via) in enumerate(zip(picks.warehouse_id.to_numpy(), picks.route_aisles.to_numpy())):
        b = blk.get(wh)
        if b is None or ">" not in via:
            continue
        p, q = (int(v) for v in via.split(">"))
        if min(p, q) < b < max(p, q):
            cand.append(i)
    chosen = rng.choice(cand, size=min(target, len(cand)), replace=False) if cand else []
    for i in sorted(chosen):
        via = picks.at[i, "route_aisles"]
        p, q = via.split(">")
        b = blk[picks.at[i, "warehouse_id"]]
        picks.at[i, "route_aisles"] = f"{p}>{b}>{q}"
        gt.add("PICK_PATH_USES_BLOCKED_AISLE", "PickEvent", picks.at[i, "pick_id"], picks.at[i, "warehouse_id"],
               related=picks.at[i, "order_id"], subtype="CUT_THROUGH_PERMANENT_BLOCK",
               note=f"picker cut through blocked aisle {b}")
    return picks


def temporary_blocks(blocks: pd.DataFrame, locations: pd.DataFrame, zones: pd.DataFrame, picks: pd.DataFrame,
                     rng: np.random.Generator, gt: GT) -> pd.DataFrame:
    """Short maintenance blocks on the busiest ambient aisle of warehouses without a permanent block.

    Picks that traverse the aisle INSIDE the window are rule-derived positives;
    picks in the same aisle on the same day OUTSIDE the window are negative controls.
    """
    perm = set(blocks.warehouse_id)
    amb = zones[zones.zone_type == "AMBIENT"].set_index("warehouse_id")
    rows = []
    start = pd.Timestamp(PARAMS.horizon_start)
    for wid in sorted(set(locations.warehouse_id) - perm):
        z = amb.loc[wid]
        aisle = int(z.aisle_from)
        day = start + pd.Timedelta(days=int(rng.integers(14, 56)))
        if day.weekday() == 6:
            day += pd.Timedelta(days=1)
        frm = day + pd.Timedelta(hours=int(rng.integers(9, 15)), minutes=int(rng.choice([0, 30])))
        to = frm + pd.Timedelta(minutes=int(rng.choice([45, 60, 90])))
        rows.append({"warehouse_id": wid, "zone_id": z.zone_id, "aisle": aisle, "reason": "MAINTENANCE",
                     "blocked_from": frm.strftime("%Y-%m-%dT%H:%M:%S"), "blocked_to": to.strftime("%Y-%m-%dT%H:%M:%S"),
                     "status": "ACTIVE"})
    tmp = pd.DataFrame(rows, columns=blocks.columns.drop("block_id"))
    out = pd.concat([blocks.drop(columns=["block_id"]), tmp], ignore_index=True)
    out.insert(0, "block_id", [ids.block_id(i + 1) for i in range(len(out))])
    for b in out.iloc[len(blocks):].itertuples(index=False):
        pw = picks[picks.warehouse_id == b.warehouse_id]
        hit = pw.route_aisles.map(lambda v: b.aisle in {int(x) for x in str(v).split(">")})
        frm, to = pd.Timestamp(b.blocked_from), pd.Timestamp(b.blocked_to)
        win = (pw.picked_at >= frm) & (pw.picked_at < to)
        for r in pw[hit & win].itertuples(index=False):
            gt.add("PICK_PATH_USES_BLOCKED_AISLE", "PickEvent", r.pick_id, r.warehouse_id, related=r.order_id,
                   subtype="TEMPORARY_BLOCK_WINDOW",
                   note=f"aisle {b.aisle} under {b.block_id} {b.blocked_from}..{b.blocked_to}")
        same_day = pw[hit & (pw.picked_at.dt.normalize() == frm.normalize()) & ~win]
        for r in same_day.head(5).itertuples(index=False):
            gt.add("NONE", "PickEvent", r.pick_id, r.warehouse_id, related=b.block_id,
                   subtype="CONTROL_OUTSIDE_BLOCK_WINDOW", note=f"aisle {b.aisle} used outside the block window")
    return out


def boundary_controls(slots, prof_cur, locations, roster, repl, gt: GT, n: int = 10):
    """Valid edge cases near each rule's threshold, labelled NONE (expected: not flagged)."""
    from ..engine.exceptions import _active_view, pair_capacity
    a = _active_view(slots, prof_cur, locations)
    cap = pair_capacity(a)
    dup_locs = set(a.location_id[a.location_id.duplicated(keep=False)])
    exact = a[(cap == a.case_qty) & ~a.location_id.isin(dup_locs)]
    for r in exact.head(n).itertuples(index=False):
        gt.add("NONE", "SlotAssignment", r.slot_id, r.warehouse_id, subtype="CONTROL_EXACT_CAPACITY_FIT",
               note=f"{r.sku_id} capacity exactly one case ({r.case_qty})")
    h = a[a.hazard_class != "NONE"]
    k = 0
    for _, g in h.groupby(["warehouse_id", "aisle", "bay"]):
        cls = list(g.hazard_class)
        if len(g) >= 2 and not any(c2 in incompatible_with(c1) for c1 in cls for c2 in cls):
            gt.add("NONE", "SlotAssignment", g.slot_id.iloc[-1], g.warehouse_id.iloc[0],
                   related="|".join(g.slot_id.iloc[:-1]), subtype="CONTROL_COMPATIBLE_HAZMAT_SAME_BAY",
                   note=" + ".join(sorted(set(cls))) + " share a bay (allowed)")
            k += 1
            if k >= n:
                break
    load = repl.groupby("roster_id").labour_minutes.sum()
    rr = roster.assign(w=roster.roster_id.map(load).fillna(0))
    near = rr[(rr.w <= rr.staffed_minutes) & (rr.w >= 0.85 * rr.staffed_minutes)].sort_values("roster_id")
    for r in near.head(n).itertuples(index=False):
        gt.add("NONE", "LabourRoster", r.roster_id, r.warehouse_id, subtype="CONTROL_NEAR_LABOUR_CAPACITY",
               note=f"workload {r.w:.0f} of {r.staffed_minutes} staffed minutes")
