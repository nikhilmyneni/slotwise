# Design notes: what to be able to explain

## Architecture in one line
`slotting/` (Python, numpy and pandas only) generates the dataset, runs the engine, validates the result and exports files. `web/` (Vite, React, Tailwind) is a static dashboard that reads the exported JSON. There is no server, so it hosts free on Vercel and runs offline with `npm run dev`.

```
generate/master.py  -> generate/demand.py -> engine/slotting.py (legacy) -> generate/anomalies.py
   -> pick events (engine/pickpath.py) -> replenishment + roster -> ground truth
engine/run.py (optimize, simulate, detect) -> validate.py -> evaluate.py -> export.py / web_export.py
```

**Why this order.** Master data comes before transactions, so every foreign key refers to a row that already exists. Velocity is derived from order lines, not drawn at random, so it is consistent with the demand. Anomalies are added as new history rows, so the records before them stay valid. Ground truth is written beside the inputs and never into them.

## Key files to walk through
| File | What it does |
|---|---|
| `slotting/config.py` | Every parameter: scales, seed, layout, demand, labour, anomaly volumes |
| `slotting/engine/candidates.py` | Hard constraints as vectorised matrices: fit in any rotation, capacity, temperature, hazmat zoning |
| `slotting/engine/slotting.py` | Greedy assignment, the cost function, the move rule, bay segregation, move reasons |
| `slotting/engine/pickpath.py` | The S-shape route: per-leg distances and the aisles each leg passes through |
| `slotting/engine/replenishment.py` | The min/max refill simulation per shift |
| `slotting/engine/exceptions.py` | Rule checks that read inputs only |
| `slotting/generate/anomalies.py` | Labelled anomaly injection, temporary blocks and negative controls |
| `slotting/validate.py` | 112 integrity and business-rule checks |

## The optimizer
For SKU `s` and a free, feasible location `l`, the expected labour seconds per day are:

```
cost(s,l) = picks/day(s) × 2 × (dist_from_dock(l) + level_penalty(l)) / 0.8 m/s
          + trips/day(s,l) × 360 s
trips/day = units/day(s) / (capacity(s,l) × 0.7)
```

- The current slot gets a bonus of 20 minutes ÷ 60 days. A SKU therefore moves only when the saving repays the move within 60 days.
- **Order of placement:** oversized SKUs first (they fit only the bulk pallets), then hazmat (only hazmat cabinets fit), then everything else by picks per day, fastest first. Fast movers get the nearest free slot they fit.
- **Why greedy:** about 250 SKUs × 500 locations per warehouse. It runs in seconds and every decision can be explained in one line. The trade-off is that it isn't a proven optimum. The natural upgrade is a swap pass, or an assignment-problem (Hungarian/MIP) solve per zone.
- **Why the move rule:** without it, 991 of 1,000 starter SKUs moved, which is unrealistic.

## Evaluation choices
- **Holdout.** Velocity is learned on weeks 1-10, and the travel and labour saving is reported on weeks 11-12. Measuring on the same weeks used for training would overstate the gain.
- **Same orders, both layouts.** Every order is replayed through one route model, so the distances compare like for like.
- **Ground-truth isolation.** The detector never reads the labels. `evaluate.py` is the only module that does, and it runs afterwards. Validation also checks that no input column carries a label.
- **Negative controls.** These are valid cases at each threshold, and they must not be flagged:
  - capacity exactly one case;
  - compatible hazmat classes sharing a bay;
  - labour at 85-100% of capacity;
  - picks outside a block's time window.

## Likely questions, short answers
- **Why is precision and recall 1.0?** The labels come from documented rules, so the score proves the rules are implemented correctly, including the boundaries tested by the controls. It does not prove the detector would catch kinds of anomaly it was never written for.
- **How do you know the proposal is physically valid?** The exception detector runs on the proposal as if it were active and finds 0 issues. Validation also checks that the proposal uses no blocked locations and leaves no SKU unslotted.
- **What is reproducible?** Each generation step uses its own seeded random stream. Two full runs produce byte-identical CSVs (SHA-256 in `repro_report.json`).
- **Why a static site?** Vercel runs static files and short serverless functions, not a long-running Python server. Precomputing keeps the demo fast and free.
- **What did AI do, and what did I decide?** Claude Code wrote most of the code from my prompts. I set the scope, stack, deployment target, design direction, review criteria and authorship. Every prompt is in `submission/prompts/PROMPTS.md`.
