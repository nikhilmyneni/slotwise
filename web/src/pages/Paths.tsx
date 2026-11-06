import { useEffect, useState } from "react";
import type { Ctx } from "../main";
import { fmt, Wh } from "../data";
import { Badge, btnSecondary, Card, cx, Delta, ErrorBox, Legend, Loading, PageHeader, Segmented, Select } from "../ui";
import { useWarehouse } from "./MapPage";

function routeLen(r: number[][]) {
  let d = 0;
  for (let i = 1; i < r.length; i++) d += Math.abs(r[i][0] - r[i - 1][0]) + Math.abs(r[i][1] - r[i - 1][1]);
  return Math.ceil(d + 1);
}

export default function Paths({ summary, base, wh, setWh }: Ctx) {
  const { data, error } = useWarehouse(base, wh);
  return (
    <div>
      <PageHeader title="Pick paths"
        lead="Replay a real order on both layouts. Pickers follow an S-shape route: up one aisle, down the next, then back to the dock. Fewer aisles and shorter legs mean less walking. Orders flagged for crossing a blocked aisle are marked."
        who="warehouse operator, logistics analyst" />
      <div className="mb-4">
        <Select label="Warehouse" value={wh} onChange={setWh}
          options={summary.warehouses.map((w) => ({ value: w.id, label: `${w.id} · ${w.name}${w.blocked ? " (blocked aisle)" : ""}` }))} />
      </div>
      {error && <ErrorBox error={error} />}
      {!data && !error && <Loading what="orders" />}
      {data && <div className={data.id !== wh ? "is-stale" : undefined}><PathView data={data} aisleLen={summary.params.aisle_len_m} pitch={summary.params.aisle_pitch_m} /></div>}
    </div>
  );
}

