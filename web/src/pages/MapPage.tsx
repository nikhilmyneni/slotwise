import { useMemo, useState } from "react";
import type { Ctx } from "../main";
import { fmt, LocRow, MOVE_LABEL, Sku, useData, Wh } from "../data";
import { Badge, Card, cx, ErrorBox, Legend, Loading, PageHeader, Search, Segmented, Select } from "../ui";

const ZONE_NAME: Record<string, string> = { AMB: "Ambient", BLK: "Bulk pallets", CHL: "Chilled", FRZ: "Frozen", HAZ: "Hazmat" };
const ZONE_COLOR: Record<string, string> = { AMB: "var(--zone-amb)", BLK: "var(--zone-blk)", CHL: "var(--zone-chl)", FRZ: "var(--zone-frz)", HAZ: "var(--zone-haz)" };

export function useWarehouse(base: string, id: string) {
  return useData<Wh>(`${base}/wh/${id}.json`);
}

export default function MapPage({ summary, base, wh, setWh }: Ctx) {
  const [plan, setPlan] = useState<"base" | "opt">("opt");
  const [colour, setColour] = useState<"cls" | "zone">("cls");
  const [sel, setSel] = useState<string | null>(null);
  const [q, setQ] = useState(() => new URLSearchParams(window.location.hash.split("?")[1] || "").get("sku") ?? "");
  const [focus, setFocus] = useState<"all" | "moved" | "issues">("all");
  const { data, error } = useWarehouse(base, wh);

  return (
    <div>
      <PageHeader title="Floor plan"
        lead="Every pick location, seen from above. The dock is bottom-left; travel grows to the right and up. Switch between the legacy layout and the proposal to see fast movers pulled toward the dock. Click any slot to see why a SKU is there."
        who="slotting planner, warehouse operator" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select label="Warehouse" value={wh} onChange={(v) => { setWh(v); setSel(null); }}
          options={summary.warehouses.map((w) => ({ value: w.id, label: `${w.id} · ${w.name}` }))} />
        <Segmented label="Layout" value={plan} onChange={setPlan} options={[{ value: "base", label: "Legacy" }, { value: "opt", label: "Proposal" }]} />
        <Segmented label="Colour by" value={colour} onChange={setColour} options={[{ value: "cls", label: "Velocity" }, { value: "zone", label: "Zone" }]} />
        <Segmented label="Highlight" value={focus} onChange={setFocus} options={[{ value: "all", label: "All slots" }, { value: "moved", label: "Moves" }, { value: "issues", label: "Rule breaks" }]} />
        <Search value={q} onChange={setQ} placeholder="Find SKU, e.g. SKU-000123" />
      </div>
      {error && <ErrorBox error={error} />}
      {!data && !error && <Loading what="warehouse" />}
      {data && <div className={data.id !== wh ? "is-stale" : undefined}><MapView data={data} plan={plan} colour={colour} sel={sel} setSel={setSel} q={q} focus={focus} /></div>}
    </div>
  );
}

