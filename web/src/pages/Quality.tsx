import { useState } from "react";
import type { Ctx } from "../main";
import { fmt, useData } from "../data";
import { Badge, Card, Callout, Loading, PageHeader, Search, Segmented, Select } from "../ui";

type Samples = Record<string, { columns: string[]; rows: Record<string, unknown>[]; total: number }>;

export default function Quality(c: Ctx) {
  const [tab, setTab] = useState<"checks" | "repro" | "dict" | "model" | "explore">("checks");
  const { summary, scale, base } = c;
  const v = summary.validation;
  return (
    <div>
      <PageHeader title="Data & validation"
        lead={<>The dataset is fully synthetic, generated with seed <b className="text-fg">{summary.manifest.seed}</b> by one parameterised generator for both scales.
          Parents are created before children, every derived value is recomputed from source rows, and labelled anomalies live in a separate ground-truth file.</>}
        who="logistics analyst, reviewers"
        right={<a href={`${base}/slotting-${scale}-dataset.zip`} download className="inline-flex min-h-10 items-center rounded-lg bg-ink px-4 text-sm font-semibold text-on-ink hover:opacity-85">Download dataset ZIP</a>} />
      <div className="mb-4 overflow-x-auto">
        <Segmented label="Section" value={tab} onChange={setTab} options={[
          { value: "checks", label: `Validation (${v.total})` }, { value: "repro", label: "Reproducibility" },
          { value: "dict", label: "Data dictionary" }, { value: "model", label: "Entities" }, { value: "explore", label: "Browse tables" }]} />
      </div>
      {tab === "checks" && <Checks {...c} />}
      {tab === "repro" && <Repro {...c} />}
      {tab === "dict" && <Dict {...c} />}
      {tab === "model" && <Model {...c} />}
      {tab === "explore" && <Explore {...c} />}
    </div>
  );
}

