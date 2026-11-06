"""Data dictionary: field meaning and units (hand-written) combined with
type / required / uniqueness / allowed values / FK rule (derived from the
generated data and the validation catalogue, so it can never drift)."""
from __future__ import annotations

import pandas as pd

from .validate import ENUMS, FK, PK

TABLE_INFO = {
    "suppliers": ("Supplier master (actor: supplier)", "1 supplier : N SKUs"),
    "warehouses": ("Distribution centre; dock at (0,0)", "1 warehouse : N zones, N locations, N orders"),
    "zones": ("Storage zone per warehouse (one per type), laid out from the dock outward", "1 zone : N locations"),
    "aisle_blocks": ("Aisle closures with effective window (blocked_to empty = open-ended)", "N blocks : 1 warehouse"),
    "locations": ("Pick location (slot position) with physical capacity", "1 location : N slot assignments over time"),
    "compatibility_rules": ("Hazard classes that must not share a bay", "reference table"),
    "skus": ("Item master", "1 SKU : N profiles (versioned), N order lines"),
    "sku_profiles": ("Versioned physical + velocity profile (SCD type 2 by effective dates)", "N profiles : 1 SKU; exactly one is_current"),
    "orders": ("Customer order picked at one warehouse (actor: carrier)", "1 order : N order lines, N pick events"),
    "order_lines": ("One SKU on an order", "N lines : 1 order; 1 line : 0..1 pick event"),
    "slot_assignments": ("Bridge SKU x Location over time (N:M with history). Never overwritten: moves RELEASE the old row and create a new one", "N : 1 SKU, N : 1 location"),
    "slot_events": ("Lifecycle events of slot assignments", "N events : 1 slot assignment"),
    "pick_events": ("Executed pick in S-shape route sequence", "1 pick : 1 order line"),
    "replenishments": ("Reserve -> forward-slot replenishment task per SKU per shift", "N tasks : 1 roster shift"),
    "labour_roster": ("Replenishment team capacity per warehouse shift", "1 roster shift : N replenishment tasks"),
}

DESC = {
    "supplier_name": "Display name", "country_code": "ISO-3166 alpha-2", "lead_time_days": ("Replenishment lead time", "days"),
    "status": "Lifecycle status", "warehouse_name": "Display name", "city": "City", "region": "Sales region",
    "opened_date": ("Opening date", "ISO date"), "dock_x_m": ("Dock x coordinate", "m"), "dock_y_m": ("Dock y coordinate", "m"),
    "aisle_length_m": ("Aisle length front to back", "m"), "location_count": "Derived: count of child locations",
    "zone_type": "AMBIENT / BULK (oversized pallets) / CHILLED / FROZEN / HAZMAT",
    "temp_class": "Temperature regime", "allows_hazmat": "Only HAZMAT zones accept hazard classes",
    "is_forward_pick": "Zone is a forward pick zone", "aisle_from": "First aisle number of the zone",
    "aisle_to": "Last aisle number of the zone", "aisle": "Aisle number inside the warehouse (1 = nearest dock)",
    "reason": "Why the record exists", "blocked_from": ("Block start", "ISO datetime"),
    "blocked_to": ("Block end (empty = still blocked)", "ISO datetime"), "bay": "Bay along the aisle (1 = front)",
    "level": "Shelf level (1-2 = golden zone)", "side": "L or R side of the aisle", "location_type": "Rack type",
    "width_cm": ("Width", "cm"), "depth_cm": ("Depth", "cm"), "height_cm": ("Height", "cm"),
    "max_weight_kg": ("Load limit", "kg"), "volume_l": ("Derived: width x depth x height / 1000", "litre"),
    "x_m": ("x = aisle x 3.0", "m"), "y_m": ("y = (bay - 0.5) x 1.2", "m"), "dist_from_dock_m": ("Derived: x + y", "m"),
    "class_a": "Hazard class", "class_b": "Hazard class", "scope": "Segregation scope", "rule": "Rule",
    "sku_name": "Display name", "category": "Merchandise category", "home_warehouse_id": "Warehouse that stocks the SKU",
    "unit_of_measure": "Unit", "created_date": ("SKU creation date", "ISO date"), "version": "Profile version",
    "effective_from": ("Version valid from", "ISO date"), "effective_to": ("Version valid to (empty = current)", "ISO date"),
    "is_current": "Current profile flag", "length_cm": ("Unit length (longest side)", "cm"),
    "unit_weight_kg": ("Unit weight", "kg"), "case_qty": ("Units per case (minimum slot stock)", "units"),
    "hazard_class": "NONE or a dangerous-goods class", "is_oversized": "Only fits BULK pallet positions",
    "picks_total": "Derived: non-cancelled order lines in the horizon", "units_total": ("Derived: units ordered", "units"),
    "picks_per_day": ("Derived: picks_total / 84", "lines/day"), "units_per_day": ("Derived", "units/day"),
    "peak_picks_per_day": ("Derived: weeks 9-10 only", "lines/day"), "normal_picks_per_day": ("Derived: other weeks", "lines/day"),
    "velocity_class": "Derived ABC: A = first 80% of warehouse picks, B = next 15%, C = rest",
    "peak_velocity_class": "Derived ABC on peak weeks", "carrier_id": "Carrier collecting the order",
    "priority": "Service level", "created_at": ("Order time", "ISO datetime"), "week_no": "Horizon week (1-12)",
    "shift": "AM 06-14 / PM 14-22", "line_count": "Derived: count(order_lines)", "total_units": ("Derived: sum(qty)", "units"),
    "released_at": ("Released to picking", "ISO datetime"), "picker_id": "Picker", "picked_at": ("Pick completed", "ISO datetime"),
    "shipped_at": ("Handed to carrier", "ISO datetime"), "cancelled_at": ("Cancellation time", "ISO datetime"),
    "pick_distance_m": ("Derived: sum(pick travel_m) + return_leg_m", "m"), "return_leg_m": ("Last pick back to dock", "m"),
    "line_no": "Line number", "qty": ("Quantity", "units"), "line_status": "PICKED or CANCELLED",
    "strategy": "BASELINE (legacy) or OPTIMIZED (engine proposal)", "assigned_at": ("Effective from", "ISO datetime"),
    "released_at_slot": "", "capacity_units": ("Derived: min(85% volume fill, weight limit, 10 cases)", "units"),
    "min_units": ("Derived: replenishment trigger = 30% of capacity", "units"),
    "cost_s_per_day": ("Engine: expected labour seconds per day in this slot", "s/day"),
    "n_candidates": "Engine: feasible locations for the SKU", "candidate_rank": "Engine: rank of the chosen slot by cost",
    "supersedes_slot_id": "Slot this record replaces", "change_reason": "INITIAL / LEGACY_MOVE / RESLOT",
    "event_type": "CREATED / ACTIVATED / RELEASED / PROPOSED", "event_at": ("Event time", "ISO datetime"),
    "actor_role": "PLANNER / OPERATOR / SYSTEM", "seq": "Position in the S-shape route",
    "travel_m": ("Leg distance from previous stop", "m"), "route_aisles": "Aisles traversed on the leg, '>' separated",
    "pick_seconds": ("Derived: travel/0.8 + 12 + 3 x qty", "s"), "to_location_id": "Forward slot replenished",
    "from_area": "Reserve storage", "shift_date": ("Shift date", "ISO date"), "qty_units": ("Units moved", "units"),
    "trips": "Derived: ceil(deficit / capacity)", "labour_minutes": ("Derived: trips x 6 + units x 0.05", "min"),
    "triggered_at": ("Task created", "ISO datetime"), "completed_at": ("Task done (empty if DEFERRED)", "ISO datetime"),
    "planned_minutes": ("Derived: p90 normal-week workload x 1.3, rounded up to 30", "min"),
    "staffed_minutes": ("Minutes actually staffed", "min"), "roster_status": "STAFFED or SHORT_STAFFED", "team": "Team",
}


