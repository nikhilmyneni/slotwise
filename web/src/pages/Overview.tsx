import { useState } from "react";
import type { Ctx } from "../main";
import { fmt, type Kpi as K } from "../data";
import type { ReactNode } from "react";
import { btnPrimary, btnSecondary, Card, Delta, Kpi, LineChart, PairBars, Segmented } from "../ui";

/*
  Screen question: "Is the proposal worth executing, and is it safe?"
  Biggest thing: the holdout pick-travel saving with its weekly evidence.
  Grid: centred 1200px column, one 16px gap; rows of 2/3 + 1/3, 4 equal KPIs, 1/2 + 1/2, full-width table.
*/
export default function Overview({ summary, go, base, prefetchWh }: Ctx) {
  const m = summary.metrics;
  const [win, setWin] = useState<"holdout" | "overall">("holdout");
  const k = m[win];
  const ev = summary.evaluation;
  const v = summary.validation;
  const weeks = summary.weekly.map((w) => w.week_no);
  const peak = m.evaluation_window.peak_weeks;
  const hold = summary.manifest.horizon.train_weeks + 1;
  const winLabel = win === "holdout" ? `unseen weeks ${m.evaluation_window.holdout_weeks}` : "all 12 weeks";
  const forced = m.moves_by_reason.FORCED_CURRENT_INFEASIBLE ?? 0;
  const taken = m.moves_by_reason.FORCED_CURRENT_TAKEN ?? 0;
  const saving = m.moves_by_reason.LABOUR_SAVING ?? 0;
  const auditExceptions = Object.entries(m.exceptions_by_type).filter(([t]) => !t.startsWith("OPTIMIZED") && t !== "NO_FEASIBLE_SLOT")
    .reduce((s, [, n]) => s + n, 0);
  const replPct = k.repl_hours_baseline ? (100 * (k.repl_hours_optimized - k.repl_hours_baseline)) / k.repl_hours_baseline : 0;

  return (
    <div className="space-y-4">
      {/* Title row: the question, the finding, the main job */}
      <div className="mb-2 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[760px]">
          <h1 className="text-[24px] font-semibold leading-tight tracking-[-0.01em]">Network slotting proposal</h1>
          <p className="mt-2 text-[14px] leading-relaxed text-muted">
            Moving <span className="tnum font-medium text-fg">{fmt.n(m.skus_moved)}</span> of {fmt.n(m.skus_total)} SKUs cuts pick travel by{" "}
            <span className="tnum font-medium text-fg">{fmt.pct(m.holdout.distance_saving_pct)}</span> on weeks the optimizer never saw, with{" "}
            <span className="tnum font-medium text-fg">{m.constraint_violations_optimized}</span> rule violations. {fmt.n(forced)} of those moves are mandatory: the legacy slot does not fit the SKU.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a className={btnSecondary} href={`${base}/slot_proposals.csv`} download>Download proposal</a>
          <button className={btnPrimary} onClick={() => go("proposals")}>Review {fmt.n(m.skus_moved)} moves</button>
        </div>
      </div>

      {/* Headline: answer + evidence, and the proposal ledger */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section className="min-w-0 rounded-lg border border-line bg-surface xl:col-span-2" aria-labelledby="h-travel">
          <div className="flex flex-wrap items-start justify-between gap-4 px-5 pt-5">
            <div>
              <h2 id="h-travel" className="text-[15px] font-semibold">Pick travel per order</h2>
              <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="tnum text-[44px] font-medium leading-none tracking-[-0.03em]">{fmt.n(k.distance_saving_pct, 1)}%</span>
                <span className="text-[14px] text-muted">less walking on {winLabel}</span>
              </div>
              <p className="tnum mt-2 text-[13px] text-subtle">
                {fmt.n(k.avg_distance_baseline_m, 1)} m → <span className="text-fg">{fmt.n(k.avg_distance_optimized_m, 1)} m</span> per order ·{" "}
                {fmt.n(k.orders)} orders replayed on both layouts · {fmt.n(k.distance_baseline_km - k.distance_optimized_km, 0)} km saved
              </p>
            </div>
            <Segmented label="Measurement window" value={win} onChange={setWin}
              options={[{ value: "holdout", label: `Unseen W${m.evaluation_window.holdout_weeks}` }, { value: "overall", label: "All weeks" }]} />
          </div>
          <div className="px-3 pb-3 pt-2">
            <LineChart xs={weeks} yLabel="Average metres walked per order, by week" height={262} format={(x) => `${x.toFixed(0)} m`}
              bands={[{ from: peak[0], to: peak[peak.length - 1], label: "Peak", color: "var(--band-peak)" },
                { from: hold, to: weeks[weeks.length - 1], label: "Unseen", color: "var(--band-hold)" }]}
              series={[{ name: "Legacy", color: "var(--base-line)", values: summary.weekly.map((w) => w.base), width: 1.75 },
                { name: "Proposal", color: "var(--hue)", values: summary.weekly.map((w) => w.opt), width: 2.5 }]} />
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-2 text-[13px] text-subtle">
              <span className="inline-flex items-center gap-1.5"><i className="inline-block h-[2px] w-4" style={{ background: "var(--base-line)" }} />Legacy layout</span>
              <span className="inline-flex items-center gap-1.5"><i className="inline-block h-[3px] w-4 bg-hue" />Proposal</span>
              <span>Velocity learned on weeks 1-{summary.manifest.horizon.train_weeks}; peak demand in weeks {peak.join("-")}.</span>
            </div>
          </div>
        </section>

        <section className="min-w-0 rounded-lg border border-line bg-surface px-5 py-5" aria-labelledby="h-ledger">
          <h2 id="h-ledger" className="text-[15px] font-semibold">The proposal</h2>
          <div className="mt-4">
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] text-subtle">SKUs that move</span>
              <span className="tnum text-[14px]"><span className="font-medium">{fmt.n(m.skus_moved)}</span> <span className="text-subtle">of {fmt.n(m.skus_total)}</span></span>
            </div>
            <div className="mt-2 flex h-2 overflow-hidden rounded-[2px] bg-[var(--rule)]" role="img"
              aria-label={`${forced} mandatory, ${taken} displaced, ${saving} for labour saving`}>
              <span style={{ width: `${(100 * forced) / m.skus_total}%` }} className="bg-ink" />
              <span style={{ width: `${(100 * taken) / m.skus_total}%` }} className="bg-[var(--base-line)]" />
              <span style={{ width: `${(100 * saving) / m.skus_total}%` }} className="bg-hue" />
            </div>
            <ul className="mt-2 space-y-1 text-[13px]">
              <LegendRow color="var(--ink)" label="Mandatory, slot breaks a rule" n={forced} />
              <LegendRow color="var(--base-line)" label="Displaced by a faster SKU" n={taken} />
              <LegendRow color="var(--hue)" label="Moved to save labour" n={saving} />
            </ul>
          </div>
          <dl className="mt-5 divide-y divide-[var(--rule)] text-[13px]">
            <Row label="Rule violations in proposal" value={<Status ok={m.constraint_violations_optimized === 0} text={`${m.constraint_violations_optimized}`} />} />
            <Row label="Open exceptions on legacy data" value={<button className="tnum font-medium underline decoration-line-strong underline-offset-4 hover:decoration-ink" onClick={() => go("exceptions")}>{fmt.n(auditExceptions)}</button>} />
            <Row label="Integrity checks" value={<Status ok={v.failed === 0} text={`${v.passed} of ${v.passed + v.failed} pass`} />} />
            <Row label="Labelled anomalies found" value={<Status ok={ev.overall.fn === 0} text={`${fmt.n(ev.overall.tp)} of ${fmt.n(ev.overall.tp + ev.overall.fn)}`} />} />
            <Row label="False alarms on controls" value={<Status ok={ev.negative_controls.false_alarms === 0} text={`${ev.negative_controls.false_alarms} of ${ev.negative_controls.controls}`} />} />
            <Row label="Reproducible from seed" value={<Status ok={!!summary.repro?.all_identical} text={summary.repro ? `${summary.repro.files.length} files identical` : "not run"} />} />
          </dl>
        </section>
      </div>

      {/* Operational impact */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Lines per labour hour" value={fmt.n(k.lines_per_hour_optimized, 1)} good
          before={fmt.n(k.lines_per_hour_baseline, 1)} after={<Delta good>{fmt.pct(k.throughput_gain_pct)} throughput</Delta>} />
        <Kpi label="Replenishment labour" value={fmt.n(k.repl_hours_optimized, 0)} unit="h" good={replPct <= 0}
          before={`${fmt.n(k.repl_hours_baseline, 0)} h`} after={<Delta good={replPct <= 0}>{fmt.pct(Math.abs(replPct))} {replPct <= 0 ? "less" : "more"}</Delta>} />
        <Kpi label="Shifts over labour capacity" value={fmt.n(k.overloaded_shifts_optimized)} good={k.overloaded_shifts_optimized <= k.overloaded_shifts_baseline}
          before={`${fmt.n(k.overloaded_shifts_baseline)} legacy`} after={`${fmt.n(k.overloaded_shifts_baseline - k.overloaded_shifts_optimized)} fewer`} />
        <Kpi label="Aisles entered per order" value={fmt.n(k.avg_aisles_optimized, 2)} good={k.avg_aisles_optimized <= k.avg_aisles_baseline}
          before={fmt.n(k.avg_aisles_baseline, 2)} after={`${fmt.n(k.total_labour_hours_baseline - k.total_labour_hours_optimized, 0)} labour h saved`} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Where the fast movers sit" subtitle="Average distance from the dock by velocity class, legacy against proposal">
          <PairBars unit="m" rows={(["A", "B", "C"] as const).map((c) => ({
            label: `${c}-class`, a: m.velocity_slotting.baseline[c].avg_dist_m, b: m.velocity_slotting.optimized[c].avg_dist_m,
            note: `${fmt.n(m.velocity_slotting.baseline[c].avg_dist_m, 1)} → ${fmt.n(m.velocity_slotting.optimized[c].avg_dist_m, 1)} m`,
          }))} />
          <dl className="mt-5 grid grid-cols-3 border-t border-[var(--rule)] pt-4 text-[13px]">
            {(["A", "B", "C"] as const).map((c) => (
              <div key={c}>
                <dt className="text-subtle">{c} in golden zone</dt>
                <dd className="tnum mt-1 text-[15px] font-medium">{fmt.pct(m.velocity_slotting.optimized[c].golden_zone_pct, 0)}
                  <span className="ml-1 text-[13px] font-normal text-subtle">from {fmt.pct(m.velocity_slotting.baseline[c].golden_zone_pct, 0)}</span></dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[13px] text-subtle">Golden zone: shelf levels 1-2, picked without reaching. A-class: SKUs making the first {Math.round(summary.params.abc_cutoffs[0] * 100)}% of picks in their warehouse.</p>
        </Card>
        <Card title="How many moves are worth it" subtitle="Modelled labour saved per day when the best moves are executed first">
          <MoveCurve curve={m.move_curve} />
        </Card>
      </div>

      <NetworkTable summary={summary} win={win} go={go} prefetchWh={prefetchWh} />

      <p className="px-1 pt-2 text-[13px] leading-relaxed text-subtle">
        Both layouts replay identical orders through the same S-shape route model, so distances compare like for like. A SKU moves only when its saving repays the
        {" "}{summary.params.move_cost_minutes}-minute move within {summary.params.move_payback_days} days. Full method on the <a href="#/method" className="text-fg underline underline-offset-4">Method</a> page.
      </p>
    </div>
  );
}

function LegendRow({ color, label, n }: { color: string; label: string; n: number }) {
  return (
    <li className="flex items-center justify-between gap-2">
      <span className="inline-flex items-center gap-2 text-muted"><i className="inline-block h-2 w-2 rounded-[2px]" style={{ background: color }} />{label}</span>
      <span className="tnum text-fg">{fmt.n(n)}</span>
    </li>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-fg">{value}</dd>
    </div>
  );
}

function Status({ ok, text }: { ok: boolean; text: string }) {
  return (
    <span className="tnum inline-flex items-center gap-2 font-medium">
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-good" : "bg-bad"}`} aria-hidden />
      {text}
      <span className="sr-only">{ok ? "(passing)" : "(needs attention)"}</span>
    </span>
  );
}

function NetworkTable({ summary, win, go, prefetchWh }: { summary: Ctx["summary"]; win: "holdout" | "overall"; go: Ctx["go"]; prefetchWh: (id: string) => void }) {
  const rows = summary.warehouses.map((w) => ({ ...w, k: w.kpi[win === "holdout" ? "holdout" : "all"] as K }));
  const max = Math.max(...rows.map((r) => r.k.distance_saving_pct), 1);
  const [sort, setSort] = useState<"id" | "saving">("id");
  const sorted = [...rows].sort((a, b) => (sort === "id" ? a.id.localeCompare(b.id) : b.k.distance_saving_pct - a.k.distance_saving_pct));
  return (
    <Card title="Warehouses" subtitle={`${rows.length} sites, measured on ${win === "holdout" ? "the unseen weeks" : "all 12 weeks"}`}
      action={<Segmented label="Sort warehouses" value={sort} onChange={setSort} options={[{ value: "id", label: "By site" }, { value: "saving", label: "By saving" }]} />}>
      <div className="-mx-5 overflow-x-auto px-5">
        <table className="w-full min-w-[860px] text-[14px]">
          <thead className="text-left text-[13px] text-subtle">
            <tr className="border-b border-line">
              <th className="pb-2 font-medium">Site</th>
              <th className="pb-2 font-medium">City</th>
              <th className="pb-2 text-right font-medium">SKUs</th>
              <th className="pb-2 text-right font-medium">Orders</th>
              <th className="pb-2 text-right font-medium">Legacy m/order</th>
              <th className="pb-2 text-right font-medium">Proposal m/order</th>
              <th className="w-[200px] pb-2 pl-6 font-medium">Travel saved</th>
              <th className="pb-2 text-right font-medium">Repl. hours</th>
              <th className="pb-2 text-right font-medium">Exceptions</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id} tabIndex={0} onClick={() => go("map", { wh: r.id })} onMouseEnter={() => prefetchWh(r.id)} onFocus={() => prefetchWh(r.id)}
                onKeyDown={(e) => { if (e.key === "Enter") go("map", { wh: r.id }); }}
                className="cursor-pointer border-b border-[var(--rule)] last:border-b-0 hover:bg-surface-2 focus-visible:bg-surface-2">
                <td className="py-2.5 font-medium">{r.id}{r.blocked && <span className="ml-2 text-[12px] font-normal text-subtle">aisle blocked</span>}</td>
                <td className="py-2.5 text-muted">{r.city}</td>
                <td className="tnum py-2.5 text-right">{fmt.n(r.skus)}</td>
                <td className="tnum py-2.5 text-right">{fmt.n(r.k.orders)}</td>
                <td className="tnum py-2.5 text-right text-subtle">{fmt.n(r.k.avg_distance_baseline_m, 1)}</td>
                <td className="tnum py-2.5 text-right">{fmt.n(r.k.avg_distance_optimized_m, 1)}</td>
                <td className="py-2.5 pl-6">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-[2px] bg-[var(--rule)]">
                      <div className="h-full rounded-[2px] bg-hue" style={{ width: `${(100 * Math.max(0, r.k.distance_saving_pct)) / max}%` }} />
                    </div>
                    <span className="tnum w-12 text-right">{fmt.pct(r.k.distance_saving_pct)}</span>
                  </div>
                </td>
                <td className="tnum py-2.5 text-right"><span className="text-subtle">{fmt.n(r.k.repl_hours_baseline, 0)} →</span> {fmt.n(r.k.repl_hours_optimized, 0)}</td>
                <td className="tnum py-2.5 text-right">{r.exceptions ? fmt.n(r.exceptions) : <span className="text-subtle">0</span>}</td>
                <td className="py-2.5 pl-3 text-right"><span className="whitespace-nowrap text-[13px] text-muted" aria-hidden>Floor plan →</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function MoveCurve({ curve }: { curve: { moves: number; saving_hours_per_day: number }[] }) {
  const W = 600, H = 200, L = 46, R = 14, T = 14, B = 28;
  const maxX = Math.max(...curve.map((c) => c.moves)) || 1;
  const total = curve[curve.length - 1]?.saving_hours_per_day ?? 0;
  const maxY = total * 1.12 || 1;
  const x = (v: number) => L + (v / maxX) * (W - L - R);
  const y = (v: number) => T + (1 - v / maxY) * (H - T - B);
  const knee = curve.find((c) => c.saving_hours_per_day >= 0.8 * total);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Cumulative labour saving by number of moves executed">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={L} x2={W - R} y1={y(f * total)} y2={y(f * total)} stroke="var(--rule)" />
            <text x={L - 8} y={y(f * total) + 4} fontSize="11" textAnchor="end" fill="var(--fg-subtle)">{(f * total).toFixed(1)} h</text>
          </g>
        ))}
        <polyline fill="none" stroke="var(--hue)" strokeWidth={2.5} strokeLinejoin="round" points={curve.map((c) => `${x(c.moves)},${y(c.saving_hours_per_day)}`).join(" ")} />
        {knee && (
          <g>
            <line x1={x(knee.moves)} x2={x(knee.moves)} y1={y(knee.saving_hours_per_day)} y2={H - B} stroke="var(--ink)" strokeDasharray="3 3" />
            <circle cx={x(knee.moves)} cy={y(knee.saving_hours_per_day)} r={4} fill="var(--ink)" stroke="var(--surface)" strokeWidth={1.5} />
            <text x={x(knee.moves) + 8} y={y(knee.saving_hours_per_day) + 16} fontSize="12" fill="var(--fg)">{knee.moves.toLocaleString()} moves = 80% of the saving</text>
          </g>
        )}
        <text x={L} y={H - 8} fontSize="11" fill="var(--fg-subtle)">0</text>
        <text x={W - R} y={H - 8} fontSize="11" textAnchor="end" fill="var(--fg-subtle)">{maxX.toLocaleString()} moves</text>
      </svg>
      <p className="tnum mt-1 text-[13px] text-subtle">All moves together save about <span className="text-fg">{total.toFixed(1)} labour hours a day</span> in modelled pick walking and replenishment.</p>
    </div>
  );
}
