# dissenter Benchmark Plan

A roadmap for evaluating dissenter against existing LLM ensemble tools and writing it up as a paper.

---

## 1. Benchmark Mode Design

dissenter currently produces prose ADRs — for benchmarks we need parseable single answers. Two design options:

### Option A: New `dissenter benchmark` subcommand (recommended)

```bash
dissenter benchmark --dataset gpqa --config benchmark.toml --output results.json
```

- Loads a dataset (JSONL of questions + ground truth)
- Runs each question through the full pipeline
- Uses a benchmark-specific synthesis prompt: "Output ONLY the letter of the correct answer on the final line."
- Parses the answer, compares to ground truth, writes per-question results
- No ADR generation — pure answer extraction
- Tracks tokens, cost, and latency per question

**Output format (JSON):**
```json
{
  "dataset": "gpqa-diamond",
  "config": "benchmark.toml",
  "total": 198,
  "correct": 142,
  "accuracy": 0.717,
  "total_cost_usd": 12.34,
  "total_latency_s": 4521,
  "questions": [
    {
      "id": "gpqa_001",
      "question": "...",
      "ground_truth": "B",
      "predicted": "B",
      "correct": true,
      "rounds": [...],
      "tokens": 4123,
      "cost_usd": 0.045,
      "latency_s": 23.1
    }
  ]
}
```

### Option B: `--benchmark` flag on `ask`

- Adds the parseable-output instruction to the synthesis prompt
- Doesn't save ADR
- User wraps it with their own runner script

**Recommendation: Option A.** Cleaner for a paper — one tool that does everything end-to-end and emits a results file you can publish as supplementary material.

### Components needed

1. **Dataset loader** — read JSONL, normalize question format
2. **Answer parser** — extract letter (MCQ), number (math), code block (HumanEval)
3. **Benchmark synthesis prompt** — separate from ADR prompt, demands structured output
4. **Results writer** — JSON with per-question detail
5. **Aggregator** — compute accuracy, cost, latency stats; print summary

### TUI + CLI parity

Benchmark mode must be available in **both** the CLI and the TUI:

