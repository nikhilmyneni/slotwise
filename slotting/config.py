"""Central configuration: scale presets, fixed seed and business-rule parameters.

Every number the generator or engine relies on lives here so that the
methodology is documented in one place and the starter / full datasets come
from exactly the same code path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SEED = 20261022
GENERATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class Scale:
    name: str
    warehouses: int
    locations: int
    skus: int
    order_lines: int


SCALES: dict[str, Scale] = {
    # Same density per warehouse as "full" (500 locations / 250 SKUs / 5k lines)
    "starter": Scale("starter", warehouses=4, locations=2_000, skus=1_000, order_lines=20_000),
    "full": Scale("full", warehouses=20, locations=10_000, skus=5_000, order_lines=100_000),
}


@dataclass(frozen=True)
class Params:
    # ---- calendar -------------------------------------------------------
    horizon_start: date = date(2026, 1, 5)          # Monday, week 1
    horizon_weeks: int = 12
    peak_weeks: tuple[int, ...] = (9, 10)           # 1-based weeks with demand shift
    peak_volume_multiplier: float = 1.8
    seasonal_cohort_share: float = 0.10             # SKUs that surge during peak
    seasonal_boost: float = 8.0
    baseline_slot_date: date = date(2025, 12, 15)   # legacy slotting went live
    reslot_proposal_date: date = date(2026, 4, 1)   # optimizer proposal date
    train_weeks: int = 10                           # optimizer learns velocity on weeks 1-10, evaluated on 11-12 (holdout)
    shifts: tuple[str, ...] = ("AM", "PM")          # AM 06-14, PM 14-22

    # ---- layout ---------------------------------------------------------
    aisle_pitch_m: float = 3.0                      # x distance between aisles
    bay_width_m: float = 1.2                        # y distance between bays
    bays_per_aisle: int = 8
    levels: int = 3
    sides: int = 2
    # zone mix (share of a warehouse's locations), laid out in this order from the dock
    zone_mix: tuple[tuple[str, float], ...] = (
        ("AMBIENT", 0.62),
        ("BULK", 0.08),
        ("CHILLED", 0.15),
        ("FROZEN", 0.08),
        ("HAZMAT", 0.07),
    )
    blocked_aisle_every_nth_wh: int = 3             # WH index % n == 0 gets a blocked aisle

    # ---- SKU mix --------------------------------------------------------
    oversized_share: float = 0.03
    hazmat_share: float = 0.05
    temp_mix: tuple[tuple[str, float], ...] = (("AMBIENT", 0.75), ("CHILLED", 0.15), ("FROZEN", 0.10))
    hazard_classes: tuple[str, ...] = ("FLAMMABLE", "OXIDIZER", "CORROSIVE", "TOXIC")
    # pairs that must not share a bay
    incompatible_pairs: tuple[tuple[str, str], ...] = (
        ("FLAMMABLE", "OXIDIZER"),
        ("CORROSIVE", "TOXIC"),
        ("FLAMMABLE", "CORROSIVE"),
    )
    profile_change_share: float = 0.05              # SKUs with a historical profile version
    zipf_exponent: float = 1.1
    abc_cutoffs: tuple[float, float] = (0.80, 0.95)  # cumulative pick share for A / B

    # ---- labour ---------------------------------------------------------
    walk_speed_mps: float = 0.8
    pick_seconds_per_line: float = 12.0
    pick_seconds_per_unit: float = 3.0
    level_penalty_m: tuple[float, ...] = (0.0, 0.0, 4.0)   # per level 1..3 (golden zone = 1-2)
    repl_minutes_per_trip: float = 6.0
    repl_minutes_per_unit: float = 0.05
    max_cases_per_slot: int = 10                    # stocking policy: forward slot holds at most 10 cases
    move_cost_minutes: float = 20.0                 # labour to physically move one SKU
    move_payback_days: float = 60.0                 # a move must pay back within this many days
    repl_min_fill: float = 0.30                     # trigger replenishment below 30% of capacity
    roster_headroom: float = 1.30                   # planned minutes = p90 normal workload x headroom
    staff_shortage_share: float = 0.03             # share of shifts with injected staff shortage
    staff_shortage_factor: float = 0.40

    # ---- anomaly injection (per full scale; scaled linearly) -------------
    anomalies_full: dict = field(default_factory=lambda: {
        "SKU_EXCEEDS_LOCATION_CAPACITY": 120,
        "INCOMPATIBLE_PRODUCTS_CO_LOCATED": 60,
        "DUPLICATE_ACTIVE_LOCATION": 100,
        "PICK_PATH_USES_BLOCKED_AISLE": 150,
    })
    cancel_share: float = 0.01


PARAMS = Params()

ISSUE_TYPES = (
    "SKU_EXCEEDS_LOCATION_CAPACITY",
    "INCOMPATIBLE_PRODUCTS_CO_LOCATED",
    "DUPLICATE_ACTIVE_LOCATION",
    "PICK_PATH_USES_BLOCKED_AISLE",
    "REPLENISHMENT_EXCEEDS_LABOR_CAPACITY",
)


def anomaly_target(issue: str, scale: Scale) -> int:
    full = SCALES["full"]
    return max(5, round(PARAMS.anomalies_full[issue] * scale.order_lines / full.order_lines))
