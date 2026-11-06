"""Score the rule-based detector against the separate ground truth file.

This is the ONLY module that reads ground truth, and it runs after the
engine has finished: labels never feed back into slotting decisions.
"""
from __future__ import annotations

import pandas as pd

from .config import ISSUE_TYPES


def score(exceptions: pd.DataFrame, gt: pd.DataFrame) -> dict:
    det = exceptions[exceptions.source == "DATA_AUDIT"]
    out, tot = {}, {"tp": 0, "fp": 0, "fn": 0}
    for t in ISSUE_TYPES:
        d = set(det[det.issue_type == t].entity_id)
        g = set(gt[gt.issue_type == t].entity_id)
        tp, fp, fn = len(d & g), len(d - g), len(g - d)
        out[t] = {
            "ground_truth": len(g), "detected": len(d), "tp": tp, "fp": fp, "fn": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "false_positive_ids": sorted(d - g)[:20], "missed_ids": sorted(g - d)[:20],
        }
        for k in tot:
            tot[k] += {"tp": tp, "fp": fp, "fn": fn}[k]
    tot["precision"] = round(tot["tp"] / (tot["tp"] + tot["fp"]), 4) if tot["tp"] + tot["fp"] else None
    tot["recall"] = round(tot["tp"] / (tot["tp"] + tot["fn"]), 4) if tot["tp"] + tot["fn"] else None
    ctrl = gt[gt.issue_type == "NONE"]
    flagged = set(det.entity_id)
    fa = ctrl[ctrl.entity_id.isin(flagged)]
    controls = {"controls": len(ctrl), "false_alarms": len(fa),
                "specificity": round(1 - len(fa) / len(ctrl), 4) if len(ctrl) else None,
                "by_subtype": ctrl.issue_subtype.value_counts().sort_index().to_dict(),
                "false_alarm_ids": sorted(fa.entity_id)[:20]}
    subtypes = gt.groupby(["issue_type", "issue_subtype"]).size().reset_index(name="n").to_dict("records")
    return {"by_issue": out, "overall": tot, "negative_controls": controls, "ground_truth_subtypes": subtypes,
            "note": ("Detector uses only input tables; ground truth is read here, after the run, for scoring. "
                     "Labels come from the same documented rules, so a perfect score shows the detector implements "
                     "the rules correctly (time windows and thresholds are probed by the negative controls); "
                     "it is not evidence of generalisation to unseen anomaly types.")}
