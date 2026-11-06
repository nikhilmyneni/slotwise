"""Hard-constraint candidate generation (vectorised per warehouse).

A location is a feasible slot for a SKU when ALL of these hold:
  1. location status is ACTIVE (not in a blocked aisle)
  2. temperature class of the zone equals the SKU temperature class
  3. hazmat SKUs only in HAZMAT zones, and HAZMAT zones only hold hazmat SKUs
  4. unit dimensions fit (any rotation: sorted dims compared)
  5. capacity_units = min(volume fill 85%, weight limit, 10-case stocking policy) >= one case
Bay-level segregation of incompatible hazard classes is dynamic and is
checked during assignment (see slotting.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PARAMS

FILL_FACTOR = 0.85


def sku_arrays(prof: pd.DataFrame) -> dict:
    dims = np.sort(prof[["length_cm", "width_cm", "height_cm"]].to_numpy(float), axis=1)[:, ::-1]
    return {
        "dims": dims,
        "vol": dims.prod(axis=1),
        "w": prof.unit_weight_kg.to_numpy(float),
        "case": prof.case_qty.to_numpy(int),
        "temp": prof.temp_class.to_numpy(),
        "haz": prof.hazard_class.to_numpy(),
    }


def loc_arrays(locs: pd.DataFrame, zones: pd.DataFrame) -> dict:
    z = zones.set_index("zone_id")
    dims = np.sort(locs[["width_cm", "depth_cm", "height_cm"]].to_numpy(float), axis=1)[:, ::-1]
    return {
        "dims": dims,
        "vol": dims.prod(axis=1),
        "maxw": locs.max_weight_kg.to_numpy(float),
        "temp": z.temp_class.reindex(locs.zone_id).to_numpy(),
        "hazok": z.allows_hazmat.reindex(locs.zone_id).to_numpy(bool),
        "active": (locs.status == "ACTIVE").to_numpy(),
    }


def capacity_matrix(S: dict, L: dict) -> np.ndarray:
    """Units of each SKU a location can hold (0 when it physically does not fit)."""
    fit = np.all(S["dims"][:, None, :] <= L["dims"][None, :, :] + 1e-9, axis=2)
    by_vol = np.floor(FILL_FACTOR * L["vol"][None, :] / S["vol"][:, None])
    by_w = np.floor(L["maxw"][None, :] / S["w"][:, None])
    policy = (PARAMS.max_cases_per_slot * S["case"])[:, None]
    return np.where(fit, np.minimum(np.minimum(by_vol, by_w), policy), 0).astype(np.int64)


def compat_matrix(S: dict, L: dict) -> np.ndarray:
    temp_ok = S["temp"][:, None] == L["temp"][None, :]
    haz_ok = (S["haz"] != "NONE")[:, None] == L["hazok"][None, :]
    return temp_ok & haz_ok & L["active"][None, :]


def single_capacity(sku_row: pd.Series, loc_row: pd.Series) -> int:
    """Scalar helper used by validators/detectors."""
    sd = sorted([sku_row.length_cm, sku_row.width_cm, sku_row.height_cm], reverse=True)
    ld = sorted([loc_row.width_cm, loc_row.depth_cm, loc_row.height_cm], reverse=True)
    if any(a > b + 1e-9 for a, b in zip(sd, ld)):
        return 0
    vol = sd[0] * sd[1] * sd[2]
    return int(min(np.floor(FILL_FACTOR * ld[0] * ld[1] * ld[2] / vol),
                   np.floor(loc_row.max_weight_kg / sku_row.unit_weight_kg),
                   PARAMS.max_cases_per_slot * sku_row.case_qty))
