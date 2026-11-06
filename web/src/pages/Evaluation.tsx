import { useState } from "react";
import type { Ctx } from "../main";
import { fmt, ISSUE_LABEL, useData } from "../data";
import { Badge, Callout, Card, Col, Loading, PageHeader, Search, Select, Table } from "../ui";

type GtRow = { gt_id: string; issue_type: string; issue_subtype: string; entity_type: string; entity_id: string;
  related_ids: string; warehouse_id: string; rule: string; expected_decision: string; note: string };

export default function Evaluation({ summary, base }: Ctx) {
  const ev = summary.evaluation;
  const { data } = useData<GtRow[]>(`${base}/ground_truth.json`);
  const [type, setType] = useState("ALL");
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((r) => (type === "ALL" || r.issue_type === type) && (!q || `${r.entity_id} ${r.note}`.toUpperCase().includes(q.toUpperCase())));
  const cols: Col<GtRow>[] = [
    { key: "gt_id", label: "Label", render: (r) => <span className="font-mono text-[13px]">{r.gt_id}</span> },
    { key: "issue_type", label: "Type", render: (r) => r.issue_type === "NONE" ? <Badge tone="good">control</Badge> : ISSUE_LABEL[r.issue_type] },
    { key: "issue_subtype", label: "Subtype", render: (r) => <span className="text-[13px] text-muted">{r.issue_subtype.toLowerCase().replace(/_/g, " ")}</span> },
    { key: "entity_id", label: "Record", render: (r) => <span className="font-mono text-[13px]">{r.entity_id}</span> },
    { key: "expected_decision", label: "Expected decision", render: (r) => <span className="text-[13px]">{r.expected_decision.toLowerCase().replace(/_/g, " ")}</span> },
    { key: "note", label: "Note", render: (r) => <span className="text-[13px] text-muted">{r.note}</span> },
  ];
  return (
    <div>
      <PageHeader title="Evaluation against ground truth"
        lead="Anomalies were injected deliberately and recorded in a separate answer key that the engine never reads. This page compares what the exception detector found with that key, including negative controls: valid edge cases right at each rule's threshold that must not be flagged."
        who="reviewers, logistics analyst" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Card><div className="text-[13px] font-medium text-subtle">Labelled anomalies</div><div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">{fmt.n(ev.overall.tp + ev.overall.fn)}</div></Card>
        <Card><div className="text-[13px] font-medium text-subtle">Precision</div><div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">{fmt.n(ev.overall.precision * 100, 1)}%</div></Card>
        <Card><div className="text-[13px] font-medium text-subtle">Recall</div><div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">{fmt.n(ev.overall.recall * 100, 1)}%</div></Card>
        <Card><div className="text-[13px] font-medium text-subtle">False alarms on controls</div><div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">{ev.negative_controls.false_alarms} / {ev.negative_controls.controls}</div></Card>
      </div>
      <div className="mt-4 grid grid-cols-1 items-start gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Card title="By issue type">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-[13px]">
              <thead className="text-left text-subtle"><tr><th className="py-1.5 font-medium">Issue</th><th className="text-right font-medium">Labelled</th><th className="text-right font-medium">Detected</th><th className="text-right font-medium">TP</th><th className="text-right font-medium">FP</th><th className="text-right font-medium">FN</th><th className="text-right font-medium">Recall</th></tr></thead>
              <tbody>
                {Object.entries(ev.by_issue).map(([t, x]) => (
                  <tr key={t} className="border-t border-line">
                    <td className="py-1.5">{ISSUE_LABEL[t]}</td><td className="tnum text-right">{x.ground_truth}</td><td className="tnum text-right">{x.detected}</td>
                    <td className="tnum text-right text-good">{x.tp}</td><td className="tnum text-right">{x.fp}</td><td className="tnum text-right">{x.fn}</td>
                    <td className="tnum text-right">{x.recall == null ? "–" : `${(x.recall * 100).toFixed(0)}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4 className="mt-5 text-sm font-semibold">How the labels were made</h4>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {ev.ground_truth_subtypes.map((s) => (
              <li key={`${s.issue_type}${s.issue_subtype}`}><Badge tone={s.issue_type === "NONE" ? "good" : "neutral"}>{s.issue_subtype.toLowerCase().replace(/_/g, " ")}: {s.n}</Badge></li>
            ))}
          </ul>
        </Card>
        <div className="space-y-4">
          <Callout title="Read this score honestly">{ev.note}</Callout>
          <Callout tone="neutral" title="What the controls test">
            Exact-fit slots (capacity equals one case), compatible hazard classes sharing a bay, labour just under the staffed minutes, and picks through an aisle on the day of a temporary block but outside its time window.
            A detector with an off-by-one threshold or one that ignores block times would fail these.
          </Callout>
        </div>
      </div>
      <Card className="mt-4" title="Ground truth file" subtitle="Separate from the inputs: ground_truth/ground_truth.csv"
        action={<div className="flex flex-wrap gap-2"><Select label="Type" value={type} onChange={setType} options={[{ value: "ALL", label: "All" }, ...[...new Set((data ?? []).map((r) => r.issue_type))].map((t) => ({ value: t, label: ISSUE_LABEL[t] ?? t }))]} /><Search value={q} onChange={setQ} placeholder="Search record" /></div>}>
        {!data ? <Loading what="ground truth" /> : <Table rows={rows} cols={cols} rowKey={(r) => r.gt_id} pageSize={12} />}
      </Card>
    </div>
  );
}
