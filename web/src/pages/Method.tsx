import type { Ctx } from "../main";
import { Card, PageHeader } from "../ui";

const STEPS = [
  ["Master data", "20 warehouses with 5 zones each (ambient, bulk pallets, chilled, frozen, hazmat), laid out from the dock outward. Every location has real dimensions and a weight limit."],
  ["SKUs and demand", "SKUs get sizes, weights, temperature and hazard classes. 12 weeks of orders follow a Zipf curve (a few fast movers, a long tail), with a peak in weeks 9-10 where a seasonal cohort surges."],
  ["Derived velocity", "Picks per day and A/B/C class are computed from the order lines, never drawn at random. A = SKUs making the first 80% of picks in their warehouse."],
  ["Legacy layout + anomalies", "A legacy layout is placed at random but legally. Then labelled problems are injected as new history records: oversized items in small bins, incompatible chemicals in one bay, two SKUs on one slot, picks through blocked aisles, and short-staffed shifts."],
  ["Candidate slots", "For each SKU the engine keeps only locations that are active, match its temperature and hazmat zone, fit its dimensions in any rotation, and hold at least one case within the weight limit."],
  ["Assignment", "SKUs are placed in order: oversized, hazmat, then by pick frequency. Each takes the free feasible slot with the lowest expected daily labour, keeping incompatible hazards out of the same bay."],
  ["Simulation", "Every historical order is replayed on both layouts with the same S-shape route model, and replenishment is simulated shift by shift against the labour roster."],
  ["Checks", "Constraint audit of the proposal, exception detection on the data, validation of keys and arithmetic, scoring against ground truth, and a two-run reproducibility check."],
];

export default function Method({ summary }: Ctx) {
  const p = summary.params;
  return (
    <div>
      <PageHeader title="How it works" lead="One Python pipeline generates the data, slots the SKUs, simulates operations and checks itself. This dashboard is a static view of its outputs." />
      <Card title="The pipeline" subtitle="One deterministic run, in this order">
        <ol className="divide-y divide-[var(--rule)]">
          {STEPS.map(([t, d]) => (
            <li key={t} className="grid grid-cols-1 gap-1 py-3 first:pt-0 last:pb-0 md:grid-cols-[220px_1fr] md:gap-6">
              <span className="text-[14px] font-medium text-fg">{t}</span>
              <p className="text-[14px] leading-relaxed text-muted">{d}</p>
            </li>
          ))}
        </ol>
      </Card>
      <div className="mt-4 grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
        <Card title="Slot cost (what the optimizer minimises)">
          <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[12px] leading-relaxed text-fg">{`cost(sku, slot) per day =
    picks/day × 2 × (distance from dock + level penalty) / ${p.walk_speed_mps} m/s
  + replenishment trips/day × ${p.repl_minutes_per_trip} min

trips/day = units/day ÷ (capacity × ${1 - p.repl_min_fill})
capacity  = min(85% volume fill, weight limit, ${p.max_cases_per_slot} cases)

stay bonus = ${p.move_cost_minutes} min ÷ ${p.move_payback_days} days
  (a SKU moves only if the move pays back in ${p.move_payback_days} days)`}</pre>
        </Card>
        <Card title="Rules enforced on every slot">
          <ul className="space-y-1.5 text-sm text-muted">
            <li>Location must be active (no blocked aisles).</li>
            <li>Zone temperature equals the SKU's temperature class.</li>
            <li>Hazmat SKUs only in hazmat zones, and only hazmat there.</li>
            <li>Unit fits the location in some rotation; capacity holds at least one case; weight within the limit.</li>
            <li>Never two active SKUs on one location.</li>
            <li>No incompatible hazard pair in one bay: {p.incompatible_pairs.map((x) => x.join(" + ").toLowerCase()).join("; ")}.</li>
          </ul>
        </Card>
        <Card title="Pick path model">
          <p className="text-sm leading-relaxed text-muted">Aisles are {p.aisle_pitch_m} m apart and {p.aisle_len_m} m long with {p.bays} bays and {p.levels} levels. The picker leaves the dock, visits the aisles that hold picks in order,
            going up one and down the next, and returns to the dock. Distances are measured along aisles and cross-aisles. Level 3 adds a reach penalty in the cost but not in walking distance.</p>
        </Card>
        <Card title="Limits we are open about">
          <ul className="space-y-1.5 text-sm text-muted">
            <li>Greedy assignment is fast and explainable but not a proven optimum.</li>
            <li>One pick slot per SKU; no reserve-location modelling beyond trip time.</li>
            <li>Savings in the move budget are per SKU; chained moves interact, so they are approximate.</li>
            <li>Detection labels come from the same documented rules, so a perfect score checks correctness, not generalisation.</li>
          </ul>
        </Card>
      </div>
      <Card className="mt-4" title="Reproduce everything">
        <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[12px] leading-relaxed text-fg">{`pip install -r requirements.txt
python -m slotting all   --scale full --web     # generate, optimize, validate, export (~80 s)
python -m slotting repro --scale full           # regenerate twice, compare SHA-256
cd web && npm install && npm run dev            # this dashboard`}</pre>
      </Card>
    </div>
  );
}
