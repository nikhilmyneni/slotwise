"""Export: CSV + JSON + SQLite + SQL seed, ground truth kept apart, manifest with checksums."""
from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .config import GENERATOR_VERSION, PARAMS, Scale
from .validate import FK, PK

PROVENANCE = ("100% synthetic. No external dataset was used; no personal or confidential data. "
              "City names are used only as warehouse labels.")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind == "M":
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S").where(out[c].notna(), None)
        elif out[c].dtype == object:
            out[c] = out[c].map(lambda v: v.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(v, pd.Timestamp) else v)
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csvs(frames: dict[str, pd.DataFrame], folder: Path) -> list[dict]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name, df in frames.items():
        p = folder / f"{name}.csv"
        _clean(df).to_csv(p, index=False, lineterminator="\n")
        out.append({"file": p.as_posix(), "rows": int(len(df)), "bytes": p.stat().st_size, "sha256": sha256(p)})
    return out


def write_json(frames: dict[str, pd.DataFrame], folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        _clean(df).to_json(folder / f"{name}.json", orient="records", indent=None, date_format="iso")


def _sqltype(s: pd.Series) -> str:
    return {"b": "INTEGER", "i": "INTEGER", "u": "INTEGER", "f": "REAL"}.get(s.dtype.kind, "TEXT")


def write_sql(tables: dict[str, pd.DataFrame], db_path: Path, seed_path: Path):
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    fks = {}
    for c, col, p, _ in FK:
        fks.setdefault(c, []).append(f"FOREIGN KEY ({col}) REFERENCES {p}({PK[p]})")
    for name, df in tables.items():
        cols = [f'"{c}" {_sqltype(df[c])}' + (" PRIMARY KEY" if c == PK[name] else "") for c in df.columns]
        con.execute(f'CREATE TABLE "{name}" ({", ".join(cols + fks.get(name, []))})')
    for name, df in tables.items():
        d = _clean(df).astype(object).where(_clean(df).notna(), None)
        rows = [tuple(int(v) if isinstance(v, (bool, np.bool_)) else (v.item() if isinstance(v, np.generic) else v)
                      for v in r) for r in d.itertuples(index=False, name=None)]
        con.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" * len(df.columns))})', rows)
    con.commit()
    with open(seed_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Synthetic slotting dataset seed (SQLite dialect). Load with: sqlite3 slotting.db < seed.sql\n")
        f.write("PRAGMA foreign_keys=OFF;\n")
        for line in con.iterdump():
            f.write(line + "\n")
    con.close()


def export_all(root: Path, scale: Scale, tables, gt, results, validation, evaluation, dictionary_md: str,
               with_sql: bool = True) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    files = write_csvs(tables, root / "data" / "csv")
    write_json(tables, root / "data" / "json")
    if with_sql:
        write_sql(tables, root / "data" / "slotting.db", root / "data" / "seed.sql")
    files += write_csvs({"ground_truth": gt}, root / "ground_truth")
    _clean(gt).to_json(root / "ground_truth" / "ground_truth.json", orient="records")
    res_frames = {k: v for k, v in results.items() if isinstance(v, pd.DataFrame)}
    files += write_csvs(res_frames, root / "results")
    (root / "results" / "metrics.json").write_text(json.dumps(results["metrics"], indent=2, default=str))
    (root / "results" / "evaluation.json").write_text(json.dumps(evaluation, indent=2, default=str))
    (root / "validation_summary.json").write_text(json.dumps(validation, indent=2, default=str))
    (root / "DATA_DICTIONARY.md").write_text(dictionary_md, encoding="utf-8")
    (root / "README.md").write_text(
        f"# SlotWise {scale.name} dataset\n\n"
        f"Synthetic warehouse slotting data generated with seed `{config.SEED}`. "
        f"Regenerate from the repository root with "
        f"`python -m slotting all --scale {scale.name} --seed {config.SEED}`.\n\n"
        "- `data/csv/` and `data/json/`: operational input tables.\n"
        "- `data/slotting.db` and `data/seed.sql`: SQLite database and SQL seed (unless `--no-sql` was used).\n"
        "- `results/`: proposals, simulation comparisons, exceptions and metrics.\n"
        "- `ground_truth/`: separate labelled answer key. Never use as input features.\n"
        "- `DATA_DICTIONARY.md`: fields, keys, values, units and validation rules.\n"
        "- `validation_summary.json`: integrity and business-rule checks.\n"
        "- `manifest.json`: provenance, source command, versions, row counts and SHA-256 hashes.\n"
        "- `repro_report.json`: optional two-run row count and checksum comparison.\n\n"
        "All records are synthetic; no external data or personal information is included.\n",
        encoding="utf-8",
    )
    manifest = {
        "dataset": f"slotting-{scale.name}", "scale": scale.__dict__, "seed": config.SEED,
        "generator_version": GENERATOR_VERSION,
        "command": f"python -m slotting all --scale {scale.name} --seed {config.SEED}",
        "horizon": {"start": PARAMS.horizon_start.isoformat(), "weeks": PARAMS.horizon_weeks,
                    "peak_weeks": list(PARAMS.peak_weeks), "train_weeks": PARAMS.train_weeks},
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
        "provenance": PROVENANCE,
        "files": [{**f, "file": Path(f["file"]).relative_to(root).as_posix()} for f in files],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
