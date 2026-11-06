import { useEffect, useState } from "react";

export type Kpi = {
  orders: number; lines: number; units: number;
  distance_baseline_km: number; distance_optimized_km: number; distance_saving_pct: number;
  avg_distance_baseline_m: number; avg_distance_optimized_m: number;
  avg_aisles_baseline: number; avg_aisles_optimized: number;
  pick_hours_baseline: number; pick_hours_optimized: number;
  lines_per_hour_baseline: number; lines_per_hour_optimized: number; throughput_gain_pct: number;
  repl_trips_baseline: number; repl_trips_optimized: number;
  repl_hours_baseline: number; repl_hours_optimized: number;
  overloaded_shifts_baseline: number; overloaded_shifts_optimized: number;
  total_labour_hours_baseline: number; total_labour_hours_optimized: number;
};

export type Check = { category: string; check: string; status: "PASS" | "FAIL" | "FINDING"; violations: number; detail: string; sample: string[] };

export type Summary = {
  scale: string;
  manifest: { dataset: string; seed: number; generator_version: string; command: string; scale: Record<string, number | string>;
    horizon: { start: string; weeks: number; peak_weeks: number[]; train_weeks: number }; provenance: string;
    environment: Record<string, string> };
  files: { file: string; rows: number; bytes: number; sha256: string }[];
  repro: null | { scale: string; seed: number; all_identical: boolean;
    files: { file: string; rows_run1: number; rows_run2: number; sha256_run1: string; sha256_run2: string; identical: boolean }[] };
  row_counts: Record<string, number>;
  metrics: {
    overall: Kpi; holdout: Kpi;
    per_warehouse: Record<string, { all: Kpi; holdout: Kpi }>;
    peak_vs_normal: { peak: Kpi; normal: Kpi };
    evaluation_window: { train_weeks: string; holdout_weeks: string; peak_weeks: number[] };
    move_curve: { moves: number; saving_hours_per_day: number }[];
    moves_by_reason: Record<string, number>;
    velocity_slotting: Record<"baseline" | "optimized", Record<"A" | "B" | "C", { skus: number; avg_dist_m: number; golden_zone_pct: number }>>;
    peak_class_shift_skus: number; constraint_violations_optimized: number; unslotted_skus_optimized: number;
    skus_moved: number; skus_total: number; exceptions_by_type: Record<string, number>;
  };
  evaluation: {
    by_issue: Record<string, { ground_truth: number; detected: number; tp: number; fp: number; fn: number;
      precision: number | null; recall: number | null; false_positive_ids: string[]; missed_ids: string[] }>;
    overall: { tp: number; fp: number; fn: number; precision: number; recall: number };
    negative_controls: { controls: number; false_alarms: number; specificity: number; by_subtype: Record<string, number> };
    ground_truth_subtypes: { issue_type: string; issue_subtype: string; n: number }[];
    note: string;
  };
  validation: { total: number; passed: number; failed: number; findings: number; checks: Check[] };
  warehouses: { id: string; name: string; city: string; region: string; locations: number; skus: number; blocked: boolean; exceptions: number;
    kpi: { all: Kpi; holdout: Kpi } }[];
  weekly: { week_no: number; orders: number; base: number; opt: number; rb: number; ro: number; ob: number; oo: number }[];
  exceptions_by_type: { issue_type: string; severity: string; n: number }[];
  dictionary: { table: string; field: string; type: string; required: boolean; unique: boolean; units: string;
    allowed_values: string; validation: string; description: string }[];
  tables: Record<string, { purpose: string; cardinality: string; pk: string }>;
  relationships: { child: string; col: string; parent: string; nullable: boolean }[];
  params: { walk_speed_mps: number; repl_minutes_per_trip: number; move_cost_minutes: number; move_payback_days: number;
    max_cases_per_slot: number; repl_min_fill: number; abc_cutoffs: number[]; incompatible_pairs: string[][];
    aisle_len_m: number; aisle_pitch_m: number; bays: number; levels: number };
};

export type Exc = { exception_id: string; issue_type: string; entity_type: string; entity_id: string; warehouse_id: string;
  related_ids: string; detail: string; severity: string; suggested_action: string; source: string };

export type Sku = { id: string; name: string; cat: string; temp: string; haz: string; over: boolean; cls: string; peak_cls: string;
  train_cls: string | null; ppd: number; upd: number; case: number; dims: number[]; kg: number;
  base_loc: string; base_slot: string; base_cap: number; base_dup: boolean;
  opt_loc: string | null; opt_slot: string | null; opt_cap: number | null; move: string | null;
  saving_s: number | null; cost_s: number | null; cost_cur_s: number | null; ncand: number | null; reason: string | null };

export type LocRow = [string, string, number, number, number, string, string, string, string[], string[], number, number, number, number, number];

export type Wh = {
  id: string;
  zones: { zone_id: string; zone_type: string; temp_class: string; aisle_from: number; aisle_to: number; location_count: number }[];
  blocks: { block_id: string; aisle: number; reason: string; blocked_from: string; blocked_to: string | null; status: string }[];
  locations: LocRow[]; skus: Sku[];
  orders: { id: string; week: number; lines: number; units: number; base_m: number; opt_m: number;
    base_route: number[][]; opt_route: number[][];
    picks: { pick: string; sku: string; qty: number; base_loc: string; opt_loc: string; via: string; leg: number }[] }[];
  repl: { date: string[]; shift: string[]; staffed: number[]; base: number[]; opt: number[] };
  exceptions: Exc[];
  kpi: { all: Kpi; holdout: Kpi };
};

const cache = new Map<string, Promise<unknown>>();

export function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export function useData<T>(path: string | null): { data: T | null; error: string | null } {
  const [state, set] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    if (!path) return;
    let live = true;
    set((s) => ({ data: s.data, error: null }));
    load<T>(path).then((d) => live && set({ data: d, error: null })).catch((e) => live && set({ data: null, error: String(e.message || e) }));
    return () => { live = false; };
  }, [path]);
  return state;
}

export const fmt = {
  n: (v: number | null | undefined, d = 0) => (v == null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v: number | null | undefined, d = 1) => (v == null ? "–" : `${v.toFixed(d)}%`),
  signed: (v: number, d = 1) => `${v > 0 ? "+" : ""}${v.toFixed(d)}`,
};

export const ISSUE_LABEL: Record<string, string> = {
  SKU_EXCEEDS_LOCATION_CAPACITY: "SKU exceeds location capacity",
  INCOMPATIBLE_PRODUCTS_CO_LOCATED: "Incompatible products co-located",
  DUPLICATE_ACTIVE_LOCATION: "Duplicate active location",
  PICK_PATH_USES_BLOCKED_AISLE: "Pick path uses blocked aisle",
  REPLENISHMENT_EXCEEDS_LABOR_CAPACITY: "Replenishment exceeds labour",
  NO_FEASIBLE_SLOT: "No feasible slot",
  OPTIMIZED_RULE_VIOLATION: "Optimizer rule violation",
  NONE: "Negative control",
};

export const MOVE_LABEL: Record<string, string> = {
  STAY: "Stays in place",
  LABOUR_SAVING: "Moves to save labour",
  FORCED_CURRENT_INFEASIBLE: "Must move: current slot breaks a rule",
  FORCED_CURRENT_TAKEN: "Moves: current slot given to a faster SKU",
};
