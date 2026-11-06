import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { load, Summary, useData } from "./data";
import { cx, ErrorBox, Loading } from "./ui";
import Overview from "./pages/Overview";
import MapPage from "./pages/MapPage";
import Proposals from "./pages/Proposals";
import Paths from "./pages/Paths";
import Labour from "./pages/Labour";
import Exceptions from "./pages/Exceptions";
import Quality from "./pages/Quality";
import Evaluation from "./pages/Evaluation";
import Method from "./pages/Method";

export type Ctx = {
  scale: string; summary: Summary; base: string;
  go: (route: string, params?: Record<string, string>) => void;
  /** Warehouse shared by every page, kept in the URL (?wh=WH-003). */
  wh: string; setWh: (id: string) => void; prefetchWh: (id: string) => void;
};

const ROUTES: { id: string; label: string; el: (c: Ctx) => JSX.Element }[] = [
  { id: "overview", label: "Overview", el: (c) => <Overview {...c} /> },
  { id: "map", label: "Floor plan", el: (c) => <MapPage {...c} /> },
  { id: "proposals", label: "Proposals", el: (c) => <Proposals {...c} /> },
  { id: "paths", label: "Pick paths", el: (c) => <Paths {...c} /> },
  { id: "labour", label: "Replenishment", el: (c) => <Labour {...c} /> },
  { id: "exceptions", label: "Exceptions", el: (c) => <Exceptions {...c} /> },
  { id: "quality", label: "Data", el: (c) => <Quality {...c} /> },
  { id: "evaluation", label: "Evaluation", el: (c) => <Evaluation {...c} /> },
  { id: "method", label: "Method", el: (c) => <Method {...c} /> },
];

function readHash() {
  const h = window.location.hash.replace(/^#\/?/, "");
  const [route, q] = h.split("?");
  const params = new URLSearchParams(q || "");
  return { route: ROUTES.some((r) => r.id === route) ? route : "overview", wh: params.get("wh") };
}

function getStored(key: string, fallback: string) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}
function setStored(key: string, v: string | null) {
  try { if (v === null) localStorage.removeItem(key); else localStorage.setItem(key, v); } catch { /* storage unavailable */ }
}
const idle = (fn: () => void) => ("requestIdleCallback" in window ? (window as unknown as { requestIdleCallback: (f: () => void) => void }).requestIdleCallback(fn) : setTimeout(fn, 400));

export function Mark({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="7" fill="var(--mark-tile)" />
      <rect x="7" y="8" width="18" height="4" rx="1" fill="#fff" />
      <rect x="7" y="14" width="12" height="4" rx="1" fill="#4f86e0" />
      <rect x="7" y="20" width="7" height="4" rx="1" fill="#fff" opacity="0.55" />
    </svg>
  );
}

/* ---------- theme: system by default, light or dark on request ---------- */
type Mode = "system" | "light" | "dark";
function useTheme(): [Mode, (m: Mode) => void] {
  const [mode, setMode] = useState<Mode>(() => (getStored("theme", "system") as Mode));
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = mode === "dark" || (mode === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#121519" : "#ffffff");
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [mode]);
  return [mode, (m) => { setMode(m); setStored("theme", m === "system" ? null : m); }];
}

const ICON: Record<Mode, JSX.Element> = {
  light: <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M3 13l1.4-1.4M11.6 4.4L13 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  dark: <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden><path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>,
  system: <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden><rect x="1.75" y="2.75" width="12.5" height="8.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M5.5 14h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
};

function ThemeToggle({ mode, setMode }: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <div role="radiogroup" aria-label="Colour theme" className="flex shrink-0 rounded-md bg-seg p-0.5">
      {(["system", "light", "dark"] as Mode[]).map((m) => (
        <button key={m} role="radio" aria-checked={mode === m} aria-label={`${m[0].toUpperCase()}${m.slice(1)} theme`} title={`${m[0].toUpperCase()}${m.slice(1)} theme`}
          onClick={() => setMode(m)}
          className={cx("grid h-8 w-8 place-items-center rounded-[5px]", mode === m ? "bg-surface text-fg ring-1 ring-line" : "text-muted hover:text-fg")}>
          {ICON[m]}
        </button>
      ))}
    </div>
  );
}

