import { ReactNode, useMemo, useState } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export const btnPrimary = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md bg-ink px-3.5 text-[14px] font-medium text-on-ink hover:bg-[var(--ink-hover)] active:translate-y-px";
export const btnSecondary = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md bg-[var(--seg)] px-3.5 text-[14px] font-medium text-fg hover:bg-[var(--seg-hover)] active:translate-y-px";

export function Card({ children, className, title, action, subtitle }: {
  children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; subtitle?: ReactNode;
}) {
  return (
    <section className={cx("min-w-0 rounded-lg border border-line bg-surface", className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold leading-snug text-fg">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[13px] leading-snug text-subtle">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="px-5 pb-5 pt-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, lead, who, right }: { title: string; lead: ReactNode; who?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-[780px]">
        <h1 className="text-[24px] font-semibold leading-tight tracking-[-0.01em] text-fg">{title}</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-muted">{lead}</p>
        {who && <p className="mt-1.5 text-[13px] text-subtle">For the {who}.</p>}
      </div>
      {right}
    </div>
  );
}

type Tone = "good" | "bad" | "warn" | "info" | "neutral" | "accent";
const TONE: Record<Tone, string> = {
  good: "bg-good-soft text-[var(--good-ink)]",
  bad: "bg-bad-soft text-[var(--bad-ink)]",
  warn: "bg-warn-soft text-warn",
  info: "bg-info-soft text-info",
  neutral: "bg-[var(--neutral-soft)] text-[var(--neutral-ink)]",
  accent: "bg-info-soft text-info",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-[5px] px-1.5 py-0.5 text-[12px] font-medium leading-4", TONE[tone], className)}>{children}</span>;
}

export function severityTone(s: string): Tone {
  return s === "CRITICAL" ? "bad" : s === "HIGH" ? "warn" : s === "MEDIUM" ? "info" : "neutral";
}

/** A change signal: small arrow in green/red, the only hue a KPI carries. */
export function Delta({ good, children }: { good: boolean; children: ReactNode }) {
  return (
    <span className={cx("tnum inline-flex items-center gap-1 text-[13px] font-medium", good ? "text-good" : "text-bad")}>
      <svg viewBox="0 0 8 8" className="h-2 w-2" aria-hidden><path d={good ? "M0 2h8L4 7z" : "M0 6h8L4 1z"} fill="currentColor" /></svg>
      {children}
    </span>
  );
}

export function Kpi({ label, value, unit, before, after, good, hint }: {
  label: string; value: ReactNode; unit?: string; before?: ReactNode; after?: ReactNode; good?: boolean; hint?: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-line bg-surface px-5 py-4" title={hint}>
      <div className="text-[13px] font-medium text-subtle">{label}</div>
      <div className="tnum mt-2 text-[30px] font-medium leading-none tracking-[-0.02em] text-fg">
        {value}
        {unit && <span className="ml-1 text-[15px] font-normal text-subtle">{unit}</span>}
      </div>
      {(before !== undefined || after !== undefined) && (
        <div className="tnum mt-3 flex flex-wrap items-center gap-x-1.5 text-[13px] text-subtle">
          <span>{before}</span>
          <span aria-hidden className={cx("font-semibold", good === undefined ? "" : good ? "text-good" : "text-bad")}>→</span>
          <span className="sr-only">{good === undefined ? "to" : good ? "improved to" : "worsened to"}</span>
          <span className="text-fg">{after}</span>
        </div>
      )}
      {hint && <div className="mt-2 text-xs leading-snug text-subtle">{hint}</div>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-md bg-[var(--seg)] p-0.5">
      {options.map((o) => (
        <button key={o.value} role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cx("min-h-8 whitespace-nowrap rounded-[5px] px-3 text-[13px] font-medium",
            value === o.value ? "bg-surface text-fg" : "text-muted hover:text-fg")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, label }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; label: string;
}) {
  return (
    <label className="inline-flex max-w-full items-center gap-2 text-[13px] text-subtle">
      <span className="whitespace-nowrap">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="min-h-9 min-w-0 rounded-md border border-line-strong bg-surface px-2.5 text-base text-fg sm:text-[14px]">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Search({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder}
      className="min-h-9 w-full rounded-md border border-line-strong bg-surface px-3 text-base text-fg placeholder:text-subtle sm:w-64 sm:text-[14px]" />
  );
}

export type Col<T> = { key: string; label: string; render?: (r: T) => ReactNode; className?: string; sort?: (r: T) => number | string };

export function Table<T>({ rows, cols, pageSize = 15, onRow, rowKey, empty = "Nothing to show.", selected }: {
  rows: T[]; cols: Col<T>[]; pageSize?: number; onRow?: (r: T) => void; rowKey: (r: T) => string; empty?: string; selected?: string | null;
}) {
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const c = cols.find((x) => x.key === sort.key);
    const get = c?.sort ?? ((r: T) => (r as Record<string, unknown>)[sort.key] as number | string);
    return [...rows].sort((a, b) => (get(a) > get(b) ? sort.dir : get(a) < get(b) ? -sort.dir : 0));
  }, [rows, sort, cols]);
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const p = Math.min(page, pages - 1);
  const slice = sorted.slice(p * pageSize, (p + 1) * pageSize);
  return (
    <div>
      <div className="-mx-5 overflow-x-auto px-5">
        <table className="w-full min-w-[720px] text-left text-[14px]">
          <thead className="text-[13px] text-subtle">
            <tr className="border-b border-line">
              {cols.map((c) => (
                <th key={c.key} className={cx("px-3 pb-2 font-medium first:pl-0 last:pr-0", c.className)}>
                  <button className="inline-flex items-center gap-1 hover:text-fg" onClick={() =>
                    setSort((s) => (s?.key === c.key ? { key: c.key, dir: (s.dir * -1) as 1 | -1 } : { key: c.key, dir: -1 }))}>
                    {c.label}
                    {sort?.key === c.key && <span aria-hidden className="text-[10px]">{sort.dir === 1 ? "▲" : "▼"}</span>}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.length === 0 && <tr><td colSpan={cols.length} className="py-10 text-center text-subtle">{empty}</td></tr>}
            {slice.map((r) => {
              const k = rowKey(r);
              return (
                <tr key={k} onClick={onRow ? () => onRow(r) : undefined}
                  onKeyDown={onRow ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(r); } } : undefined}
                  tabIndex={onRow ? 0 : undefined} aria-label={onRow ? `Open details for ${k}` : undefined}
                  aria-selected={selected != null ? selected === k : undefined}
                  className={cx("border-b border-[var(--rule)] last:border-b-0", onRow && "cursor-pointer hover:bg-surface-2 focus-visible:bg-surface-2",
                    selected === k && "bg-[var(--sel)] hover:bg-[var(--sel)]")}>
                  {cols.map((c) => (
                    <td key={c.key} className={cx("px-3 py-2.5 align-top text-fg first:pl-0 last:pr-0", c.className)}>
                      {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "–")}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="mt-3 flex items-center justify-between text-[13px] text-subtle">
          <span className="tnum">{sorted.length.toLocaleString()} rows</span>
          <div className="flex items-center gap-1">
            <button className="min-h-9 rounded-md px-2.5 hover:bg-surface-2 disabled:opacity-40" disabled={p === 0} onClick={() => setPage(p - 1)}>Previous</button>
            <span className="tnum px-1">{p + 1} of {pages}</span>
            <button className="min-h-9 rounded-md px-2.5 hover:bg-surface-2 disabled:opacity-40" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Legend({ items }: { items: { color: string; label: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-subtle">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-3.5 rounded-[2px]" style={{ background: i.dashed ? "transparent" : i.color, border: i.dashed ? `1.5px dashed ${i.color}` : undefined }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

/** Line chart: faint gridlines, direct hover readout, optional week bands. */
export function LineChart({ xs, series, bands = [], yLabel, height = 240, format = (v: number) => v.toFixed(0) }: {
  xs: number[]; series: { name: string; color: string; values: number[]; dashed?: boolean; width?: number }[];
  bands?: { from: number; to: number; label: string; color: string }[]; yLabel: string; height?: number; format?: (v: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 680, H = height, L = 46, R = 12, T = 22, B = 28;
  const all = series.flatMap((s) => s.values);
  const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
  const max = hi + span * 0.35, min = Math.max(0, lo - span * 0.6);
  const x = (i: number) => L + (i / Math.max(1, xs.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const ticks = [0, 0.5, 1].map((f) => min + f * (max - min));
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={yLabel}
        onPointerLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          const i = Math.round(((px - L) / (W - L - R)) * (xs.length - 1));
          setHover(i >= 0 && i < xs.length ? i : null);
        }}>
        {bands.map((b) => {
          const i0 = xs.indexOf(b.from), i1 = xs.indexOf(b.to);
          if (i0 < 0 || i1 < 0) return null;
          const step = (W - L - R) / Math.max(1, xs.length - 1);
          const x0 = Math.max(L, x(i0) - step / 2), x1 = Math.min(W - R, x(i1) + step / 2);
          return (
            <g key={b.label}>
              <rect x={x0} y={T} width={x1 - x0} height={H - T - B} fill={b.color} />
              <text x={x0 + 6} y={T + 13} fontSize="11" fill="var(--fg-subtle)">{b.label}</text>
            </g>
          );
        })}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
            <text x={L - 8} y={y(t) + 4} fontSize="11" textAnchor="end" fill="var(--fg-subtle)">{format(t)}</text>
          </g>
        ))}
        {xs.map((v, i) => (
          <text key={v} x={x(i)} y={H - 8} fontSize="11" textAnchor="middle" fill="var(--fg-subtle)">W{v}</text>
        ))}
        {series.map((s) => (
          <polyline key={s.name} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeLinejoin="round" strokeDasharray={s.dashed ? "5 4" : undefined}
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
        ))}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--border-strong)" />
            {series.map((s) => <circle key={s.name} cx={x(hover)} cy={y(s.values[hover])} r={3.5} fill={s.color} stroke="var(--surface)" strokeWidth={1.5} />)}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-md border border-line bg-surface px-3 py-2 text-[13px] shadow-[var(--tip-shadow)]">{/* taste-skill-ignore: hover tooltip is a real overlay */}
          <div className="font-medium text-fg">Week {xs[hover]}</div>
          {series.map((s) => (
            <div key={s.name} className="tnum flex items-center gap-2 text-subtle">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.name} <span className="ml-auto pl-3 text-fg">{format(s.values[hover])}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Paired horizontal bars: legacy (grey) vs optimized (data hue) per category. */
export function PairBars({ rows, unit, format = (v: number) => v.toFixed(1) }: {
  rows: { label: string; a: number; b: number; note?: string }[]; unit: string; format?: (v: number) => string;
}) {
  const max = Math.max(...rows.flatMap((r) => [r.a, r.b])) || 1;
  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[64px_1fr_auto] items-center gap-3">
          <div className="text-[13px] font-medium text-fg">{r.label}</div>
          <div className="space-y-1">
            <div className="h-2 rounded-[2px]" style={{ width: `${(r.a / max) * 100}%`, background: "var(--base-line)" }} title={`Legacy ${format(r.a)} ${unit}`} />
            <div className="h-2 rounded-[2px] bg-hue" style={{ width: `${(r.b / max) * 100}%` }} title={`Optimized ${format(r.b)} ${unit}`} />
          </div>
          <div className="tnum w-24 text-right text-[13px] text-fg">{r.note}</div>
        </div>
      ))}
    </div>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center gap-3 text-[14px] text-subtle" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-ink" aria-hidden />
      Loading {what}…
    </div>
  );
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-line bg-bad-soft p-4 text-[14px] text-[var(--bad-ink)]" role="alert">
      Could not load data: {error}. Run <code className="font-mono">python -m slotting all --scale full --web</code> to build it.
    </div>
  );
}

export function Callout({ tone = "info", title, children }: { tone?: Tone; title: string; children: ReactNode }) {
  return (
    <div className={cx("rounded-lg border p-4", tone === "warn" ? "border-[var(--warn-line)] bg-warn-soft" : tone === "good" ? "border-line bg-good-soft" : tone === "bad" ? "border-line bg-bad-soft" : "border-line bg-surface")}>
      <div className="text-[14px] font-semibold text-fg">{title}</div>
      <div className="mt-1 text-[14px] leading-relaxed text-muted">{children}</div>
    </div>
  );
}