function PathView({ data, aisleLen, pitch }: { data: Wh; aisleLen: number; pitch: number }) {
  const flaggedPicks = new Set(data.exceptions.filter((e) => e.issue_type === "PICK_PATH_USES_BLOCKED_AISLE").map((e) => e.entity_id));
  const orders = data.orders;
  const [oid, setOid] = useState(orders[0]?.id);
  const [show, setShow] = useState<"both" | "base" | "opt">("both");
  const [replay, setReplay] = useState(0);
  useEffect(() => setOid(orders[0]?.id), [data.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const o = orders.find((x) => x.id === oid) ?? orders[0];
  if (!o) return <p className="text-sm text-muted">No sample orders for this warehouse.</p>;
  const aisles = [...new Set(data.locations.map((l) => l[2]))].sort((a, b) => a - b);
  const maxA = aisles[aisles.length - 1];
  const W = (maxA + 1) * pitch, H = aisleLen;
  const blocked = data.blocks.filter((b) => !b.blocked_to).map((b) => b.aisle);
  const temp = data.blocks.filter((b) => b.blocked_to).map((b) => b.aisle);
  const zoneOf = (a: number) => data.zones.find((z) => a >= z.aisle_from && a <= z.aisle_to)?.zone_type ?? "";
  const pad = 1.6;
  const S = 26; // px per metre, so labels are real 12px type
  const sy = (y: number) => H - y;
  const pts = (r: number[][]) => r.map(([x, y]) => `${x},${sy(y)}`).join(" ");
  const badOrder = o.picks.some((p) => flaggedPicks.has(p.pick));
  const locXY = new Map(data.locations.map((l) => [l[0], [l[2] * pitch, (l[3] - 0.5) * 1.2]]));

  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[300px_1fr]">
      <Card title={`${orders.length} sample orders`} subtitle="From the unseen weeks, plus flagged orders">
        <div className="no-scrollbar -mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1 xl:mx-0 xl:block xl:max-h-[560px] xl:space-y-1 xl:overflow-y-auto xl:px-0 xl:pr-1">
          {orders.map((x) => {
            const bad = x.picks.some((p) => flaggedPicks.has(p.pick));
            const save = 100 * (x.base_m - x.opt_m) / (x.base_m || 1);
            return (
              <button key={x.id} onClick={() => setOid(x.id)} aria-pressed={x.id === o.id}
                className={cx("flex w-[210px] shrink-0 snap-start items-center justify-between gap-2 rounded-lg border px-2.5 py-2 text-left text-[13px] xl:w-full",
                  x.id === o.id ? "border-line-strong bg-surface-2" : "border-line hover:bg-surface-2 xl:border-transparent")}>
                <span>
                  <span className="block font-mono text-fg">{x.id}</span>
                  <span className="text-muted">week {x.week} · {x.lines} lines</span>
                </span>
                <span className="text-right">
                  {bad && <Badge tone="bad">blocked aisle</Badge>}
                  <span className={cx("tnum block", save > 0 ? "text-good" : "text-muted")}>{save > 0 ? "−" : ""}{fmt.n(Math.abs(save), 0)}%</span>
                </span>
              </button>
            );
          })}
        </div>
      </Card>
      <Card title={<span className="font-mono">{o.id}</span>}
        subtitle={`${o.lines} lines · ${o.units} units · week ${o.week}`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Segmented label="Routes" value={show} onChange={setShow} options={[{ value: "both", label: "Both" }, { value: "base", label: "Legacy" }, { value: "opt", label: "Proposal" }]} />
            <button className={btnSecondary} onClick={() => setReplay((r) => r + 1)} aria-label="Replay the proposal route">
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden><path d="M4 2.5v11l9-5.5z" fill="currentColor" /></svg>Replay
            </button>
          </div>}>
        <dl className="mb-4 grid grid-cols-3 divide-x divide-[var(--rule)] border-y border-[var(--rule)] py-3">
          <div className="pr-4"><dt className="text-[13px] text-subtle">Legacy route</dt><dd className="tnum mt-1 text-[22px] font-medium tracking-[-0.01em]">{fmt.n(o.base_m, 1)}<span className="ml-1 text-[13px] font-normal text-subtle">m</span></dd></div>
          <div className="px-4"><dt className="text-[13px] text-subtle">Proposal route</dt><dd className="tnum mt-1 text-[22px] font-medium tracking-[-0.01em]">{fmt.n(o.opt_m, 1)}<span className="ml-1 text-[13px] font-normal text-subtle">m</span></dd></div>
          <div className="pl-4"><dt className="text-[13px] text-subtle">Difference</dt><dd className="mt-2"><Delta good={o.base_m >= o.opt_m}>{fmt.n(Math.abs(o.opt_m - o.base_m), 1)} m {o.base_m >= o.opt_m ? "shorter" : "longer"}</Delta></dd></div>
        </dl>
        {badOrder && <div className="mb-3 rounded-md bg-bad-soft p-3 text-[13px] text-[var(--bad-ink)]">Safety exception: the recorded legacy route cut through a blocked aisle. The proposal never slots stock in blocked aisles.</div>}
        <div className="overflow-x-auto">
          <svg viewBox={`${-pad * S} ${-pad * S} ${(W + 2 * pad) * S} ${(H + 2 * pad + 1.4) * S}`} className="w-full min-w-[480px]" role="img" aria-label="Pick route plan, dock bottom left">
            <g transform={`scale(${S})`}>
              {aisles.map((a) => {
                const x = a * pitch;
                const isB = blocked.includes(a), isT = temp.includes(a);
                return (
                  <g key={a}>
                    <rect x={x - pitch / 2 + 0.25} y={0} width={0.6} height={H} fill="var(--rack)" rx={0.08} />
                    <rect x={x + pitch / 2 - 0.85} y={0} width={0.6} height={H} fill="var(--rack)" rx={0.08} />
                    {(isB || isT) && <rect x={x - 0.9} y={0} width={1.8} height={H} fill={isB ? "var(--bad-soft)" : "var(--warn-soft)"} stroke={isB ? "var(--bad)" : "var(--warn)"} strokeWidth={0.06} strokeDasharray="0.3 0.2" />}
                  </g>
                );
              })}
              <rect x={-1.2} y={H - 0.4} width={1.6} height={1.4} rx={0.2} fill="var(--ink)" />
              {show !== "opt" && <polyline points={pts(o.base_route)} fill="none" stroke="var(--base-line)" strokeWidth={0.16} strokeDasharray="0.45 0.3" strokeLinejoin="round" />}
              {show !== "base" && <polyline key={`${o.id}-${replay}`} className="route-draw" style={{ ["--len" as string]: routeLen(o.opt_route) }}
                points={pts(o.opt_route)} fill="none" stroke="var(--hue)" strokeWidth={0.2} strokeLinejoin="round" />}
              {o.picks.map((p) => {
                const b = locXY.get(p.base_loc), q = locXY.get(p.opt_loc);
                return (
                  <g key={p.pick}>
                    {show !== "opt" && b && <circle cx={b[0]} cy={sy(b[1])} r={0.3} fill="var(--surface)" stroke={flaggedPicks.has(p.pick) ? "var(--bad)" : "var(--base-line)"} strokeWidth={0.1} />}
                    {show !== "base" && q && <circle key={`${p.pick}-${replay}`} className="pick-pop" style={{ animationDelay: `${300 + 180 * o.picks.indexOf(p)}ms` }} cx={q[0]} cy={sy(q[1])} r={0.3} fill="var(--hue)" stroke="var(--surface)" strokeWidth={0.08} />}
                  </g>
                );
              })}
            </g>
            {aisles.map((a) => (
              <g key={a}>
                <text x={a * pitch * S} y={(H + 1.1) * S} fontSize={12} textAnchor="middle" fill="var(--fg-subtle)">A{a}</text>
                {a === aisles.find((z) => zoneOf(z) === zoneOf(a)) && <text x={(a * pitch - pitch / 2 + 0.3) * S} y={-0.5 * S} fontSize={12} fill="var(--fg-muted)">{zoneOf(a).charAt(0) + zoneOf(a).slice(1).toLowerCase()}</text>}
              </g>
            ))}
            <text x={-0.4 * S} y={(H + 1.75) * S} fontSize={12} textAnchor="middle" fill="var(--fg)">Dock</text>
          </svg>
        </div>
        <div className="mt-3">
          <Legend items={[{ color: "var(--base-line)", label: "Legacy route", dashed: true }, { color: "var(--hue)", label: "Proposal route" },
            { color: "var(--bad)", label: "Blocked aisle", dashed: true }, { color: "var(--warn)", label: "Temporary block", dashed: true }]} />
        </div>
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-fg">Pick list ({o.picks.length})</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[520px] text-[13px]">
              <thead className="text-subtle"><tr><th className="py-1 text-left font-medium">Pick</th><th className="text-left font-medium">SKU</th><th className="text-right font-medium">Qty</th><th className="text-left font-medium">Legacy slot</th><th className="text-left font-medium">Route aisles</th><th className="text-left font-medium">Proposed slot</th></tr></thead>
              <tbody>
                {o.picks.map((p) => (
                  <tr key={p.pick} className={cx("border-t border-line", flaggedPicks.has(p.pick) && "bg-bad-soft")}>
                    <td className="py-1 font-mono">{p.pick.slice(-3)}</td><td className="font-mono">{p.sku}</td><td className="tnum text-right">{p.qty}</td>
                    <td className="font-mono">{p.base_loc.slice(4)}</td><td className="font-mono">{p.via}</td><td className="font-mono">{p.opt_loc.slice(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
    </div>
  );
}
