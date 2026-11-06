# How the work was verified

Every number below was produced by the commands shown, on Windows 11 with Python 3.13.7 (pandas 3.0.3, numpy 2.5.0) and Node 22.20, seed `20261022`. The figures come from the full-scale run (`out/full/`).

## 1. Automated tests

```powershell
python -m pytest -q
# 10 passed
```

`tests/test_pipeline.py` runs the whole pipeline at starter scale and checks:
- exact volumes;
- ID formats;
- that validation has no failures;
- zero constraint violations in the proposal;
- that the proposal beats the legacy layout on the holdout weeks;
- that the move budget stays partial (under half the SKUs);
- detector precision and recall, with zero false alarms on the negative controls;
- that no label columns leak into the inputs;
- byte-identical regeneration;
- that a custom seed changes the random stream.

## 2. Full pipeline with built-in validation

```powershell
python -m slotting all --scale full --web
```

**Volumes.** 20 warehouses, 10,000 locations, 5,000 SKUs and 100,000 order lines. Derived tables:

| Table | Rows |
|---|---:|
| orders | 36,527 |
| pick_events | 98,957 |
| slot_assignments | 5,280 |
| slot_events | 10,840 |
| replenishments | 11,092 |
| labour_roster | 3,360 |
| sku_profiles | 5,244 |

**Validation:** 112 checks. 107 integrity checks pass, 0 fail. The other 5 are business-rule findings, the injected anomalies, and each one reconciles exactly to its count in ground truth. Categories covered:
- volume, primary keys, ID formats, foreign keys and joins;
- enums, date ordering, arithmetic reconciliation and lifecycle transitions;
- duplicates, label leakage and physical constraints.

**Proposal.**
- 0 constraint violations and 0 unslotted SKUs.
- 907 of 5,000 SKUs move:
  - 120 are mandatory, because the legacy slot breaks a rule;
  - 378 are displaced by a faster SKU;
  - 409 move to save labour.

**Results on the holdout weeks 11-12** (velocity is learned on weeks 1-10 only; 5,162 orders replayed on both layouts):

| Metric | Legacy | Proposal | Change |
|---|---:|---:|---:|
| Pick travel per order | 72.2 m | 60.6 m | −16.1% |
| Lines per labour hour | 68.4 | 76.0 | +11.1% |
| Replenishment labour | 247.7 h | 193.9 h | −21.7% |
| Shifts over labour capacity | 17 | 10 | −7 |

Over all 12 weeks: −16.9% travel, +11.8% throughput, replenishment 1,646.6 h → 1,234.4 h, overloaded shifts 157 → 76.

**Exception detection against ground truth.** The detector reads input tables only; the ground truth is read afterwards for scoring.

| Issue type | Labelled | Found |
|---|---:|---:|
| SKU exceeds location capacity | 120 | 120 |
| Incompatible products co-located | 60 | 60 |
| Duplicate active location | 100 | 100 |
| Pick path uses blocked aisle (150 injected cut-throughs + 9 inside temporary block windows) | 159 | 159 |
| Replenishment exceeds labour capacity (peak demand, staff shortage, spikes) | 157 | 157 |

The 92 negative controls raised 0 false alarms. These are valid cases at each rule's threshold:
- exact-fit capacity;
- compatible hazmat classes sharing a bay;
- labour just under capacity;
- picks through an aisle outside its block window.

## 3. Reproducibility

```powershell
python -m slotting repro --scale full
# reproducible: True (21 files compared)
```

The generator and engine run twice from the same seed. Row counts and SHA-256 checksums of all 21 output files match, and the report is saved to `out/full/repro_report.json`. `manifest.json` records the seed, the command, library versions and a checksum for every file.

## 4. Dashboard

- `cd web && npm run build`: TypeScript type-check and production build, about 70 KB of gzipped JS.
- The design-taste-frontend skill's `inspect.mjs --app` was run on all 9 pages at 1440, 768 and 390 px: 0 FAIL. The remaining warnings are deliberate: sticky side panels beside long tables, and monospace used for record IDs.
- I reviewed the inspector's screenshots in light and dark themes and at phone width. The first version of the dashboard was also clicked through in Chrome.
- The live deployment (https://slotwisely.vercel.app) was checked with HTTP requests. The page, `summary.json`, the warehouse files, the favicon and the proposal CSV all return 200.

## 5. Manual checks

- Spot-checked rows across files: a pick's `location_id` belongs to the SKU's active slot; the order's `pick_distance_m` equals the sum of its legs plus the return leg.
- Ran the detector on the proposal (treated as active). It reports zero issues, so the proposal fixes every legacy anomaly.
