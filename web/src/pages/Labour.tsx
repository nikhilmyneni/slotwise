import { useState } from "react";
import type { Ctx } from "../main";
import { fmt, Wh } from "../data";
import { Badge, Card, ErrorBox, Kpi, Legend, Loading, PageHeader, Select } from "../ui";
import { useWarehouse } from "./MapPage";

export default function Labour({ summary, base, wh, setWh }: Ctx) {
  const { data, error } = useWarehouse(base, wh);
  const pk = summary.metrics.peak_vs_normal;
  const all = summary.metrics.overall;
  return (
    <div>
      <PageHeader title="Replenishment & labour"
        lead={<>Pick slots are topped up from reserve when they fall below {Math.round(summary.params.repl_min_fill * 100)}% of capacity. Each trip costs {summary.params.repl_minutes_per_trip} minutes plus handling.
          Bigger slots for fast movers mean fewer trips; when a shift needs more minutes than the team has, the lowest-priority tasks are deferred and an exception is raised.</>}
        who="operations manager, warehouse operator" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Replenishment trips (12 weeks)" value={fmt.n(all.repl_trips_optimized)} good={all.repl_trips_optimized <= all.repl_trips_baseline}
          before={fmt.n(all.repl_trips_baseline)} after={`${fmt.n(all.repl_trips_optimized)} trips`} />
        <Kpi label="Replenishment labour" value={fmt.n(all.repl_hours_optimized, 0)} unit="h" good={all.repl_hours_optimized <= all.repl_hours_baseline}
          before={`${fmt.n(all.repl_hours_baseline, 0)} h`} after={`${fmt.n(all.repl_hours_optimized, 0)} h`} />
        <Kpi label="Overloaded shifts in peak weeks" value={fmt.n(pk.peak.overloaded_shifts_optimized)} good={pk.peak.overloaded_shifts_optimized <= pk.peak.overloaded_shifts_baseline}
          before={fmt.n(pk.peak.overloaded_shifts_baseline)} after={`${fmt.n(pk.peak.overloaded_shifts_optimized)} shifts`} />
        <Kpi label="Overloaded shifts in normal weeks" value={fmt.n(pk.normal.overloaded_shifts_optimized)} good={pk.normal.overloaded_shifts_optimized <= pk.normal.overloaded_shifts_baseline}
          before={fmt.n(pk.normal.overloaded_shifts_baseline)} after={`${fmt.n(pk.normal.overloaded_shifts_optimized)} shifts`} />
      </div>
      <div className="mb-4 mt-6">
        <Select label="Warehouse" value={wh} onChange={setWh} options={summary.warehouses.map((w) => ({ value: w.id, label: `${w.id} · ${w.name}` }))} />
      </div>
      {error && <ErrorBox error={error} />}
      {!data && !error && <Loading what="labour data" />}
      {data && <div className={data.id !== wh ? "is-stale" : undefined}><ShiftView data={data} peakWeeks={summary.metrics.evaluation_window.peak_weeks} /></div>}
    </div>
  );
}

