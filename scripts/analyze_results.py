#!/usr/bin/env python3
"""Aggregate dissenter benchmark results and emit comparison tables.

Reads one or more results.json files produced by `dissenter benchmark`
and emits a markdown table comparing them. Supports per-domain breakdown
and basic paired statistics when you have matching question IDs across runs.

Usage:
    python scripts/analyze_results.py results/*.json
    python scripts/analyze_results.py results/a.json results/b.json --compare
    python scripts/analyze_results.py results/*.json --by-domain
    python scripts/analyze_results.py results/*.json --output analysis.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_result(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def short_config(cfg: str) -> str:
    """Strip long path components from config label for display."""
    if not cfg:
        return "?"
    # Trim absolute paths down to the filename
    if "/" in cfg:
        cfg = cfg.split("/")[-1]
    return cfg


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def fmt_dur(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    mins, secs = divmod(seconds, 60)
    return f"{int(mins)}m{int(secs):02d}s"


# ── Main summary table ─────────────────────────────────────────────────
def summary_table(results: list[dict]) -> str:
    lines = [
        "## Summary",
        "",
        "| Config | Dataset | Total | Correct | Accuracy | Errors | Time | Avg/Q |",
        "|--------|---------|------:|--------:|---------:|-------:|-----:|------:|",
    ]
    for r in results:
        total = r["total"]
        if total == 0:
            continue
        avg = r["total_latency_s"] / total
        lines.append(
            f"| {short_config(r['config'])} "
            f"| {r['dataset']} "
            f"| {total} "
            f"| {r['correct']} "
            f"| {fmt_pct(r['accuracy'])} "
            f"| {r['errors']} "
            f"| {fmt_dur(r['total_latency_s'])} "
            f"| {avg:.1f}s |"
        )
    return "\n".join(lines)


# ── Per-domain breakdown ───────────────────────────────────────────────
def by_domain_table(results: list[dict]) -> str:
    """Group each run's questions by metadata.domain and compute per-domain accuracy."""
    lines = ["", "## Accuracy by domain", ""]
    # Build a sparse matrix: domain → config → (correct, total)
    matrix: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    configs: list[str] = []
    for r in results:
        label = short_config(r["config"])
        configs.append(label)
        domain_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for q in r["questions"]:
            domain = (q.get("metadata") or {}).get("domain") or "?"
            domain_counts[domain][1] += 1
            if q["correct"]:
                domain_counts[domain][0] += 1
        for domain, (correct, total) in domain_counts.items():
            matrix[domain][label] = (correct, total)

    if not matrix:
        return ""

    header = "| Domain | " + " | ".join(configs) + " |"
    sep = "|--------|" + "|".join(["------:"] * len(configs)) + "|"
    lines.append(header)
    lines.append(sep)

    for domain in sorted(matrix.keys()):
        row = [domain]
        for cfg in configs:
            cell = matrix[domain].get(cfg)
            if cell:
                correct, total = cell
                row.append(f"{correct}/{total} ({fmt_pct(correct / total)})")
            else:
                row.append("—")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# ── Paired comparison ──────────────────────────────────────────────────
def paired_compare(a: dict, b: dict) -> str:
    """Emit a McNemar-style table for two runs over the same question set.

    Pairs questions by id. Reports:
      - accuracy delta
      - questions where only A was correct
      - questions where only B was correct
      - questions where both were correct / both wrong
      - sign-test p-value (two-sided, exact binomial)
    """
    a_by_id = {q["id"]: q for q in a["questions"]}
    b_by_id = {q["id"]: q for q in b["questions"]}
    shared_ids = sorted(set(a_by_id) & set(b_by_id))

    if not shared_ids:
        return "\n*No shared question IDs between runs — cannot pair.*\n"

    a_only = 0
    b_only = 0
    both = 0
    neither = 0
    for qid in shared_ids:
        a_c = a_by_id[qid]["correct"]
        b_c = b_by_id[qid]["correct"]
        if a_c and b_c:
            both += 1
        elif a_c and not b_c:
            a_only += 1
        elif b_c and not a_c:
            b_only += 1
        else:
            neither += 1

    discordant = a_only + b_only
    p_value = _sign_test_p(a_only, discordant) if discordant > 0 else None
    a_acc = (both + a_only) / len(shared_ids)
    b_acc = (both + b_only) / len(shared_ids)

    a_label = short_config(a["config"])
    b_label = short_config(b["config"])

    lines = [
        "",
        f"## Paired comparison: {a_label} vs {b_label}",
        "",
        f"- Shared questions: {len(shared_ids)}",
        f"- {a_label}: {both + a_only}/{len(shared_ids)} = {fmt_pct(a_acc)}",
        f"- {b_label}: {both + b_only}/{len(shared_ids)} = {fmt_pct(b_acc)}",
        f"- Delta: {fmt_pct(b_acc - a_acc)} (B − A)",
        "",
        "| | B correct | B wrong |",
        "|---|---:|---:|",
        f"| **A correct** | {both} | {a_only} |",
        f"| **A wrong** | {b_only} | {neither} |",
        "",
    ]
    if p_value is not None:
        lines.append(f"Two-sided sign-test p-value: `{p_value:.4f}`")
        if p_value < 0.05:
            lines.append("→ Statistically significant at α=0.05")
    return "\n".join(lines)


def _sign_test_p(successes: int, trials: int) -> float:
    """Two-sided exact binomial test with p=0.5 (sign test).

    Simple implementation; no scipy dependency.
    """
    if trials == 0:
        return 1.0
    # P(X = k) where X ~ Binomial(trials, 0.5)
    def pmf(k: int) -> float:
        return math.comb(trials, k) * (0.5 ** trials)

    obs = pmf(successes)
    # Two-sided: sum of PMFs ≤ observed
    total = sum(pmf(k) for k in range(trials + 1) if pmf(k) <= obs + 1e-12)
    return min(1.0, total)


# ── Main ───────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results",
        nargs="+",
        type=Path,
        help="One or more results.json files",
    )
    parser.add_argument(
        "--by-domain",
        action="store_true",
        help="Include per-domain accuracy breakdown",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Paired comparison (requires exactly 2 results files with shared question IDs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write markdown report to file instead of stdout",
    )
    args = parser.parse_args()

    results = [load_result(p) for p in args.results]

    parts = [summary_table(results)]

    if args.by_domain:
        parts.append(by_domain_table(results))

    if args.compare:
        if len(results) != 2:
            print("--compare requires exactly 2 result files", file=sys.stderr)
            return 1
        parts.append(paired_compare(results[0], results[1]))

    report = "\n\n".join(p for p in parts if p)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
