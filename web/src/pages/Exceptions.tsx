import { useState } from "react";
import type { Ctx } from "../main";
import { Exc, fmt, ISSUE_LABEL, useData } from "../data";
import { Badge, Card, Col, ErrorBox, Loading, PageHeader, Search, Select, severityTone, Table } from "../ui";

export default function Exceptions({ summary, base }: Ctx) {
  const { data, error } = useData<Exc[]>(`${base}/exceptions.json`);
  const [type, setType] = useState("ALL");
  const [wh, setWh] = useState("ALL");
  const [sev, setSev] = useState("ALL");
  const [q, setQ] = useState("");
  const [pick, setPick] = useState<Exc | null>(null);

  const counts = Object.entries(summary.metrics.exceptions_by_type);
  const rows = (data ?? []).filter((e) => (type === "ALL" || e.issue_type === type) && (wh === "ALL" || e.warehouse_id === wh)
    && (sev === "ALL" || e.severity === sev) && (!q || `${e.entity_id} ${e.related_ids} ${e.detail}`.toUpperCase().includes(q.toUpperCase())));

  const cols: Col<Exc>[] = [
    { key: "severity", label: "Severity", render: (e) => <Badge tone={severityTone(e.severity)}>{e.severity.toLowerCase()}</Badge> },
    { key: "issue_type", label: "Issue", render: (e) => ISSUE_LABEL[e.issue_type] ?? e.issue_type },
    { key: "warehouse_id", label: "Warehouse", render: (e) => <span className="font-mono text-[13px]">{e.warehouse_id}</span> },
    { key: "entity_id", label: "Record", render: (e) => <span className="font-mono text-[13px]">{e.entity_id}</span> },
    { key: "detail", label: "What happened", className: "max-w-[360px]", render: (e) => <span className="text-muted">{e.detail}</span> },
  ];

  return (
    <div>
      <PageHeader title="Exceptions"
        lead="Rule checks run on the recorded data and flag anything that breaks a physical, safety or labour rule, with a suggested action. This page uses only the operational data; the answer key is kept on the Evaluation page."
        who="operations manager, warehouse operator, logistics analyst" />
      <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5">
        {counts.map(([t, n]) => (
          <button key={t} onClick={() => setType(type === t ? "ALL" : t)}
            className={`rounded-lg border p-3 text-left transition-colors ${type === t ? "border-ink bg-surface ring-1 ring-ink" : "border-line bg-surface hover:border-line-strong"}`}>
            <div className="text-[13px] leading-snug text-muted">{ISSUE_LABEL[t] ?? t}</div>
            <div className="tnum mt-1 text-2xl font-semibold text-fg">{fmt.n(n)}</div>
          </button>
        ))}
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select label="Warehouse" value={wh} onChange={setWh} options={[{ value: "ALL", label: "All" }, ...summary.warehouses.map((w) => ({ value: w.id, label: w.id }))]} />
        <Select label="Severity" value={sev} onChange={setSev} options={["ALL", "CRITICAL", "HIGH", "MEDIUM"].map((s) => ({ value: s, label: s === "ALL" ? "All" : s.toLowerCase() }))} />
        <Search value={q} onChange={setQ} placeholder="Search record ID or text" />
      </div>
      {error && <ErrorBox error={error} />}
      {!data && !error && <Loading what="exceptions" />}
      {data && (
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[1fr_340px]">
          <Card title={`${rows.length.toLocaleString()} exceptions`}>
            <Table rows={rows} cols={cols} rowKey={(e) => e.exception_id} onRow={setPick} selected={pick?.exception_id ?? null} />
          </Card>
          <Card title="Action" className="xl:sticky xl:top-28">
            {!pick && <p className="text-sm text-muted">Select an exception to see the evidence and what to do.</p>}
            {pick && (
              <div className="space-y-3 text-[13px]">
                <div className="flex flex-wrap gap-1"><Badge tone={severityTone(pick.severity)}>{pick.severity.toLowerCase()}</Badge><Badge>{pick.source === "DATA_AUDIT" ? "data audit" : "optimizer"}</Badge></div>
                <div className="text-sm font-semibold text-fg">{ISSUE_LABEL[pick.issue_type]}</div>
                <dl className="space-y-1.5">
                  <div><dt className="text-subtle">Exception</dt><dd className="font-mono">{pick.exception_id}</dd></div>
                  <div><dt className="text-subtle">{pick.entity_type}</dt><dd className="font-mono">{pick.entity_id}</dd></div>
                  {pick.related_ids && <div><dt className="text-subtle">Related</dt><dd className="font-mono break-all">{pick.related_ids}</dd></div>}
                  <div><dt className="text-subtle">Evidence</dt><dd className="text-fg">{pick.detail}</dd></div>
                </dl>
                <div className="rounded-md bg-surface-2 p-3 text-fg"><span className="font-medium">Suggested action</span><span className="mt-0.5 block text-muted">{pick.suggested_action}</span></div>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
