# What works, known limitations, next steps

## Works
- **Generator.** A deterministic generator at both scales. It writes CSV, JSON, SQLite and a SQL seed, plus a data dictionary, a manifest with checksums, a separate ground truth, a validation summary and a two-run reproducibility check.
- **Slotting engine.** Applies the hard constraints (fit, weight, temperature, hazmat zoning, bay segregation, blocked locations). The optimizer ranks by velocity and labour cost and only moves a SKU when the move pays back.
- **Simulation.** Replays the same orders on both layouts to compare pick paths, and simulates replenishment shift by shift against the labour roster.
- **Exception detection.** Covers all five required edge cases with suggested actions, and is scored against ground truth and negative controls.
- **Dashboard.** A static dashboard covering KPIs, the floor plan, proposals with a move budget, route replay, labour, exceptions, data validation and evaluation. It has light, dark and system themes and works on phones. It is deployed on Vercel's free tier.

## Limitations
- **Greedy, not optimal.** Assignment is greedy. It is fast and easy to explain, but there is no proof it is optimal and no local-search improvement pass yet.
- **Approximate move-budget savings.** The savings in the move budget are per SKU. Chained moves interact, so the curve is an estimate.
- **Simplified storage.** One forward pick slot per SKU. Reserve storage is not modelled, apart from a fixed trip time.
- **Simplified picking.** Single-order picking only, with no batching or zone picking. The S-shape route is a heuristic, not the shortest path.
- **Simplified labour.** Labour is modelled as minutes per shift. There are no individual workers, skills or equipment.
- **Detection is rule-based.** The labels come from the same rules, so precision and recall of 1.0 are expected (see ASSUMPTIONS.md).
- **Read-only dashboard.** A planner cannot approve or reject moves in the browser; changes come from re-running the pipeline.
- **Synthetic data only.** Distributions are plausible but not calibrated to a real warehouse.
- **Web fonts load from Google Fonts.** Offline, the browser falls back to a system font.

## Next steps
1. A local-search pass (pairwise swaps) after the greedy step, and a report of how far the result is from a lower bound.
2. Batch picking and a multi-order route model; a comparison of S-shape against largest-gap routing.
3. Reserve locations with replenishment travel, and cases or pallets as separate units of measure.
4. A planner workflow: approve or reject proposals, stored durably (for example SQLite through a small API), with an audit trail of slot events.
5. An importer for real data, with a schema mapping and validation report, reusing `validate.py`.
6. A learned anomaly detector evaluated on anomaly types it has not seen, to test generalisation honestly.
