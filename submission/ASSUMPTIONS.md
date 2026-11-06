# Assumptions and deviations

The brief leaves some choices open. Each decision below is stated so it can be checked or changed (`slotting/config.py` holds every tunable number).

## Identifiers
The brief fixes `WH-001`, `LOC-<zone-id>-000001`, `SKU-000001`, `ORD-2026-000001`, `PICK-<order-id>-001` and `SLOT-2026-000001`. The rest are mine:

| Entity | Format | Note |
|---|---|---|
| Zone | `WH001-AMB` | One zone per type per warehouse; types AMB, BLK, CHL, FRZ, HAZ. A location is therefore `LOC-WH001-AMB-000001`, with a counter per zone. |
| Order line | `ORD-2026-000001-L01` | |
| Pick event | `PICK-<order>-NNN` | One per order line, numbered in route order. |
| Profile | `PRF-000001-V01` | Versioned. |
| Other records | `REPL-2026-000001`, `RST-001-20260105-AM`, `SEV-0000001`, `BLK-0001`, `SUP-0001`, `GT-000001`, `EXC-000001` | Replenishment, roster, slot event, aisle block, supplier, ground truth, exception. |

All counters are zero-padded and immutable, and order numbers are assigned in time order.

## Data model
- **Entities added beyond the brief's ten:**
  - Supplier (an actor in the brief);
  - AisleBlock (needed for the blocked-aisle rule, with effective windows);
  - LabourRoster (staffed minutes per shift, needed for the labour-capacity rule);
  - CompatibilityRules (which hazard classes may not share a bay);
  - SlotEvents (the lifecycle history).
- **SlotAssignment** is the SKU-location bridge with effective dates. Records are never overwritten: a move RELEASEs the old row and creates a new one, and the optimizer's output is a separate set of PROPOSED rows.
- **SKUProfile** is versioned (about 5% of SKUs have an earlier version). Velocity fields exist only on the current version, derived from order lines.
- **Home warehouse.** Each SKU is stocked in one warehouse and has exactly one forward pick slot. Reserve storage is not modelled as locations; replenishment comes from a "RESERVE" area.

## Business rules
- **Fit.** The unit fits the location in some rotation (sorted dimensions compared). Capacity is the smallest of:
  - 85% of the location volume;
  - the weight limit;
  - a stocking policy of 10 cases.
  
  The slot must hold at least one case.
- **Compatibility.**
  - Zone temperature must equal the SKU's temperature class.
  - Hazmat SKUs go only in HAZMAT zones, and HAZMAT zones hold only hazmat.
  - FLAMMABLE+OXIDIZER, CORROSIVE+TOXIC and FLAMMABLE+CORROSIVE may not share a bay.
- **Labour capacity** is measured per warehouse **shift** (AM 06-14, PM 14-22), not per day. Staffed minutes are the 90th percentile of normal-week workload × 1.3, rounded up to 30, with injected short-staffed shifts at 40%.
- **Velocity classes:** A is the first 80% of a warehouse's picks, B the next 15%, C the rest.
- **Pick path:** the S-shape traversal from a dock at (0,0); distance is measured along aisles and cross-aisles.
- **Replenishment:** a min/max rule per shift. Refill to capacity when stock drops below 30%. Cost is 6 minutes per trip plus 0.05 minutes per unit.

## Optimisation choices
- **Greedy by constraint tier, then velocity.** SKUs are placed in this order: oversized first, then hazmat, then the rest by pick frequency.
- **Cost minimised:** expected daily labour (pick walking plus replenishment trips).
- **Move cost.** A SKU stays in place unless moving saves more than a 20-minute move repaid within 60 days. Without this rule nearly every SKU moved.
- **Holdout evaluation.** Velocity is learned on weeks 1-10 and the result is scored on weeks 11-12. Weeks 9-10 are the peak, so the training window includes a demand shift.

## Generated data and anomalies
- **Scale.** Full scale is exactly the brief's volume. Starter is the same code at one-fifth of the volume (4 / 2,000 / 1,000 / 20,000).
- **Demand:** Zipf popularity per warehouse, plus a peak cohort that rises eightfold in weeks 9-10. About 3% of SKUs are oversized and 5% are hazmat; temperature mix is 75% ambient, 15% chilled, 10% frozen.
- **Injected anomalies at full scale:** 120 capacity, 60 incompatible, 100 duplicate and 150 blocked-aisle cut-throughs. Labour overloads are not injected; they are derived from the roster rule.
- **Temporary blocks.** Maintenance windows add rule-derived positives (picks inside the window) and negative controls (the same aisle, the same day, outside the window).

## Deviations to be aware of
- **The detection score is 100% by construction.** Labels come from the same documented rules the detector implements. The negative controls check thresholds and time windows, but the score shows the rules are implemented correctly, not that the detector would generalise to new kinds of anomaly.
- **The dashboard is read-only.** It shows precomputed outputs as a static site, so it can be hosted free with no server. Changing the scenario means re-running the Python pipeline.
- **The plan said "2 days".** The FAQ's 72-hour window takes precedence.
- **External data:** none. Everything is synthetic, and city names are used only as warehouse labels.