def _type(s: pd.Series) -> str:
    k = s.dtype.kind
    if k == "b":
        return "boolean"
    if k in "iu":
        return "integer"
    if k == "f":
        return "integer" if s.dropna().apply(float.is_integer).all() and "cm" not in s.name else "decimal"
    if k == "M":
        return "datetime"
    return "string"


def dictionary(tables: dict[str, pd.DataFrame]) -> list[dict]:
    fk = {(c, col): (p, nullable) for c, col, p, nullable in FK}
    rows = []
    for tbl, df in tables.items():
        for col in df.columns:
            s = df[col]
            d = DESC.get(col, "")
            desc, unit = (d if isinstance(d, tuple) else (d, ""))
            rule = []
            if col == PK.get(tbl):
                rule.append("primary key")
                desc = desc or "Primary key"
            if (tbl, col) in fk:
                p, _ = fk[(tbl, col)]
                rule.append(f"FK -> {p}.{PK[p]}")
                desc = desc or f"Reference to {p}"
            allowed = ENUMS.get((tbl, col))
            if allowed is None and s.dtype == object and 1 < s.nunique() <= 8 and col not in ("city", "region"):
                allowed = set(s.dropna().unique())
            if s.dtype.kind in "if" and s.notna().any():
                rule.append(f"range {s.min():g}..{s.max():g}")
            rows.append({
                "table": tbl, "field": col, "type": _type(s), "required": bool(s.notna().all()),
                "unique": bool(s.is_unique), "units": unit, "allowed_values": "|".join(sorted(map(str, allowed))) if allowed else "",
                "validation": "; ".join(rule), "description": desc,
            })
    return rows


def dictionary_markdown(tables: dict[str, pd.DataFrame]) -> str:
    rows = dictionary(tables)
    out = ["# Data dictionary", "",
           "Generated by `python -m slotting all`; type, required, unique and ranges are measured, "
           "not hand-typed.", ""]
    for tbl, (purpose, card) in TABLE_INFO.items():
        out += [f"## {tbl}", "", f"{purpose}. Cardinality: {card}. Primary key: `{PK[tbl]}`.", "",
                "| Field | Type | Req | Unique | Units | Allowed | Validation | Description |",
                "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            if r["table"] == tbl:
                out.append(f"| `{r['field']}` | {r['type']} | {'Y' if r['required'] else 'N'} | {'Y' if r['unique'] else ''} | "
                           f"{r['units']} | {r['allowed_values']} | {r['validation']} | {r['description']} |")
        out.append("")
    return "\n".join(out)
