"""Deterministic, zero-padded, immutable identifiers.

WH-001; LOC-<zone-id>-000001; SKU-000001; ORD-2026-000001;
PICK-<order-id>-001; SLOT-2026-000001.
"""
from __future__ import annotations

import re

ZONE_CODES = {"AMBIENT": "AMB", "BULK": "BLK", "CHILLED": "CHL", "FROZEN": "FRZ", "HAZMAT": "HAZ"}


def wh_id(n: int) -> str:
    return f"WH-{n:03d}"


def zone_id(wh_n: int, zone_type: str) -> str:
    # e.g. WH001-AMB ; one zone per type per warehouse
    return f"WH{wh_n:03d}-{ZONE_CODES[zone_type]}"


def loc_id(zone: str, n: int) -> str:
    return f"LOC-{zone}-{n:06d}"


def sku_id(n: int) -> str:
    return f"SKU-{n:06d}"


def profile_id(sku: str, version: int) -> str:
    return f"PRF-{sku[4:]}-V{version:02d}"


def order_id(n: int, year: int = 2026) -> str:
    return f"ORD-{year}-{n:06d}"


def order_line_id(order: str, n: int) -> str:
    return f"{order}-L{n:02d}"


def pick_id(order: str, n: int) -> str:
    return f"PICK-{order}-{n:03d}"


def slot_id(n: int, year: int = 2026) -> str:
    return f"SLOT-{year}-{n:06d}"


def repl_id(n: int, year: int = 2026) -> str:
    return f"REPL-{year}-{n:06d}"


def roster_id(wh: str, d: str, shift: str) -> str:
    return f"RST-{wh[3:]}-{d.replace('-', '')}-{shift}"


def block_id(n: int) -> str:
    return f"BLK-{n:04d}"


def supplier_id(n: int) -> str:
    return f"SUP-{n:04d}"


PATTERNS = {
    "warehouse_id": re.compile(r"^WH-\d{3}$"),
    "zone_id": re.compile(r"^WH\d{3}-(AMB|BLK|CHL|FRZ|HAZ)$"),
    "location_id": re.compile(r"^LOC-WH\d{3}-(AMB|BLK|CHL|FRZ|HAZ)-\d{6}$"),
    "sku_id": re.compile(r"^SKU-\d{6}$"),
    "profile_id": re.compile(r"^PRF-\d{6}-V\d{2}$"),
    "order_id": re.compile(r"^ORD-2026-\d{6}$"),
    "order_line_id": re.compile(r"^ORD-2026-\d{6}-L\d{2}$"),
    "pick_id": re.compile(r"^PICK-ORD-2026-\d{6}-\d{3}$"),
    "slot_id": re.compile(r"^SLOT-2026-\d{6}$"),
    "repl_id": re.compile(r"^REPL-2026-\d{6}$"),
}
