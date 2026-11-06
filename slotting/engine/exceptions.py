"""Rule-based exception detection over input tables only (never reads ground truth)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PARAMS
from .candidates import FILL_FACTOR
from .slotting import incompatible_with

ACTIONS = {
    "SKU_EXCEEDS_LOCATION_CAPACITY": ("HIGH", "Re-slot SKU to a location it physically fits (see optimized proposal)"),
    "INCOMPATIBLE_PRODUCTS_CO_LOCATED": ("CRITICAL", "Segregate: move the later-assigned SKU out of the bay"),
    "DUPLICATE_ACTIVE_LOCATION": ("HIGH", "Release the duplicate assignment and re-slot the SKU"),
    "PICK_PATH_USES_BLOCKED_AISLE": ("CRITICAL", "Safety: reroute via cross-aisle; brief picker"),
    "REPLENISHMENT_EXCEEDS_LABOR_CAPACITY": ("MEDIUM", "Add replenishment labour or defer C-class tasks"),
    "NO_FEASIBLE_SLOT": ("HIGH", "Add suitable locations or review SKU profile"),
}


def pair_capacity(a: pd.DataFrame) -> np.ndarray:
    """Row-wise capacity for an active view (SKU dims + loc_* location dims)."""
    sd = np.sort(a[["length_cm", "width_cm", "height_cm"]].to_numpy(float), axis=1)
    ld = np.sort(a[["loc_width_cm", "loc_depth_cm", "loc_height_cm"]].to_numpy(float), axis=1)
    fit = np.all(sd <= ld + 1e-9, axis=1)
    by_vol = np.floor(FILL_FACTOR * ld.prod(axis=1) / sd.prod(axis=1))
    by_w = np.floor(a.loc_max_weight_kg.to_numpy(float) / a.unit_weight_kg.to_numpy(float))
    pol = PARAMS.max_cases_per_slot * a.case_qty.to_numpy()
    return np.where(fit, np.minimum(np.minimum(by_vol, by_w), pol), 0)


def _active_view(slots, prof_cur, locs):
    a = slots[slots.status == "ACTIVE"].copy()
    a = a.merge(prof_cur.drop(columns=["status"], errors="ignore"), on="sku_id", how="left")
    l = locs.drop(columns=["warehouse_id"]).rename(columns={
        "width_cm": "loc_width_cm", "depth_cm": "loc_depth_cm", "height_cm": "loc_height_cm",
        "max_weight_kg": "loc_max_weight_kg", "status": "loc_status"})
    a = a.merge(l, on="location_id", how="left")
    return a.reset_index(drop=True)


def slot_violations(slots: pd.DataFrame, prof_cur: pd.DataFrame, locs: pd.DataFrame,
                    zones: pd.DataFrame) -> list[dict]:
    a = _active_view(slots, prof_cur, locs)
    out = []
    cap = pair_capacity(a)
    for r, c in zip(a.itertuples(index=False), cap):
        if c < r.case_qty:
            out.append(dict(issue_type="SKU_EXCEEDS_LOCATION_CAPACITY", entity_type="SlotAssignment",
                            entity_id=r.slot_id, warehouse_id=r.warehouse_id, related_ids="",
                            detail=f"{r.sku_id} needs {r.case_qty} units/case, {r.location_id} holds {int(c)}"))
    # duplicates: all but the earliest active slot on a location
    a_sorted = a.sort_values(["assigned_at", "slot_id"], kind="stable")
    for loc, g in a_sorted.groupby("location_id"):
        if len(g) > 1:
            first = g.iloc[0]
            for r in g.iloc[1:].itertuples(index=False):
                out.append(dict(issue_type="DUPLICATE_ACTIVE_LOCATION", entity_type="SlotAssignment",
                                entity_id=r.slot_id, warehouse_id=r.warehouse_id, related_ids=first.slot_id,
                                detail=f"{loc} already held by {first.sku_id}"))
    # incompatible hazard classes in the same bay: flag later-assigned slot
    h = a_sorted[a_sorted.hazard_class != "NONE"]
    for _, g in h.groupby(["warehouse_id", "aisle", "bay"]):
        if len(g) < 2:
            continue
        rows = list(g.itertuples(index=False))
        for j in range(1, len(rows)):
            bad = [rows[i] for i in range(j) if rows[i].hazard_class in incompatible_with(rows[j].hazard_class)]
            if bad:
                out.append(dict(issue_type="INCOMPATIBLE_PRODUCTS_CO_LOCATED", entity_type="SlotAssignment",
                                entity_id=rows[j].slot_id, warehouse_id=rows[j].warehouse_id,
                                related_ids="|".join(b.slot_id for b in bad),
                                detail=f"{rows[j].hazard_class} next to "
                                       f"{', '.join(sorted({b.hazard_class for b in bad}))} in aisle {rows[j].aisle} bay {rows[j].bay}"))
    # zone / status rules (not injected; must stay at zero)
    zt = zones.set_index("zone_id")
    temp_bad = a.temp_class.to_numpy() != zt.temp_class.reindex(a.zone_id).to_numpy()
    haz_bad = (a.hazard_class != "NONE").to_numpy() != zt.allows_hazmat.reindex(a.zone_id).to_numpy(bool)
    blk_bad = a.loc_status.to_numpy() == "BLOCKED"
    for r, t, hz, b in zip(a.itertuples(index=False), temp_bad, haz_bad, blk_bad):
        if t or hz or b:
            out.append(dict(issue_type="ZONE_RULE_VIOLATION", entity_type="SlotAssignment", entity_id=r.slot_id,
                            warehouse_id=r.warehouse_id, related_ids="",
                            detail=("temperature " if t else "") + ("hazmat-zone " if hz else "") + ("blocked " if b else "")))
    return out


def blocked_aisle_picks(picks: pd.DataFrame, blocks: pd.DataFrame) -> list[dict]:
    """Picks whose route traverses an aisle while an ACTIVE block covers picked_at (vectorised)."""
    if blocks.empty:
        return []
    act = blocks[blocks.status == "ACTIVE"].copy()
    act["frm"] = pd.to_datetime(act.blocked_from)
    act["to"] = pd.to_datetime(act.blocked_to).fillna(pd.Timestamp.max)
    pk = picks[picks.warehouse_id.isin(act.warehouse_id)][["pick_id", "order_id", "warehouse_id", "route_aisles", "picked_at"]]
    ex = pk.assign(aisle=pk.route_aisles.astype(str).str.split(">")).explode("aisle")
    ex["aisle"] = ex.aisle.astype(int)
    hit = ex.merge(act[["block_id", "warehouse_id", "aisle", "frm", "to"]], on=["warehouse_id", "aisle"])
    hit = hit[(hit.picked_at >= hit.frm) & (hit.picked_at < hit.to)].drop_duplicates("pick_id")
    return [dict(issue_type="PICK_PATH_USES_BLOCKED_AISLE", entity_type="PickEvent", entity_id=r.pick_id,
                 warehouse_id=r.warehouse_id, related_ids=r.order_id,
                 detail=f"route {r.route_aisles} crosses blocked aisle {r.aisle} ({r.block_id})")
            for r in hit.itertuples(index=False)]


def labour_overload(repl: pd.DataFrame, roster: pd.DataFrame) -> list[dict]:
    load = repl.groupby("roster_id").labour_minutes.sum()
    r = roster.assign(workload=roster.roster_id.map(load).fillna(0.0))
    over = r[r.workload > r.staffed_minutes]
    return [dict(issue_type="REPLENISHMENT_EXCEEDS_LABOR_CAPACITY", entity_type="LabourRoster",
                 entity_id=x.roster_id, warehouse_id=x.warehouse_id, related_ids="",
                 detail=f"{x.workload:.0f} min of replenishment vs {x.staffed_minutes} min staffed "
                        f"({x.shift_date} {x.shift}, {x.roster_status})")
            for x in over.itertuples(index=False)]


def detect(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    prof_cur = tables["sku_profiles"][tables["sku_profiles"].is_current]
    rows = (slot_violations(tables["slot_assignments"], prof_cur, tables["locations"], tables["zones"])
            + blocked_aisle_picks(tables["pick_events"], tables["aisle_blocks"])
            + labour_overload(tables["replenishments"], tables["labour_roster"]))
    df = pd.DataFrame(rows, columns=["issue_type", "entity_type", "entity_id", "warehouse_id", "related_ids", "detail"])
    df["severity"] = df.issue_type.map(lambda t: ACTIONS.get(t, ("MEDIUM", ""))[0])
    df["suggested_action"] = df.issue_type.map(lambda t: ACTIONS.get(t, ("", "Review"))[1])
    df["source"] = "DATA_AUDIT"
    df = df.sort_values(["issue_type", "entity_id"], kind="stable").reset_index(drop=True)
    df.insert(0, "exception_id", [f"EXC-{i + 1:06d}" for i in range(len(df))])
    return df