- **CLI:** `dissenter benchmark --dataset gpqa --config benchmark.toml --output results.json`
- **TUI:** A new "Benchmark" page in the sidebar (under NEW or as a new section) with:
  - Dataset picker (Select widget)
  - Config picker (re-uses Ask form's config selector)
  - Sample size / limit input
  - Output filename input
  - "Run benchmark" button
  - Live progress (per-question status, running accuracy, ETA)
  - Final summary panel (accuracy, cost, latency) with link to results.json
- The same engine drives both — `dissenter.benchmark` module called by CLI command and TUI screen.

---

## 2. Dataset Selection

Pick datasets that play to dissenter's strengths: hard questions where reasoning matters, with ground truth so there's no LLM-judge bias.

### Primary datasets

| Dataset | Size | Type | Why it matters | Est. cost per system |
|---------|------|------|----------------|---------------------|
| **GPQA-Diamond** | 198 MCQ | PhD-level science | ICE got +45% here. Hard enough that debate adds value. Direct comparison to ICE. | ~$50–100 |
| **HumanEval** | 164 problems | Python code generation | Exact-match (test cases). Different reasoning style. Cheap. | ~$30 |

### Optional expansion (if results look promising)

| Dataset | Size | Type | Why |
|---------|------|------|-----|
| **MMLU-PRO** (subset) | 500–1000 MCQ | Multi-domain reasoning | Sample 50 per domain. Broad coverage. |
| **MATH** (level 5 subset) | 500 problems | Competition math | Pure reasoning, exact-match. Filter to hardest only. |

### Datasets to skip

- **AlpacaEval / MT-Bench** — Open-ended preference, requires GPT-4 judge → noise
- **Vanilla MMLU** — Too easy, single models already saturate it
- **HellaSwag** — Commonsense, single model handles fine, no room for debate to help

### Recommended starting point

**GPQA-Diamond + HumanEval** (362 questions total). Cheap, fast, two very different reasoning types, both have direct prior work to cite.

---

## 3. Comparing Against Competitors

None of the three GitHub competitors have published benchmark numbers. dissenter would be the first to evaluate them on standardized datasets — that alone is paper-worthy.

| Tool | Install | Wrap-ability | Effort |
|------|---------|--------------|--------|
| **llm-council** (Karpathy) | Python pkg, `uv pip install` | Wrap stdout, parse last letter | 2–3 hrs |
| **llm-consortium** | `llm install llm-consortium` plugin | CLI wrapper, parse output | 2–3 hrs |
| **consilium** | Rust binary, `cargo install` | Has structured output already | 4–5 hrs |

Each needs a thin Python wrapper that:
1. Takes a question
2. Calls the tool with the same model set
3. Parses the answer
4. Tracks tokens + latency

**Fairness constraint:** all systems must use the same underlying model pool to isolate the effect of the orchestration strategy.

---

## 4. Paper Structure

**Working title:** *Disagreement as Signal: Adversarial Multi-Round Debate for LLM Decision Making*

**Target length:** 6–8 pages.
**Venue options:** NeurIPS workshops, ICLR Tiny Papers, arXiv preprint.

### Outline

```
1. Introduction
   - The problem with consensus-seeking ensembles
   - Disagreement as signal vs. noise
   - Contribution: first apples-to-apples ensemble comparison + new method

2. Related Work
   - MoA / ICE / Rethinking MoA (academic)
   - llm-council / llm-consortium / consilium (open source)
   - Position dissenter vs. each

3. Method
   - Adversarial role-differentiated prompting
   - Multi-round debate with context passing
   - Chairman synthesis vs. dual-arbiter
   - --deep mutual critique

4. Experimental Setup
   - Datasets: GPQA-D, HumanEval (+ optional MMLU-PRO, MATH)
   - Baselines:
     a. Best single model (Claude 3.5 Sonnet, GPT-4o, Gemini 2.0)
     b. Majority voting (3× same model)
     c. llm-council
     d. llm-consortium
     e. consilium
     f. dissenter (1-round)
     g. dissenter (2-round)
     h. dissenter (--deep)
   - Same model pool for all systems (fairness)
   - Metrics: accuracy, cost ($), latency, agreement rate

5. Results
   - Main accuracy table
   - Cost-accuracy Pareto frontier (the money chart)
   - Per-domain breakdown
   - Statistical tests: paired t-test, FDR correction, mixed-effects
     (à la ICE)

6. Analysis
   - Where debate helps: hard reasoning, multi-step problems
   - Where it doesn't: pure factual recall
   - Disagreement-as-difficulty signal: does inter-model disagreement
     correlate with question difficulty? If yes, that's a publishable
     finding on its own.

7. Limitations
   - Cost & latency vs. single models
   - Token budget
   - Limited to MCQ/exact-match for evaluation

8. Conclusion
```

---

## 5. Execution Order

1. **Build `dissenter benchmark`** subcommand — dataset loader, answer parser, results JSON writer
2. **Run on GPQA-Diamond** with three dissenter configs (1-round, 2-round, `--deep`) + best single model — sanity check before investing in competitor wrappers
3. **If results look good**, build the three competitor wrappers
4. **Expand to HumanEval** — second reasoning type
5. **Optional:** add MMLU-PRO + MATH for the full paper
6. **Write the paper**

---

## 6. Reference: Benchmarks Used by Cited Work

| Paper / Tool | Benchmarks | Metrics | Ground Truth | Statistical Rigor |
|--------------|-----------|---------|--------------|-------------------|
| **MoA** (arXiv 2406.04692) | AlpacaEval 2.0, MT-Bench, FLASK | LC win rate, GPT-4 scores | No (open-ended) | Std dev over 3 runs |
| **ICE** (medRxiv 2024) | Israeli Primary Care (200), Katz Medical (655), MMLU-PRO (3000), GPQA-Diamond (198) | Accuracy % | Yes (MCQ) | Paired t-tests, FDR correction, mixed-effects logistic regression |
| **Rethinking MoA** (arXiv 2502.00674) | AlpacaEval 2.0, MT-Bench, MMLU-redux (3000), CRUX (800), MATH (5000) | Win rate, accuracy | Mixed | Vendi Score for diversity |
| **Ensemble Survey** (arXiv 2502.18036) | Catalogs MixInstruct + RouterBench | N/A (survey) | N/A | N/A |
| **llm-council** | None | Peer ranking | No | No |
| **llm-consortium** | Custom prompts | Blind judge win rate | No | Framework only, no published results |
| **consilium** | None | None | No | No |

ICE is the gold standard for rigor — 4,058 questions, mixed-effects logistic regression, FDR correction. Their +45% on GPQA-Diamond with critique rounds is directly comparable to dissenter's `--deep`.
