"""Master data: Supplier, Warehouse, Zone, AisleBlock, Location, SKU, SKUProfile (physical part).

Velocity fields of SKUProfile are derived later from order lines (see demand.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import ids
from ..config import PARAMS, Scale

CITIES = [
    ("Hyderabad", "SOUTH"), ("Bengaluru", "SOUTH"), ("Chennai", "SOUTH"), ("Mumbai", "WEST"),
    ("Pune", "WEST"), ("Ahmedabad", "WEST"), ("Delhi NCR", "NORTH"), ("Jaipur", "NORTH"),
    ("Lucknow", "NORTH"), ("Kolkata", "EAST"), ("Bhubaneswar", "EAST"), ("Guwahati", "EAST"),
    ("Nagpur", "CENTRAL"), ("Indore", "CENTRAL"), ("Bhopal", "CENTRAL"), ("Kochi", "SOUTH"),
    ("Coimbatore", "SOUTH"), ("Surat", "WEST"), ("Chandigarh", "NORTH"), ("Patna", "EAST"),
]

# location type variants per zone type and level: (type, width, depth, height, max_kg)
LOC_TYPES = {
    "SHELF_L": (120, 80, 80, 300), "SHELF_M": (100, 60, 60, 150), "SHELF_S": (60, 50, 40, 60),
    "BIN": (40, 40, 30, 25), "PALLET": (160, 120, 180, 1200), "COLD_SHELF": (90, 60, 50, 120),
    "COLD_BIN": (50, 40, 35, 40), "HAZ_CABINET": (100, 60, 60, 200), "HAZ_SHELF": (70, 50, 45, 80),
}
LOC_CHOICES = {
    "AMBIENT": {1: (["SHELF_L", "SHELF_M"], [0.5, 0.5]), 2: (["SHELF_M", "SHELF_S"], [0.6, 0.4]),
                3: (["SHELF_S", "BIN"], [0.5, 0.5])},
    "BULK": {lv: (["PALLET"], [1.0]) for lv in (1, 2, 3)},
    "CHILLED": {lv: (["COLD_SHELF", "COLD_BIN"], [0.65, 0.35]) for lv in (1, 2, 3)},
    "FROZEN": {lv: (["COLD_SHELF", "COLD_BIN"], [0.65, 0.35]) for lv in (1, 2, 3)},
    "HAZMAT": {lv: (["HAZ_CABINET", "HAZ_SHELF"], [0.5, 0.5]) for lv in (1, 2, 3)},
}
ZONE_TEMP = {"AMBIENT": "AMBIENT", "BULK": "AMBIENT", "CHILLED": "CHILLED", "FROZEN": "FROZEN", "HAZMAT": "AMBIENT"}

CATEGORIES = {
    "AMBIENT": ["GROCERY_DRY", "HOUSEHOLD", "ELECTRONICS", "PERSONAL_CARE", "HARDWARE", "STATIONERY"],
    "CHILLED": ["DAIRY", "FRESH_PRODUCE"],
    "FROZEN": ["FROZEN_FOOD", "ICE_CREAM"],
    "HAZMAT": ["CHEMICALS"],
    "OVERSIZED": ["FURNITURE", "APPLIANCES"],
}


def split_int(total: int, weights: np.ndarray) -> np.ndarray:
    """Largest-remainder split of an integer total by weights (deterministic)."""
    raw = weights / weights.sum() * total
    base = np.floor(raw).astype(int)
    rem = total - base.sum()
    order = np.argsort(-(raw - base), kind="stable")
    base[order[:rem]] += 1
    return base


def build_suppliers(scale: Scale, rng: np.random.Generator) -> pd.DataFrame:
    n = max(10, scale.skus // 100)
    countries = rng.choice(["IN", "IN", "IN", "CN", "VN", "DE", "US"], size=n)
    return pd.DataFrame({
        "supplier_id": [ids.supplier_id(i + 1) for i in range(n)],
        "supplier_name": [f"Supplier {i + 1:04d}" for i in range(n)],
        "country_code": countries,
        "lead_time_days": rng.integers(2, 30, size=n),
        "status": "ACTIVE",
    })


def build_layout(scale: Scale, rng: np.random.Generator):
    p = PARAMS
    n_wh = scale.warehouses
    loc_per_wh = split_int(scale.locations, rng.uniform(0.85, 1.15, size=n_wh))
    per_aisle = p.bays_per_aisle * p.levels * p.sides

    wh_rows, zone_rows, loc_rows, block_rows = [], [], [], []
    for w in range(n_wh):
        wn = w + 1
        wid = ids.wh_id(wn)
        city, region = CITIES[w % len(CITIES)]
        wh_rows.append({
            "warehouse_id": wid, "warehouse_name": f"{city} DC", "city": city, "region": region,
            "opened_date": date(2019 + (w % 6), 1 + (w % 12), 1).isoformat(),
            "dock_x_m": 0.0, "dock_y_m": 0.0,
            "aisle_length_m": p.bays_per_aisle * p.bay_width_m,
            "location_count": int(loc_per_wh[w]), "status": "ACTIVE",
        })
        zone_counts = split_int(int(loc_per_wh[w]), np.array([s for _, s in p.zone_mix]))
        aisle = 0
        has_block = (wn % p.blocked_aisle_every_nth_wh) == 1
        for (ztype, _), zc in zip(p.zone_mix, zone_counts):
            zid = ids.zone_id(wn, ztype)
            n_aisles = int(np.ceil(zc / per_aisle))
            first_aisle = aisle + 1
            blocked_aisle = first_aisle + 1 if (has_block and ztype == "AMBIENT" and n_aisles >= 3) else None
            if blocked_aisle:
                block_rows.append({
                    "block_id": ids.block_id(len(block_rows) + 1), "warehouse_id": wid, "zone_id": zid,
                    "aisle": blocked_aisle, "reason": "RACK_DAMAGE",
                    "blocked_from": "2025-12-01T00:00:00", "blocked_to": None, "status": "ACTIVE",
                })
            for k in range(int(zc)):
                a = first_aisle + k // per_aisle
                r = k % per_aisle
                level = r // (p.bays_per_aisle * p.sides) + 1
                rr = r % (p.bays_per_aisle * p.sides)
                bay = rr // p.sides + 1
                side = "L" if rr % p.sides == 0 else "R"
                names, probs = LOC_CHOICES[ztype][level]
                ltype = names[rng.choice(len(names), p=probs)]
                wcm, dcm, hcm, kg = LOC_TYPES[ltype]
                x = a * p.aisle_pitch_m
                y = (bay - 0.5) * p.bay_width_m
                loc_rows.append({
                    "location_id": ids.loc_id(zid, k + 1), "zone_id": zid, "warehouse_id": wid,
                    "aisle": a, "bay": bay, "level": level, "side": side,
                    "location_type": ltype, "width_cm": wcm, "depth_cm": dcm, "height_cm": hcm,
                    "max_weight_kg": kg, "volume_l": round(wcm * dcm * hcm / 1000, 1),
                    "x_m": round(x, 2), "y_m": round(y, 2),
                    "dist_from_dock_m": round(x + y, 2),
                    "status": "BLOCKED" if a == blocked_aisle else "ACTIVE",
                })
            zone_rows.append({
                "zone_id": zid, "warehouse_id": wid, "zone_type": ztype, "temp_class": ZONE_TEMP[ztype],
                "allows_hazmat": ztype == "HAZMAT", "is_forward_pick": True,
                "aisle_from": first_aisle, "aisle_to": first_aisle + n_aisles - 1,
                "location_count": int(zc),
            })
            aisle += n_aisles
    return (pd.DataFrame(wh_rows), pd.DataFrame(zone_rows), pd.DataFrame(loc_rows),
            pd.DataFrame(block_rows, columns=["block_id", "warehouse_id", "zone_id", "aisle", "reason",
                                              "blocked_from", "blocked_to", "status"]))


def build_skus(scale: Scale, warehouses: pd.DataFrame, suppliers: pd.DataFrame, rng: np.random.Generator):
    p = PARAMS
    n = scale.skus
    # home warehouse proportional to warehouse size
    per_wh = split_int(n, warehouses["location_count"].to_numpy().astype(float))
    home = np.repeat(warehouses["warehouse_id"].to_numpy(), per_wh)
    rng.shuffle(home)

    u = rng.random(n)
    kind = np.where(u < p.oversized_share, "OVERSIZED",
                    np.where(u < p.oversized_share + p.hazmat_share, "HAZMAT", "NORMAL"))
    temp_names = [t for t, _ in p.temp_mix]
    temp = rng.choice(temp_names, size=n, p=[s for _, s in p.temp_mix])
    temp = np.where(kind == "NORMAL", temp, "AMBIENT")
    hazard = np.where(kind == "HAZMAT", rng.choice(p.hazard_classes, size=n), "NONE")

    # unit dimensions (cm) and weight (kg)
    L = np.exp(rng.normal(np.log(18), 0.45, n)).clip(3, 60)
    L = np.where(temp != "AMBIENT", np.exp(rng.normal(np.log(15), 0.35, n)).clip(3, 40), L)
    L = np.where(kind == "HAZMAT", np.exp(rng.normal(np.log(20), 0.3, n)).clip(5, 45), L)
    W = L * rng.uniform(0.4, 1.0, n)
    H = (L * rng.uniform(0.2, 1.0, n)).clip(2, None)
    over = kind == "OVERSIZED"
    L = np.where(over, rng.uniform(110, 150, n), L)
    W = np.where(over, rng.uniform(70, 100, n), W)
    H = np.where(over, rng.uniform(60, 140, n), H)
    vol_cm3 = L * W * H
    weight = (vol_cm3 / 1000 * rng.uniform(0.15, 0.9, n)).clip(0.05, 25)
    weight = np.where(over, rng.uniform(25, 180, n), weight)

    case_qty = np.where(vol_cm3 < 500, rng.choice([6, 12, 24], n),
                        np.where(vol_cm3 < 3000, rng.choice([2, 4, 6, 8], n), rng.choice([1, 2], n)))
    case_qty = np.where(over, 1, case_qty)
    case_qty = np.where(kind == "HAZMAT", rng.choice([1, 2, 4, 6], n), case_qty)

    cat = np.array([
        CATEGORIES["OVERSIZED" if k == "OVERSIZED" else "HAZMAT" if k == "HAZMAT" else t][
            int(rng.integers(0, len(CATEGORIES["OVERSIZED" if k == "OVERSIZED" else "HAZMAT" if k == "HAZMAT" else t])))]
        for k, t in zip(kind, temp)
    ])
    sku_ids = [ids.sku_id(i + 1) for i in range(n)]
    created = [(date(2024, 1, 1) + timedelta(days=int(d))).isoformat() for d in rng.integers(0, 600, n)]
    sup = suppliers["supplier_id"].to_numpy()[rng.integers(0, len(suppliers), n)]

    skus = pd.DataFrame({
        "sku_id": sku_ids,
        "sku_name": [f"{c.replace('_', ' ').title()} item {i + 1:06d}" for i, c in enumerate(cat)],
        "category": cat, "supplier_id": sup, "home_warehouse_id": home,
        "unit_of_measure": "EA", "created_date": created, "status": "ACTIVE",
    })

    # SKU profiles: physical attributes, with a historical version for some SKUs
    has_hist = rng.random(n) < p.profile_change_share
    rows = []
    for i in range(n):
        dims = sorted([L[i], W[i], H[i]], reverse=True)
        cur = {
            "sku_id": sku_ids[i], "length_cm": round(dims[0], 1), "width_cm": round(dims[1], 1),
            "height_cm": round(dims[2], 1), "unit_weight_kg": round(float(weight[i]), 3),
            "case_qty": int(case_qty[i]), "temp_class": temp[i], "hazard_class": hazard[i],
            "is_oversized": bool(over[i]),
        }
        if has_hist[i]:
            f = rng.uniform(0.85, 1.15)
            old = dict(cur)
            old.update(length_cm=round(dims[0] * f, 1), width_cm=round(dims[1] * f, 1),
                       height_cm=round(dims[2] * f, 1),
                       unit_weight_kg=round(float(weight[i]) * f, 3))
            old.update(profile_id=ids.profile_id(sku_ids[i], 1), version=1,
                       effective_from=created[i], effective_to="2025-11-30", is_current=False)
            rows.append(old)
            cur.update(profile_id=ids.profile_id(sku_ids[i], 2), version=2,
                       effective_from="2025-12-01", effective_to=None, is_current=True)
        else:
            cur.update(profile_id=ids.profile_id(sku_ids[i], 1), version=1,
                       effective_from=created[i], effective_to=None, is_current=True)
        rows.append(cur)
    profiles = pd.DataFrame(rows)
    cols = ["profile_id", "sku_id", "version", "effective_from", "effective_to", "is_current",
            "length_cm", "width_cm", "height_cm", "unit_weight_kg", "case_qty",
            "temp_class", "hazard_class", "is_oversized"]
    return skus, profiles[cols]
