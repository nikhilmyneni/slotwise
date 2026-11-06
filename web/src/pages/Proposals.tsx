import { useMemo, useState } from "react";
import type { Ctx } from "../main";
import { fmt, MOVE_LABEL, Sku } from "../data";
import { Badge, btnSecondary, Card, Col, cx, ErrorBox, Loading, PageHeader, Search, Select, Table } from "../ui";
import { useWarehouse } from "./MapPage";

const SHORT: Record<string, string> = { STAY: "Stays", LABOUR_SAVING: "Labour saving", FORCED_CURRENT_INFEASIBLE: "Mandatory", FORCED_CURRENT_TAKEN: "Displaced" };

export default function Proposals({ summary, base, wh, setWh, go }: Ctx) {
  const [reason, setReason] = useState("MOVES");
  const [cls, setCls] = useState("ALL");
  const [q, setQ] = useState("");
  const [budget, setBudget] = useState<number | null>(null);
  const [pick, setPick] = useState<Sku | null>(null);
  const { data, error } = useWarehouse(base, wh);

  const moves = useMemo(() => (data ? data.skus.filter((s) => s.move && s.move !== "STAY")
    .sort((a, b) => (b.saving_s ?? 0) - (a.saving_s ?? 0)) : []), [data]);
  const forced = moves.filter((s) => s.move?.startsWith("FORCED_CURRENT_INFEASIBLE")).length;
  const n = budget ?? moves.length;
  const inBudget = new Set(moves.slice(0, n).map((s) => s.id));
  const savedMin = moves.slice(0, n).reduce((t, s) => t + Math.max(0, s.saving_s ?? 0), 0) / 60;
  const totalMin = moves.reduce((t, s) => t + Math.max(0, s.saving_s ?? 0), 0) / 60;

  const rows = [...(data?.skus ?? [])].sort((a, b) => (b.saving_s ?? 0) - (a.saving_s ?? 0)).filter((s) =>
    (reason === "ALL" || (reason === "MOVES" ? s.move !== "STAY" : s.move === reason)) &&
    (cls === "ALL" || s.cls === cls) &&
    (!q || `${s.id} ${s.name} ${s.base_loc} ${s.opt_loc}`.toUpperCase().includes(q.toUpperCase())));

  const cols: Col<Sku>[] = [
    { key: "id", label: "SKU", render: (s) => <span className="font-mono text-[13px]">{s.id}</span> },
    { key: "cls", label: "Class", render: (s) => <Badge tone={s.cls === "A" ? "accent" : "neutral"}>{s.cls}</Badge> },
    { key: "ppd", label: "Picks/day", className: "text-right tnum", render: (s) => fmt.n(s.ppd, 2) },
    { key: "from", label: "Legacy slot", render: (s) => <span className="font-mono text-[13px] text-muted">{s.base_loc.slice(10)}</span>, sort: (s) => s.base_loc },
    { key: "to", label: "Proposed slot", render: (s) => <span className="font-mono text-[13px]">{s.opt_loc?.slice(10)}</span>, sort: (s) => s.opt_loc ?? "" },
    { key: "move", label: "Decision", render: (s) => <Badge tone={s.move === "STAY" ? "neutral" : s.move?.startsWith("FORCED") ? "warn" : "accent"}>{SHORT[s.move ?? ""] ?? "–"}</Badge> },
    { key: "saving_s", label: "Saves / day", className: "text-right tnum", render: (s) => (s.move === "STAY" ? "–" : `${fmt.n(Math.max(0, (s.saving_s ?? 0) / 60), 1)} min`), sort: (s) => s.saving_s ?? 0 },
    { key: "wave", label: "In budget", render: (s) => (s.move === "STAY" ? "" : inBudget.has(s.id) ? <Badge tone="good">Yes</Badge> : <Badge>Later</Badge>), sort: (s) => (inBudget.has(s.id) ? 1 : 0) },
  ];

  return (
    <div>
      <PageHeader title="Slot proposals"
        lead="Every SKU gets a recommended slot with the reason behind it. Moves that fix a rule violation are mandatory; the rest are ranked by the labour they save, so the planner can execute the best ones first within a move budget."
        who="slotting planner, operations manager" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select label="Warehouse" value={wh} onChange={(v) => { setWh(v); setBudget(null); setPick(null); }}
          options={summary.warehouses.map((w) => ({ value: w.id, label: `${w.id} · ${w.name}` }))} />
        <Select label="Show" value={reason} onChange={setReason} options={[
          { value: "MOVES", label: "Moves only" }, { value: "ALL", label: "All SKUs" },
          ...Object.entries(MOVE_LABEL).map(([k, v]) => ({ value: k, label: v }))]} />
        <Select label="Class" value={cls} onChange={setCls} options={["ALL", "A", "B", "C"].map((c) => ({ value: c, label: c === "ALL" ? "All" : `${c}-class` }))} />
        <Search value={q} onChange={setQ} placeholder="Search SKU or location" />
      </div>
      {error && <ErrorBox error={error} />}
      {!data && !error && <Loading what="proposals" />}
      {data && (
        <div className={cx("grid grid-cols-1 items-start gap-4 xl:grid-cols-[1fr_340px]", data.id !== wh && "is-stale")}>
          <Card title={`${rows.length.toLocaleString()} SKUs`} subtitle="Click a row for the full explanation">
            <Table rows={rows} cols={cols} rowKey={(s) => s.id} onRow={setPick} selected={pick?.id ?? null} pageSize={14} empty="No SKUs match these filters." />
          </Card>
          <div className="space-y-4 xl:sticky xl:top-28">
            <Card title="Move budget" subtitle="How many moves can the team do this week?">
              <input type="range" min={0} max={moves.length} value={n} onChange={(e) => setBudget(Math.max(forced, Number(e.target.value)))}
                className="w-full accent-[var(--accent)]" aria-label="Number of moves to execute" />
              <div className="tnum mt-2 flex justify-between text-[13px] text-muted"><span>{forced} mandatory</span><span>{moves.length} total</span></div>
              <div className="tnum mt-3 text-2xl font-semibold text-fg">{n} moves</div>
              <p className="tnum mt-1 text-sm text-muted">
                Saves about <b className="text-good">{fmt.n(savedMin / 60, 1)} labour hours a day</b>, {fmt.pct((100 * savedMin) / (totalMin || 1), 0)} of the full proposal.
              </p>
              <p className="mt-2 text-xs text-subtle">The budget cannot go below the {forced} moves that fix rule violations. Savings are modelled per SKU, so chained moves are approximate.</p>
            </Card>
            <Card title="Why this slot?">
              {!pick && <p className="text-sm text-muted">Select a SKU in the table.</p>}
              {pick && (
                <div className="text-[13px]">
                  <div className="font-mono text-sm text-fg">{pick.id}</div>
                  <div className="text-muted">{pick.name}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge tone="accent">{pick.cls}-class overall</Badge>
                    {pick.train_cls && <Badge>{pick.train_cls}-class in training weeks</Badge>}
                    {pick.peak_cls !== pick.cls && <Badge tone="warn">{pick.peak_cls}-class at peak</Badge>}
                    {pick.haz !== "NONE" && <Badge tone="bad">{pick.haz.toLowerCase()}</Badge>}
                    {pick.over && <Badge tone="warn">oversized</Badge>}
                  </div>
                  <p className="mt-3 leading-relaxed text-fg">{pick.reason}</p>
                  <dl className="tnum mt-3 grid grid-cols-2 gap-2">
                    <div><dt className="text-subtle">Legacy cost</dt><dd>{pick.cost_cur_s != null ? `${fmt.n(pick.cost_cur_s / 60, 1)} min/day` : "–"}</dd></div>
                    <div><dt className="text-subtle">Proposed cost</dt><dd>{pick.cost_s != null ? `${fmt.n(pick.cost_s / 60, 1)} min/day` : "–"}</dd></div>
                    <div><dt className="text-subtle">Feasible slots</dt><dd>{fmt.n(pick.ncand)}</dd></div>
                    <div><dt className="text-subtle">Capacity</dt><dd>{pick.base_cap} → {pick.opt_cap} units</dd></div>
                  </dl>
                  {pick.move === "FORCED_CURRENT_INFEASIBLE" && <p className="mt-3 rounded-md bg-warn-soft p-2 text-warn">The legacy slot breaks a physical or compatibility rule, so this move is mandatory.</p>}
                  {pick.base_dup && <p className="mt-3 rounded-md bg-warn-soft p-2 text-warn">The legacy location is also held by another active SKU (duplicate).</p>}
                  <button className={cx(btnSecondary, "mt-4 w-full")} onClick={() => go("map", { sku: pick.id })}>Show both slots on the floor plan</button>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