function ShiftView({ data, peakWeeks }: { data: Wh; peakWeeks: number[] }) {
  const [hov, setHov] = useState<number | null>(null);
  const r = data.repl;
  const n = r.base.length;
  const W = 900, H = 240, L = 44, R = 10, T = 14, B = 26;
  const max = Math.max(...r.base, ...r.opt, ...r.staffed) * 1.1 || 1;
  const x = (i: number) => L + (i / (n - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const line = (vals: number[]) => vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const over = r.base.map((v, i) => ({ i, base: v, opt: r.opt[i], staffed: r.staffed[i], date: r.date[i], shift: r.shift[i] }))
    .filter((s) => s.base > s.staffed || s.opt > s.staffed);
  const pkStart = (peakWeeks[0] - 1) * 14, pkEnd = peakWeeks[peakWeeks.length - 1] * 14 - 1;
  const roster = data.exceptions.filter((e) => e.issue_type === "REPLENISHMENT_EXCEEDS_LABOR_CAPACITY");

  return (
    <div className="grid grid-cols-1 gap-4">
      <Card title={`${data.id}: replenishment minutes per shift`} subtitle="Same demand on both layouts; the staffed line comes from the labour roster (dips are short-staffed shifts)">
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[640px] touch-pan-x" role="img" aria-label="Replenishment workload per shift"
            onPointerLeave={() => setHov(null)}
            onPointerMove={(e) => {
              const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
              const i = Math.round((((e.clientX - r.left) / r.width) * W - L) / ((W - L - R) / (n - 1)));
              setHov(i >= 0 && i < n ? i : null);
            }}>
            <rect x={x(pkStart)} y={T} width={x(pkEnd) - x(pkStart)} height={H - T - B} fill="var(--warn-soft)" opacity={0.6} />
            <text x={x(pkStart) + 4} y={T + 12} fontSize="11" fill="var(--fg-subtle)">Peak weeks</text>
            {[0, 0.5, 1].map((f) => (
              <g key={f}>
                <line x1={L} x2={W - R} y1={y(f * max)} y2={y(f * max)} stroke="var(--border)" />
                <text x={L - 6} y={y(f * max) + 4} fontSize="11" textAnchor="end" fill="var(--fg-subtle)">{Math.round(f * max)}</text>
              </g>
            ))}
            {Array.from({ length: 12 }, (_, w) => (
              <text key={w} x={x(w * 14 + 7)} y={H - 8} fontSize="11" textAnchor="middle" fill="var(--fg-subtle)">W{w + 1}</text>
            ))}
            <polyline points={line(r.base)} fill="none" stroke="var(--base-line)" strokeWidth={1.2} />
            <polyline points={line(r.opt)} fill="none" stroke="var(--accent)" strokeWidth={1.4} />
            <polyline points={line(r.staffed)} fill="none" stroke="var(--bad)" strokeWidth={1.4} strokeDasharray="4 3" />
            {over.map((s) => <circle key={s.i} cx={x(s.i)} cy={y(Math.max(s.base, s.opt))} r={3} fill={s.opt > s.staffed ? "var(--bad)" : "var(--warn)"} />)}
            {hov !== null && (
              <g>
                <line x1={x(hov)} x2={x(hov)} y1={T} y2={H - B} stroke="var(--border-strong)" />
                <circle cx={x(hov)} cy={y(r.base[hov])} r={3.5} fill="var(--base-line)" stroke="var(--surface)" strokeWidth={1.5} />
                <circle cx={x(hov)} cy={y(r.opt[hov])} r={3.5} fill="var(--hue)" stroke="var(--surface)" strokeWidth={1.5} />
              </g>
            )}
          </svg>
        </div>
        <p className="tnum mt-2 min-h-9 rounded-md bg-surface-2 px-3 py-2 text-[13px] text-muted" aria-live="polite">
          {hov === null ? "Hover or drag across the chart to read a shift." :
            `${r.date[hov]} ${r.shift[hov]} shift · staffed ${r.staffed[hov]} min · legacy ${fmt.n(r.base[hov])} min · proposal ${fmt.n(r.opt[hov])} min` +
            (r.opt[hov] > r.staffed[hov] ? " · still over capacity" : r.base[hov] > r.staffed[hov] ? " · overload resolved by the proposal" : "")}
        </p>
        <div className="mt-2"><Legend items={[{ color: "var(--base-line)", label: "Legacy workload" }, { color: "var(--accent)", label: "Optimized workload" },
          { color: "var(--bad)", label: "Staffed minutes", dashed: true }]} /></div>
      </Card>
      <Card title={`${over.length} shifts over capacity`} subtitle="Red: still over capacity with the proposal. Amber: fixed by the proposal.">
        {over.length === 0 && <p className="text-sm text-muted">No shift exceeds the staffed minutes in this warehouse.</p>}
        <div className="flex flex-wrap gap-2">
          {over.map((s) => (
            <div key={s.i} className="rounded-lg border border-line px-3 py-2 text-[13px]">
              <div className="font-medium text-fg">{s.date} {s.shift}</div>
              <div className="tnum text-muted">staffed {s.staffed} · legacy {fmt.n(s.base)} · new {fmt.n(s.opt)} min</div>
              {s.opt > s.staffed ? <Badge tone="bad">Add labour or defer C-class</Badge> : <Badge tone="good">Resolved by proposal</Badge>}
            </div>
          ))}
        </div>
        {roster.length > 0 && <p className="mt-3 text-[13px] text-subtle">{roster.length} of these were raised as exceptions on the recorded (legacy) history; see the Exceptions page.</p>}
      </Card>
    </div>
  );
}
