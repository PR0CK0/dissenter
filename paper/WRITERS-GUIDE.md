# Writer's Guide

Instructions for converting `paper.md` into a polished manuscript.

## Structure

The skeleton is in `paper.md`. HTML comments (`<!-- ... -->`) are writing
prompts — expand each into prose, then delete the comment. Sections are
ordered for a standard ML systems paper (NeurIPS / ICLR workshop format).

**Target length:** 6-8 pages, single column, 11pt, with an additional
2-4 pages for appendices + references.

## Tone

- Technical but accessible. A senior ML engineer should be able to follow
  without domain expertise in multi-agent systems.
- Opinionated where appropriate — this is a systems paper with a clear
  thesis (disagreement as signal, not noise).
- No hedging on the design motivation. Hedge only on quantitative claims
  (confidence intervals, p-values).
- Cite heavily in Related Work (Section 2). Cite sparingly elsewhere —
  each section should be self-contained enough to read without checking
  footnotes.

## What's ready now

- Sections 1-3 (Introduction, Related Work, Method): fully writable from
  the prompts + the README + the codebase. Tyler can answer design
  questions directly.
- Section 4 (Experimental Setup): writable except for the exact model
  versions (Tyler will provide after runs).
- Appendices A-D: can be populated from the repo directly.

## What's blocked on benchmark runs

- Section 5 (Results): needs the actual accuracy numbers from running
  `dissenter benchmark` on GPQA-Diamond and HumanEval.
- Section 6 (Analysis): needs the results to interpret.
- Section 8 (Conclusion): needs the results to summarize.
- Abstract: write last, once the story is clear.

## Figures needed

1. **Architecture diagram** (Section 3.1) — flow from question through
   rounds to synthesis. Use the Mermaid diagram in README.md as a
   starting point; redraw in a publication-quality tool (draw.io, Figma,
   or tikz).

2. **Cost-accuracy scatter** (Section 5.2) — x = total tokens, y =
   accuracy. One point per system. Pareto frontier highlighted. This is
   the most important figure in the paper.

3. **Accuracy by domain** (Section 5.3) — grouped bar chart, one group
   per GPQA domain, bars for each system.

4. **Debate depth curve** (Section 5.4) — line chart: x = debate rounds,
   y = accuracy. Shows diminishing returns.

## Tables needed

1. **System comparison** (Section 2.3) — design choices across tools.
   Adapt from the README comparison table.

2. **Main results** (Section 5.1) — System × Dataset accuracy matrix.

3. **Per-domain breakdown** (Section 5.3) — System × Domain.

4. **McNemar contingency** (Section 5.1 or 5.4) — paired comparison
   between dissenter and best baseline.

## Data files

All benchmark results will be in `results/*.json`. Use
`scripts/analyze_results.py` to generate summary tables:

```bash
python scripts/analyze_results.py results/*.json --by-domain --output paper/results-summary.md
python scripts/analyze_results.py results/single.json results/debate.json --compare --output paper/paired-comparison.md
```

## Venue considerations

- **arXiv preprint**: no page limit, no formatting constraints. Good for
  getting the work visible quickly.
- **NeurIPS workshops** (e.g., Foundation Models for Decision Making):
  typically 4-6 pages, no appendix.
- **ICLR Tiny Papers**: 2 pages + references. Would need a much more
  compressed version focusing on the main result only.
- **EMNLP / ACL**: full paper track, 8 pages. Good fit if results are
  strong.

Recommend starting with arXiv preprint (no deadline pressure), then
submitting a compressed version to a relevant workshop.

## Authors

1. **Kayla Taylor** — primary author / writer
2. **Dr. Tyler T. Procko** — tool design, implementation, experiments
3. **Dr. Omar Ochoa** — advisor