function Checks({ summary }: Ctx) {
  const v = summary.validation;
  const cats = [...new Set(v.checks.map((c) => c.category))];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card><div className="text-[13px] font-medium text-subtle">Integrity checks passed</div><div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">{v.passed} / {v.passed + v.failed}</div></Card>
        <Card><div className="text-[13px] font-medium text-subtle">Failed</div><div className={"tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg"}>{v.failed}</div></Card>
        <Card><div className="text-[13px] font-medium text-subtle">Business-rule findings (expected, labelled)</div><div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">{v.findings}</div></Card>
      </div>
      <div className="gap-4 lg:columns-2 [&>*]:mb-4 [&>*]:break-inside-avoid">
      {cats.map((cat) => (
        <Card key={cat} title={cat.replace("_", " ").replace(/^\w/, (x) => x.toUpperCase())}
          subtitle={`${v.checks.filter((c) => c.category === cat).length} checks`}>
          <ul className="divide-y divide-[var(--rule)]">
            {v.checks.filter((c) => c.category === cat).map((c) => (
              <li key={c.check} className="flex items-start justify-between gap-3 py-2 text-[13px]">
                <span className="min-w-0 break-words text-fg [overflow-wrap:anywhere]">{c.check}{c.detail && <span className="text-subtle"> · {c.detail}</span>}
                  {c.sample.length > 0 && <span className="block font-mono text-xs text-subtle">e.g. {c.sample.join(", ")}</span>}</span>
                <Badge className="shrink-0" tone={c.status === "PASS" ? "good" : c.status === "FINDING" ? "info" : "bad"}>
                  {c.status === "PASS" ? "pass" : c.status === "FINDING" ? "finding" : `${c.violations} fail`}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      ))}
      </div>
    </div>
  );
}

function Repro({ summary }: Ctx) {
  const r = summary.repro;
  return (
    <div className="space-y-4">
      <Callout tone={r?.all_identical ? "good" : "warn"} title={r?.all_identical ? "Regenerated twice: byte-identical" : "Reproducibility not yet verified"}>
        Command: <code className="font-mono text-fg">python -m slotting repro --scale {summary.scale}</code>. The generator and the engine run twice from seed {summary.manifest.seed};
        each output file's row count and SHA-256 must match.
      </Callout>
      <Card title="Manifest" subtitle={summary.manifest.command}>
        <dl className="grid grid-cols-1 gap-2 text-[13px] sm:grid-cols-2">
          <div><dt className="text-subtle">Generator version</dt><dd>{summary.manifest.generator_version}</dd></div>
          <div><dt className="text-subtle">Horizon</dt><dd>{summary.manifest.horizon.start}, {summary.manifest.horizon.weeks} weeks (peak {summary.manifest.horizon.peak_weeks.join("-")})</dd></div>
          <div><dt className="text-subtle">Environment</dt><dd>{Object.entries(summary.manifest.environment).map(([k, x]) => `${k} ${x}`).join(" · ")}</dd></div>
          <div><dt className="text-subtle">Provenance</dt><dd>{summary.manifest.provenance}</dd></div>
        </dl>
      </Card>
      {r && (
        <Card title={`${r.files.length} files compared`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-[13px]">
              <thead className="text-left text-subtle"><tr><th className="py-1.5 font-medium">File</th><th className="text-right font-medium">Rows</th><th className="font-medium">SHA-256 (run 1 = run 2)</th><th /></tr></thead>
              <tbody>
                {r.files.map((f) => (
                  <tr key={f.file} className="border-t border-line">
                    <td className="py-1.5 font-mono">{f.file}</td>
                    <td className="tnum text-right">{fmt.n(f.rows_run1)}</td>
                    <td className="font-mono text-xs text-subtle">{f.sha256_run1.slice(0, 20)}…</td>
                    <td>{f.identical ? <Badge tone="good">identical</Badge> : <Badge tone="bad">differs</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Dict({ summary }: Ctx) {
  const tables = Object.keys(summary.tables);
  const [t, setT] = useState(tables[0]);
  const rows = summary.dictionary.filter((d) => d.table === t);
  return (
    <Card title={t} subtitle={`${summary.tables[t].purpose}. ${summary.tables[t].cardinality}.`}
      action={<Select label="Table" value={t} onChange={setT} options={tables.map((x) => ({ value: x, label: `${x} (${fmt.n(summary.row_counts[x])})` }))} />}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-[13px]">
          <thead className="text-left text-subtle"><tr>{["Field", "Type", "Required", "Unique", "Units", "Allowed values", "Validation", "Description"].map((h) => <th key={h} className="py-1.5 pr-3 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.field} className="border-t border-line align-top">
                <td className="py-1.5 pr-3 font-mono text-fg">{d.field}</td><td className="pr-3">{d.type}</td>
                <td className="pr-3">{d.required ? "yes" : "no"}</td><td className="pr-3">{d.unique ? "yes" : ""}</td>
                <td className="pr-3">{d.units}</td><td className="pr-3 break-words text-muted">{d.allowed_values.split("|").join(", ")}</td>
                <td className="pr-3 text-muted">{d.validation}</td><td className="text-muted">{d.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Model({ summary }: Ctx) {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card title="Entities" subtitle="Primary key, purpose and cardinality">
        <ul className="divide-y divide-line text-[13px]">
          {Object.entries(summary.tables).map(([t, i]) => (
            <li key={t} className="py-2">
              <div className="flex items-center justify-between gap-2"><span className="font-mono font-medium text-fg">{t}</span><span className="tnum text-subtle">{fmt.n(summary.row_counts[t])} rows</span></div>
              <div className="text-muted">{i.purpose}</div>
              <div className="text-subtle">PK <span className="font-mono">{i.pk}</span> · {i.cardinality}</div>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Relationships" subtitle="Every foreign key is checked by validation">
        <ul className="space-y-1 text-[13px]">
          {summary.relationships.map((r) => (
            <li key={`${r.child}.${r.col}`} className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-fg">{r.child}.{r.col}</span><span className="text-subtle">→</span>
              <span className="font-mono text-fg">{r.parent}</span>{r.nullable && <Badge>optional</Badge>}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[13px] text-muted">SKU ↔ Location is many-to-many over time through <span className="font-mono">slot_assignments</span>, a bridge table with effective dates.
          State changes are new rows plus <span className="font-mono">slot_events</span>; nothing is overwritten.</p>
      </Card>
    </div>
  );
}

function Explore({ base }: Ctx) {
  const { data } = useData<Samples>(`${base}/samples.json`);
  const [t, setT] = useState("orders");
  const [q, setQ] = useState("");
  if (!data) return <Loading what="tables" />;
  const s = data[t];
  const rows = s.rows.filter((r) => !q || JSON.stringify(r).toUpperCase().includes(q.toUpperCase()));
  return (
    <Card title={`${t}: first ${s.rows.length} of ${fmt.n(s.total)} rows`} subtitle="The full tables are in the CSV download"
      action={<div className="flex flex-wrap gap-2"><Select label="Table" value={t} onChange={setT} options={Object.keys(data).map((k) => ({ value: k, label: k }))} /><Search value={q} onChange={setQ} placeholder="Filter rows" /></div>}>
      <div className="max-h-[560px] overflow-auto rounded-lg border border-line">
        <table className="text-[12px]">
          <thead className="sticky top-0 bg-surface-2 text-left text-subtle"><tr>{s.columns.map((col) => <th key={col} className="whitespace-nowrap px-2 py-1.5 font-medium">{col}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                {s.columns.map((col) => <td key={col} className="max-w-[260px] truncate whitespace-nowrap px-2 py-1 font-mono text-fg" title={String(r[col] ?? "")}>{r[col] == null ? <span className="text-subtle">null</span> : String(r[col])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