function App() {
  const [loc, setLoc] = useState(readHash());
  const [scale, setScale] = useState(getStored("scale", "full"));
  const [mode, setMode] = useTheme();
  const base = `/data/${scale}`;
  const { data: summary, error } = useData<Summary>(`${base}/summary.json`);
  const route = loc.route;

  useEffect(() => {
    const f = () => {
      const next = readHash();
      setLoc((prev) => { if (prev.route !== next.route) window.scrollTo(0, 0); return next; });
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);

  const whIds = summary?.warehouses.map((w) => w.id) ?? [];
  const wh = loc.wh && whIds.includes(loc.wh) ? loc.wh : whIds[0] ?? "WH-001";

  const hashFor = (r: string, params: Record<string, string> = {}) => {
    const q = new URLSearchParams({ wh, ...params });
    return `#/${r}?${q.toString()}`;
  };
  const go = (r: string, params?: Record<string, string>) => { window.location.hash = hashFor(r, params).slice(1); };
  const setWh = (id: string) => {
    const h = `#/${route}?${new URLSearchParams({ wh: id }).toString()}`;
    history.replaceState(null, "", h);
    setLoc({ route, wh: id });
  };
  const prefetchWh = useCallback((id: string) => { load(`${base}/wh/${id}.json`).catch(() => undefined); }, [base]);

  // Warm the cache while the user reads: current warehouse first, then its neighbours and the shared lists.
  useEffect(() => {
    if (!summary) return;
    const i = whIds.indexOf(wh);
    idle(() => {
      prefetchWh(wh);
      [whIds[i + 1], whIds[i - 1]].filter(Boolean).forEach((x) => prefetchWh(x as string));
      load(`${base}/exceptions.json`).catch(() => undefined);
    });
  }, [summary, wh, base]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = ROUTES.find((r) => r.id === route)!;
  const rc = summary?.row_counts;

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-30 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-20 border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-[1248px] items-center justify-between gap-3 px-4 sm:px-6">
          <a href={hashFor("overview")} className="flex min-w-0 items-center gap-2.5">
            <Mark />
            <span className="text-[16px] font-semibold tracking-tight">SlotWise</span>
            <span className="hidden text-subtle md:inline">/</span>
            <span className="hidden truncate text-[14px] text-muted md:inline">
              {rc ? `${rc.warehouses} warehouses · ${rc.skus.toLocaleString()} SKUs` : "Slotting network"}
            </span>
          </a>
          <div className="flex shrink-0 items-center gap-2">
            <div role="radiogroup" aria-label="Dataset scale" className="flex rounded-md bg-seg p-0.5 text-[13px]">
              {[{ v: "full", l: "Full", long: "Full dataset" }, { v: "starter", l: "Starter", long: "Starter" }].map((o) => (
                <button key={o.v} role="radio" aria-checked={scale === o.v}
                  onClick={() => { setScale(o.v); setStored("scale", o.v); history.replaceState(null, "", `#/${route}`); setLoc({ route, wh: null }); }}
                  className={cx("min-h-8 rounded-[5px] px-2.5 font-medium", scale === o.v ? "bg-surface text-fg ring-1 ring-line" : "text-muted hover:text-fg")}>
                  <span className="sm:hidden">{o.l}</span><span className="hidden sm:inline">{o.long}</span>
                </button>
              ))}
            </div>
            <ThemeToggle mode={mode} setMode={setMode} />
          </div>
        </div>
        <div className="mx-auto max-w-[1248px] px-4 pb-3 sm:hidden">
          <label className="flex items-center gap-2 text-[13px] text-muted">
            <span>Page</span>
            <select value={route} onChange={(e) => go(e.target.value)} className="min-h-11 flex-1 rounded-md border border-line-strong bg-surface px-2.5 text-base text-fg">
              {ROUTES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </label>
        </div>
        <nav aria-label="Main" className="no-scrollbar mx-auto hidden max-w-[1248px] gap-5 overflow-x-auto px-4 sm:flex sm:px-6">
          {ROUTES.map((r) => (
            <a key={r.id} href={hashFor(r.id)} aria-current={r.id === route ? "page" : undefined}
              className={cx("relative whitespace-nowrap pb-3 pt-1 text-[14px]",
                r.id === route ? "font-medium text-fg after:absolute after:inset-x-[-4px] after:bottom-0 after:h-0.5 after:rounded-full after:bg-ink"
                  : "text-muted hover:text-fg")}>
              {r.label}
            </a>
          ))}
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-[1248px] px-4 pb-16 pt-6 sm:px-6 sm:pt-8">
        {error && <ErrorBox error={error} />}
        {!error && !summary && <Loading what="dataset" />}
        {summary && <div className={cx(summary.scale !== scale && "is-stale")}>{current.el({ scale: summary.scale, summary, go, base: `/data/${summary.scale}`, wh, setWh, prefetchWh })}</div>}
      </main>
      {summary && (
        <footer className="border-t border-line bg-surface">
          <div className="mx-auto flex max-w-[1248px] flex-wrap items-center justify-between gap-2 px-4 py-5 text-[13px] text-muted sm:px-6">
            <span className="flex items-center gap-2"><Mark className="h-4 w-4" /> SlotWise · synthetic dataset, seed {summary.manifest.seed}, generator v{summary.manifest.generator_version}</span>
            <span className="tnum">{rc!.warehouses} warehouses · {rc!.locations.toLocaleString()} locations · {rc!.skus.toLocaleString()} SKUs · {rc!.order_lines.toLocaleString()} order lines</span>
          </div>
        </footer>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
