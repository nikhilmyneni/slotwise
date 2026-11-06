"""CLI.

  python -m slotting all   --scale starter|full [--seed N] [--no-sql] [--web]
  python -m slotting repro --scale starter|full     # generate twice, compare checksums
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from . import config

ROOT = Path(__file__).resolve().parents[1]


def run_all(scale_name: str, out: Path, with_sql: bool, web: bool, repro: dict | None = None):
    from .engine.run import optimize
    from .evaluate import score
    from .export import export_all
    from .generate.pipeline import generate
    from .schema import dictionary_markdown
    from .validate import validate

    scale = config.SCALES[scale_name]
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)  # noqa: E731
    tables, gt = generate(scale, log=log)
    log("engine: optimize, simulate pick paths and replenishment, detect exceptions")
    results = optimize(tables)
    log("validate dataset and proposal")
    validation = validate(tables, gt, scale, results)
    log("score detector against ground truth")
    evaluation = score(results["exceptions"], gt)
    log(f"export to {out}")
    manifest = export_all(out, scale, tables, gt, results, validation, evaluation, dictionary_markdown(tables),
                          with_sql=with_sql)
    if repro is None and (out / "repro_report.json").exists():
        previous_repro = json.loads((out / "repro_report.json").read_text())
        if previous_repro.get("seed") == config.SEED and previous_repro.get("scale") == scale_name:
            repro = previous_repro
    if web:
        from .web_export import build
        log("web bundle")
        build(out, ROOT / "web" / "public" / "data", scale_name, tables, gt, results, validation, evaluation,
              manifest, repro)
    m = results["metrics"]
    log("done")
    print(json.dumps({
        "validation": {k: validation[k] for k in ("total", "passed", "failed", "findings")},
        "detection": evaluation["overall"], "negative_controls": {k: evaluation["negative_controls"][k]
                                                                  for k in ("controls", "false_alarms")},
        "holdout": {k: m["holdout"][k] for k in ("distance_saving_pct", "throughput_gain_pct",
                                                  "repl_hours_baseline", "repl_hours_optimized")},
        "moves": m["moves_by_reason"], "violations_optimized": m["constraint_violations_optimized"],
    }, indent=1))
    return manifest


def run_repro(scale_name: str) -> dict:
    from .export import write_csvs
    from .generate.pipeline import generate
    from .engine.run import optimize

    runs = []
    for i in range(2):
        tables, gt = generate(config.SCALES[scale_name], log=lambda m: None)
        res = optimize(tables)
        with tempfile.TemporaryDirectory() as d:
            files = write_csvs({**tables, "ground_truth": gt,
                                **{k: v for k, v in res.items() if hasattr(v, "to_csv")}}, Path(d))
            runs.append({Path(f["file"]).name: (f["rows"], f["sha256"]) for f in files})
        print(f"run {i + 1}: {len(runs[-1])} files", flush=True)
    a, b = runs
    rows = [{"file": k, "rows_run1": a[k][0], "rows_run2": b.get(k, (None,))[0], "sha256_run1": a[k][1],
             "sha256_run2": b.get(k, (None, None))[1], "identical": a[k] == b.get(k)} for k in sorted(a)]
    return {"scale": scale_name, "seed": config.SEED, "files": rows, "all_identical": all(r["identical"] for r in rows)}


def main():
    ap = argparse.ArgumentParser(prog="python -m slotting")
    ap.add_argument("command", choices=["all", "repro"])
    ap.add_argument("--scale", default="starter", choices=list(config.SCALES))
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-sql", action="store_true")
    ap.add_argument("--web", action="store_true", help="also write the dashboard bundle to web/public/data")
    a = ap.parse_args()
    config.SEED = a.seed
    out = Path(a.out) if a.out else ROOT / "out" / a.scale
    if a.command == "repro":
        rep = run_repro(a.scale)
        out.mkdir(parents=True, exist_ok=True)
        (out / "repro_report.json").write_text(json.dumps(rep, indent=1))
        print(f"reproducible: {rep['all_identical']} ({len(rep['files'])} files compared)")
        raise SystemExit(0 if rep["all_identical"] else 1)
    if out.exists():
        for sub in ("data", "ground_truth", "results"):
            shutil.rmtree(out / sub, ignore_errors=True)
    run_all(a.scale, out, not a.no_sql, a.web)


if __name__ == "__main__":
    main()
