# SlotWise

SlotWise is a locally runnable warehouse slotting simulator. A deterministic Python pipeline creates synthetic warehouse and demand data, audits a legacy layout, proposes feasible SKU locations, replays the same orders on both layouts, and reports pick travel and replenishment labour. The Vite/React dashboard lets planners inspect decisions, exceptions, maps, paths, validation, and evaluation.

**Live demo:** https://slotwisely.vercel.app (a static build of the committed outputs; nothing to install to view it)

**Results (full scale, holdout weeks 11-12):** 16.1% less pick travel, +11.1% lines per labour hour and 21.7% less replenishment labour, while moving 907 of 5,000 SKUs with 0 constraint violations. Detection finds 596 of 596 labelled anomalies with 0 false alarms on 92 controls. 107 of 107 integrity checks pass, and two runs from the same seed are byte-identical.

## Submission materials

Everything a reviewer needs beyond the code is in [`submission/`](submission/):

| File | Contents |
|---|---|
| [`prompts/PROMPTS.md`](submission/prompts/PROMPTS.md) | Every prompt sent to the AI tool, in order, with a one-line outcome each |
| [`VERIFICATION.md`](submission/VERIFICATION.md) | Commands run and the real outputs: tests, validation, reproducibility, detection scores, UI checks |
| [`ASSUMPTIONS.md`](submission/ASSUMPTIONS.md) | Assumptions, ID formats not fixed by the brief, extra entities, rules, deviations |
| [`DESIGN_NOTES.md`](submission/DESIGN_NOTES.md) | Architecture, the optimizer's cost function, evaluation choices, likely questions |
| [`LIMITATIONS.md`](submission/LIMITATIONS.md) | What works, known limitations, next steps |

**AI use.** Built with Claude Code (Claude Opus 5.5) as the coding assistant; no other AI tool was used. I set the scope, stack, deployment target, design direction and review criteria, and verified the results as described in `VERIFICATION.md`. No existing solution or third-party code was imported.

## Run

Requires Python 3.11+ (numpy, pandas; pytest for tests) and Node.js 20+. No hosted service, account, secret or external dataset is needed. The dashboard data for both scales is already committed under `web/public/data/`, so `cd web && npm install && npm run dev` works without running Python. Regenerating takes about 15 s at starter scale and about 2 minutes at full scale, and writes about 200 MB to `out/` (git-ignored). Web fonts load from Google Fonts; offline, a system font is used instead.

```powershell
python -m pip install -r requirements.txt
python -m slotting all --scale starter --web
python -m slotting repro --scale starter
cd web
npm install
npm run dev
```

Open the local address printed by Vite. Select **Starter** in the header after generating the starter scale. For the full volume, run `python -m slotting all --scale full --web` and `python -m slotting repro --scale full` from the repository root. `python -m pytest -q` checks the pipeline; `npm run build` checks the dashboard.

The default seed is `20261022`; pass `--seed N` to either pipeline command to reproduce another run. `--out PATH` changes the export directory. The `--web` flag also refreshes `web/public/data/<scale>`.

## Data and rules

The full scale contains 20 warehouses, 10,000 locations, 5,000 SKUs and 100,000 order lines. The starter scale uses the same code path at one fifth of that volume. Masters are generated before orders, picks, replenishment tasks and slot events. IDs and foreign keys remain consistent across tables. Historical slot changes are retained as assignments and events; the proposal is exported separately.

Each candidate slot must fit the SKU dimensions in some rotation, hold a case within volume and weight capacity, match temperature and hazmat zoning, be available, and avoid incompatible hazard pairs in a bay. The engine ranks feasible slots by expected pick and replenishment labour, with a move payback rule. Pick paths replay identical orders on both layouts. Training uses weeks 1–10; weeks 11–12 are a holdout. Peak demand occurs in weeks 9–10.

Five labelled exception families are present: insufficient slot capacity, incompatible goods in one bay, duplicate active locations, picks through blocked aisles, and replenishment over staffed capacity. Labels and expected decisions live in `ground_truth/`, outside the input tables. Synthetic data uses no personal data or external sources.

## Outputs

`out/<scale>/data/` contains CSV and JSON tables, SQLite `slotting.db`, and a SQLite `seed.sql`. `results/` contains proposals, pick path and replenishment comparisons, exceptions, metrics, and detector scores. `ground_truth/` contains the separate answer key. `DATA_DICTIONARY.md` lists every field, type, requirement, units, allowed values, uniqueness and validation. `manifest.json` records seed, generator version, provenance, row counts, file hashes and the generation command. `validation_summary.json` records integrity and rule checks. `repro_report.json` compares row counts and SHA-256 hashes from two runs.

The dashboard is a read-only view of the generated outputs. Re-run the Python command to change the dataset or proposal; the browser does not write operational records.
