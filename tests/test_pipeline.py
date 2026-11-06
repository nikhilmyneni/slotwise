"""End-to-end tests on the starter scale (same code path as full)."""
import hashlib

import pandas as pd
import pytest

from slotting import ids
from slotting import config
from slotting.config import SCALES
from slotting.engine.run import optimize
from slotting.evaluate import score
from slotting.generate.pipeline import generate
from slotting.generate.pipeline import rng_for
from slotting.validate import validate

SCALE = SCALES["starter"]


@pytest.fixture(scope="module")
def run():
    tables, gt = generate(SCALE, log=lambda *_: None)
    results = optimize(tables)
    return tables, gt, results


def _digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df.astype(str), index=False).values.tobytes()).hexdigest()


def test_volumes(run):
    t, _, _ = run
    assert len(t["warehouses"]) == SCALE.warehouses
    assert len(t["locations"]) == SCALE.locations
    assert len(t["skus"]) == SCALE.skus
    assert len(t["order_lines"]) == SCALE.order_lines


def test_id_formats(run):
    t, _, _ = run
    assert t["warehouses"].warehouse_id.str.match(ids.PATTERNS["warehouse_id"]).all()
    assert t["locations"].location_id.str.match(ids.PATTERNS["location_id"]).all()
    assert t["orders"].order_id.str.match(ids.PATTERNS["order_id"]).all()
    assert t["pick_events"].pick_id.str.match(ids.PATTERNS["pick_id"]).all()
    assert t["slot_assignments"].slot_id.str.match(ids.PATTERNS["slot_id"]).all()


def test_validation_has_no_failures(run):
    t, gt, r = run
    v = validate(t, gt, SCALE, r)
    failed = [c for c in v["checks"] if c["status"] == "FAIL"]
    assert not failed, failed


def test_optimized_respects_constraints(run):
    _, _, r = run
    m = r["metrics"]
    assert m["constraint_violations_optimized"] == 0
    assert m["unslotted_skus_optimized"] == 0


def test_optimized_beats_baseline_on_holdout(run):
    _, _, r = run
    h = r["metrics"]["holdout"]
    assert h["distance_optimized_km"] < h["distance_baseline_km"]
    assert h["lines_per_hour_optimized"] > h["lines_per_hour_baseline"]


def test_move_budget_is_partial(run):
    _, _, r = run
    m = r["metrics"]
    assert 0 < m["skus_moved"] < m["skus_total"] * 0.5


def test_detector_matches_ground_truth_and_controls(run):
    _, gt, r = run
    s = score(r["exceptions"], gt)
    assert s["overall"]["fn"] == 0 and s["overall"]["fp"] == 0
    assert s["negative_controls"]["false_alarms"] == 0
    assert set(gt.issue_type) >= {"SKU_EXCEEDS_LOCATION_CAPACITY", "INCOMPATIBLE_PRODUCTS_CO_LOCATED",
                                  "DUPLICATE_ACTIVE_LOCATION", "PICK_PATH_USES_BLOCKED_AISLE",
                                  "REPLENISHMENT_EXCEEDS_LABOR_CAPACITY"}


def test_no_label_leakage(run):
    t, _, _ = run
    for name, df in t.items():
        assert not any("ground_truth" in c or "issue_type" in c for c in df.columns), name


def test_reproducible(run):
    t1, gt1, _ = run
    t2, gt2 = generate(SCALE, log=lambda *_: None)
    for k in ("locations", "order_lines", "slot_assignments", "pick_events", "replenishments"):
        assert _digest(t1[k]) == _digest(t2[k]), k
    assert _digest(gt1) == _digest(gt2)


def test_custom_seed_changes_generator_stream():
    original = config.SEED
    try:
        baseline = rng_for(1).integers(0, 1_000_000, size=8)
        config.SEED = original + 1
        changed = rng_for(1).integers(0, 1_000_000, size=8)
        assert not (baseline == changed).all()
        assert (changed == rng_for(1).integers(0, 1_000_000, size=8)).all()
    finally:
        config.SEED = original