function MapView({ data, plan, colour, sel, setSel, q, focus }: {
  data: Wh; plan: "base" | "opt"; colour: "cls" | "zone"; sel: string | null; setSel: (s: string | null) => void; q: string;
  focus: "all" | "moved" | "issues";
}) {
  const [hov, setHov] = useState<LocRow | null>(null);
  const skus = useMemo(() => new Map(data.skus.map((s) => [s.id, s])), [data]);
  const byAisle = useMemo(() => {
    const m = new Map<number, LocRow[]>();
    data.locations.forEach((l) => { if (!m.has(l[2])) m.set(l[2], []); m.get(l[2])!.push(l); });
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [data]);
  const locIdx = useMemo(() => new Map(data.locations.map((l) => [l[0], l])), [data]);
  const query = q.trim().toUpperCase();
  const found = query.length >= 5 ? data.skus.find((s) => s.id.includes(query)) : undefined;
  const hl = new Set<string>(found ? [found.base_loc, found.opt_loc ?? ""] : []);
  const blocked = new Set(data.blocks.filter((b) => !b.blocked_to).map((b) => b.aisle));
  const temp = new Set(data.blocks.filter((b) => b.blocked_to).map((b) => b.aisle));
  const exLocs = new Set(data.exceptions.filter((e) => e.entity_type === "SlotAssignment").flatMap((e) => {
    const s = data.skus.find((x) => x.base_slot === e.entity_id);
    return s ? [s.base_loc] : [];
  }));

  const fill = (l: LocRow) => {
    const occ = plan === "base" ? l[8] : l[9];
    if (l[7] === "BLOCKED") return "var(--bad-soft)";
    if (colour === "zone") return occ.length ? ZONE_COLOR[l[1]] : "var(--empty)";
    if (!occ.length) return "var(--empty)";
    const c = skus.get(occ[0])?.[plan === "opt" ? "train_cls" : "cls"] ?? skus.get(occ[0])?.cls;
    return c === "A" ? "var(--cls-a)" : c === "B" ? "var(--cls-b)" : "var(--cls-c)";
  };
  const movedLocs = useMemo(() => new Set(data.skus.filter((s) => s.move && s.move !== "STAY")
    .flatMap((s) => [s.base_loc, s.opt_loc ?? ""])), [data]);
  const dim = (l: LocRow) => focus === "moved" ? !movedLocs.has(l[0]) : focus === "issues" ? !exLocs.has(l[0]) : false;
  const readout = (l: LocRow) => {
    const occ = plan === "base" ? l[8] : l[9];
    const s = occ[0] ? skus.get(occ[0]) : undefined;
    return `${l[0].slice(4)} · aisle ${l[2]}, bay ${l[3]}, level ${l[4]} · ${l[10]} m from dock · ` +
      (l[7] === "BLOCKED" ? "blocked" : s ? `${s.id} ${s.cls}-class, ${s.ppd.toFixed(2)} picks/day${occ.length > 1 ? ` (+${occ.length - 1} more, duplicate)` : ""}` : "empty");
  };
  const selLoc = sel ? locIdx.get(sel) : undefined;
  const k = data.kpi?.holdout;

  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[1fr_360px]">
      <Card title={`${data.id} floor plan`} subtitle={`${data.locations.length} locations in ${byAisle.length} aisles · each bay shows 2 sides × 3 levels`}
        action={k && <Badge tone="accent">Unseen weeks: {fmt.pct(k.distance_saving_pct)} less travel</Badge>}>
        <p className="tnum mb-3 min-h-10 rounded-md bg-surface-2 px-3 py-2 text-[13px] leading-snug text-muted" aria-live="polite">
          {hov ? readout(hov) : selLoc ? readout(selLoc) : "Hover or tap a slot to read it. Tap selects it and opens the details."}
        </p>
        <div className="-mx-1 overflow-x-auto px-1 pb-2">
          <div className="flex min-w-[560px] items-end gap-1.5">
            <div className="flex flex-col items-center justify-end pb-6 pr-1 text-[11px] text-subtle"><span className="rotate-180 [writing-mode:vertical-rl]">Dock side, front cross-aisle</span></div>
            {byAisle.map(([aisle, locs]) => {
              const zone = locs[0][1];
              const bays = new Map<number, LocRow[]>();
              locs.forEach((l) => { if (!bays.has(l[3])) bays.set(l[3], []); bays.get(l[3])!.push(l); });
              return (
                <div key={aisle} className="flex min-w-0 flex-1 flex-col items-stretch">
                  <div className="mb-1 h-4 truncate text-center text-[11px] text-subtle"><span className="md:hidden">{zone[0] + zone.slice(1).toLowerCase()}</span><span className="hidden md:inline">{ZONE_NAME[zone]?.split(" ")[0]}</span></div>
                  <div className={cx("flex flex-col-reverse gap-1 rounded-md p-1",
                    blocked.has(aisle) ? "bg-bad-soft outline-1 outline-bad outline-dashed" : temp.has(aisle) ? "bg-warn-soft" : "bg-surface-2")}>
                    {Array.from({ length: 8 }, (_, b) => b + 1).map((bay) => {
                      const cell = bays.get(bay) ?? [];
                      return (
                        <div key={bay} className="grid grid-cols-2 gap-[2px]">
                          {(["L", "R"] as const).map((side) => (
                            <div key={side} className="flex min-w-0 flex-col-reverse gap-[2px]">
                              {[1, 2, 3].map((lv) => {
                                const l = cell.find((c) => c[5] === side && c[4] === lv);
                                if (!l) return <span key={lv} className="block h-[11px] w-full" />;
                                const isSel = sel === l[0], isHl = hl.has(l[0]);
                                const flagged = plan === "base" && exLocs.has(l[0]);
                                return (
                                  <button key={lv} aria-label={readout(l)} aria-pressed={isSel} onClick={() => setSel(l[0])}
                                    onMouseEnter={() => setHov(l)} onFocus={() => setHov(l)} onMouseLeave={() => setHov(null)}
                                    className={cx("block h-[11px] w-full rounded-[2px] hover:brightness-90", (isSel || isHl) && "ring-2 ring-ink ring-offset-1 ring-offset-surface",
                                      flagged && "outline-2 outline-bad")}
                                    style={{ background: fill(l), opacity: dim(l) ? 0.18 : 1 }} />
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                  <div className={cx("tnum mt-1 text-center text-[11px]", blocked.has(aisle) ? "font-medium text-bad" : "text-subtle")}>A{aisle}</div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="mt-3">
          {colour === "cls"
            ? <Legend items={[{ color: "var(--cls-a)", label: "A: fastest 80% of picks" }, { color: "var(--cls-b)", label: "B: next 15%" }, { color: "var(--cls-c)", label: "C: slow" },
              { color: "var(--empty)", label: "Empty" }, { color: "var(--bad)", label: "Blocked aisle", dashed: true }]} />
            : <Legend items={Object.entries(ZONE_NAME).map(([k2, v]) => ({ color: ZONE_COLOR[k2], label: v }))} />}
          {plan === "base" && exLocs.size > 0 && <p className="mt-2 text-[13px] text-bad">Red outlines mark legacy slots that break a rule ({exLocs.size}). The proposal fixes all of them.</p>}
          {found && <p className="mt-2 text-[13px] text-muted">{found.id}: legacy {found.base_loc} → proposed {found.opt_loc}. Both are ringed.</p>}
        </div>
      </Card>
      <Detail loc={selLoc} skus={skus} plan={plan} data={data} />
    </div>
  );
}

function WarehouseSummary({ data }: { data: Wh }) {
  const dist = new Map(data.locations.map((l) => [l[0], l[10]]));
  const blockedLocs = data.locations.filter((l) => l[7] === "BLOCKED").length;
  const used = (i: 8 | 9) => data.locations.filter((l) => l[i].length > 0).length;
  const avg = (cls: string, key: "base_loc" | "opt_loc") => {
    const xs = data.skus.filter((s) => s.cls === cls && s[key]).map((s) => dist.get(s[key] as string) ?? 0);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
  };
  const moves = data.skus.filter((s) => s.move && s.move !== "STAY").length;
  const zones = data.zones.map((z) => ({ t: z.zone_type, n: z.location_count }));
  const k = data.kpi?.holdout;
  return (
    <Card title={`${data.id} at a glance`} subtitle="Select any slot on the plan for its details">
      <dl className="divide-y divide-[var(--rule)] text-[13px]">
        {[
          ["Locations", `${data.locations.length.toLocaleString()}`],
          ["Blocked by rack damage", blockedLocs ? `${blockedLocs}` : "0"],
          ["Occupied, legacy → proposal", `${used(8)} → ${used(9)}`],
          ["A-class distance from dock", `${avg("A", "base_loc").toFixed(1)} → ${avg("A", "opt_loc").toFixed(1)} m`],
          ["B-class distance from dock", `${avg("B", "base_loc").toFixed(1)} → ${avg("B", "opt_loc").toFixed(1)} m`],
          ["SKUs moved", `${moves} of ${data.skus.length}`],
          ["Pick travel, unseen weeks", k ? `${k.avg_distance_baseline_m.toFixed(1)} → ${k.avg_distance_optimized_m.toFixed(1)} m/order` : "–"],
          ["Open exceptions", `${data.exceptions.length}`],
        ].map(([a, b]) => (
          <div key={a} className="flex items-center justify-between gap-3 py-2.5"><dt className="text-muted">{a}</dt><dd className="tnum text-right text-fg">{b}</dd></div>
        ))}
      </dl>
      <h3 className="mt-5 text-[13px] font-medium text-subtle">Zones, from the dock outward</h3>
      <div className="mt-2 flex h-2 overflow-hidden rounded-[2px]">
        {zones.map((z) => <span key={z.t} style={{ width: `${(100 * z.n) / data.locations.length}%`, background: ZONE_COLOR[{ AMBIENT: "AMB", BULK: "BLK", CHILLED: "CHL", FROZEN: "FRZ", HAZMAT: "HAZ" }[z.t] ?? "AMB"] }} />)}
      </div>
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
        {zones.map((z) => (
          <li key={z.t} className="flex justify-between"><span className="text-muted">{z.t.charAt(0) + z.t.slice(1).toLowerCase()}</span><span className="tnum">{z.n}</span></li>
        ))}
      </ul>
    </Card>
  );
}

function Detail({ loc, skus, plan, data }: { loc?: LocRow; skus: Map<string, Sku>; plan: "base" | "opt"; data: Wh }) {
  if (!loc) return <WarehouseSummary data={data} />;
  const [id, zone, aisle, bay, level, side, type, status, base, opt, dist, w, d, h, kg] = loc;
  const occ = plan === "base" ? base : opt;
  return (
    <Card title={<span className="font-mono text-sm">{id}</span>} subtitle={`${ZONE_NAME[zone]} · aisle ${aisle}, bay ${bay}, side ${side}, level ${level}`}>
      <dl className="grid grid-cols-2 gap-2 text-[13px]">
        <div><dt className="text-subtle">Rack</dt><dd className="text-fg">{type.replace("_", " ").toLowerCase()}</dd></div>
        <div><dt className="text-subtle">Size</dt><dd className="tnum text-fg">{w}×{d}×{h} cm, {kg} kg</dd></div>
        <div><dt className="text-subtle">From dock</dt><dd className="tnum text-fg">{dist} m</dd></div>
        <div><dt className="text-subtle">Status</dt><dd>{status === "BLOCKED" ? <Badge tone="bad">Blocked</Badge> : <Badge tone="good">Active</Badge>}</dd></div>
      </dl>
      <div className="mt-4 space-y-3">
        <SlotLine label="Legacy" ids={base} skus={skus} />
        <SlotLine label="Proposed" ids={opt} skus={skus} />
      </div>
      {occ.map((sid) => {
        const s = skus.get(sid);
        if (!s) return null;
        return (
          <div key={sid} className="mt-4 rounded-lg bg-surface-2 p-3 text-[13px]">
            <div className="font-medium text-fg">{s.name}</div>
            <div className="mt-1 flex flex-wrap gap-1">
              <Badge tone="accent">{s.cls}-class</Badge>
              <Badge>{s.temp.toLowerCase()}</Badge>
              {s.haz !== "NONE" && <Badge tone="bad">{s.haz.toLowerCase()}</Badge>}
              {s.over && <Badge tone="warn">oversized</Badge>}
              {s.move && <Badge tone={s.move === "STAY" ? "neutral" : "info"}>{MOVE_LABEL[s.move]}</Badge>}
            </div>
            <p className="tnum mt-2 text-muted">{fmt.n(s.ppd, 2)} picks/day · {fmt.n(s.upd, 1)} units/day · case of {s.case} · {s.dims.map((x) => x.toFixed(0)).join("×")} cm</p>
            {s.reason && <p className="mt-2 leading-relaxed text-fg">{s.reason}</p>}
            {s.saving_s != null && s.move !== "STAY" && (
              <p className="tnum mt-1 text-good">Saves about {fmt.n(s.saving_s / 60, 1)} labour minutes a day versus the legacy slot.</p>
            )}
          </div>
        );
      })}
    </Card>
  );
}

function SlotLine({ label, ids, skus }: { label: string; ids: string[]; skus: Map<string, Sku> }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[13px]">
      <span className="text-subtle">{label}</span>
      <span className="text-right">
        {ids.length === 0 && <span className="text-subtle">empty</span>}
        {ids.map((i) => <span key={i} className="block font-mono text-fg">{i} <span className="font-sans text-subtle">({skus.get(i)?.cls})</span></span>)}
        {ids.length > 1 && <Badge tone="bad">Duplicate active slot</Badge>}
      </span>
    </div>
  );
}
