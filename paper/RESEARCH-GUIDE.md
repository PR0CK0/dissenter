# Research Guide — Background Reading & Links

Resources for each section of the paper. Search terms, direct links to
papers and tools, and tips for what to look for.

---

## 1. Introduction

**Goal:** Motivate why this work matters. The reader should understand
the problem (LLM ensembles chase consensus) and the thesis (disagreement
is a feature) within one page.

### Key search terms
- "LLM ensemble methods"
- "multi-agent debate LLM"
- "mixture of agents"
- "LLM consensus vs disagreement"
- "AI-assisted decision making"
- "architectural decision records AI"

### Links
- arXiv search for "LLM ensemble": https://arxiv.org/search/?query=LLM+ensemble&searchtype=all
- Awesome-LLM-Ensemble (curated paper list): https://github.com/junchenzhi/Awesome-LLM-Ensemble

### Tips
- Frame around the real-world use case: engineering teams making complex
  architectural decisions, not toy benchmarks.
- The hook: "When experts disagree, that's not failure — it's the most
  useful signal you can get."
- Avoid over-selling. We're not claiming dissenter is better at
  everything. We're claiming structured disagreement helps on *hard*
  questions where models legitimately diverge.

---

## 2. Background / Related Work

**Goal:** Position dissenter against (a) academic ensemble methods,
(b) open-source tools, and (c) the broader multi-agent AI landscape.
The reader should see the gap dissenter fills.

### Academic papers (read these)

| Paper | Year | Key idea | Link |
|-------|------|----------|------|
| **Mixture of Agents (MoA)** | 2024 | Proposer → aggregator layers. AlpacaEval SOTA. | https://arxiv.org/abs/2406.04692 |
| **ICE: Iterative Critique and Ensemble** | 2024 | Mutual critique between models. +45% on GPQA-Diamond. | https://www.medrxiv.org/content/10.1101/2024.12.25.24319629v1 |
| **Rethinking MoA / Self-MoA** | 2025 | Single-model diversity > multi-model. Diversity of *framing* > diversity of *model*. | https://arxiv.org/abs/2502.00674 |
| **LLM Ensemble Survey** | 2025 | Taxonomy: before/during/after inference ensembles. Identifies gaps. | https://arxiv.org/abs/2502.18036 |
| **ReConcile** | ACL 2024 | Cross-lab panels +11.4% over homogeneous debate. | Search: "ReConcile ACL 2024 multi-agent" |
| **CALM** | 2024 | Identity anchoring bias in multi-agent debate. | Search: "CALM LLM debate bias 2024" |
| **Peacemaker / Troublemaker** | 2024 | Sycophancy correlation r=0.902 with wrong answers. Round 3+ sycophancy spike. | Search: "peacemaker troublemaker LLM sycophancy debate" |

### Open-source tools (compare against)

| Tool | Author | Link | What it does |
|------|--------|------|--------------|
| **llm-council** | Karpathy | https://github.com/karpathy/llm-council | Generate → peer rank → chairman synthesis |
| **llm-consortium** | irthomasthomas | https://github.com/irthomasthomas/llm-consortium | Semantic agreement clustering + arbiter |
| **consilium** | terry-li-hm | https://github.com/terry-li-hm/consilium | 5 LLMs + Claude judge, ACH synthesis |

### Broader landscape (for context, not direct comparison)

| Topic | Search terms | Why it matters |
|-------|-------------|----------------|
| Mixture of Experts (MoE) | "mixture of experts transformer", "switch transformer" | Different from MoA — MoE is intra-model routing, MoA is inter-model. Common confusion; clarify in the paper. |
| Multi-agent debate | "multi-agent debate LLM", "LLM debate benchmark" | The general technique. Position dissenter as a specific instantiation with role differentiation. |
| AI safety via debate | "AI safety debate Irving", "scalable oversight debate" | Irving et al. (2018) proposed debate as an AI alignment technique. Our work is applied (engineering decisions), not safety-focused, but cite for intellectual lineage. |
| Chain-of-thought / self-consistency | "self-consistency chain of thought Wang 2022" | Self-consistency (sample N CoTs, majority vote) is our majority-vote baseline. Position debate as going beyond sampling diversity. |
| Constitutional AI | "constitutional AI Anthropic" | Uses feedback loops to improve outputs. Thematic cousin — iterative refinement. Don't over-draw the parallel. |

### Tips
- Use a comparison table (like the README one) to visually contrast
  design decisions across all tools. Readers skim tables first.
- Be generous to competitors — describe their designs accurately before
  explaining what dissenter does differently. Reviewers notice when you
  strawman.
- The "Rethinking MoA" paper is your strongest citation: it directly
  supports role-differentiated prompting over model diversity.

---

## 3. Method

**Goal:** How dissenter works, at enough detail to reproduce without
reading the source code.

### Key concepts to explain
- **Role-differentiated prompting**: each model gets a unique adversarial
  mandate. Roles are external files (TOML), not hardcoded.
- **Multi-round context passing**: round N sees all outputs from rounds
  1..N-1. Models engage with prior arguments, not just the question.
- **Mutual critique (--deep)**: inspired by ICE. Each model critiques the
  others before the chairman synthesizes.
- **Chairman synthesis**: a single model produces the final answer from
  all debate context.
- **Benchmark mode**: same engine, different synthesis prompt (answer-only
  instead of ADR).

### Links
- dissenter README (architecture diagram): https://github.com/PR0CK0/dissenter
- Role prompts: see `src/dissenter/roles/*.toml` in the repo
- Benchmark mode: see `src/dissenter/benchmark/` and `benchmark-plan.md`

### Tips
- Include the architecture flow diagram. Redraw the README Mermaid
  diagram as a proper figure.
- Show an example: "Given the question '...', the devil's advocate
  argues X, the pragmatist argues Y, and the chairman synthesizes Z."
- The Method section should be tool-agnostic enough that someone could
  reimplement it from the description alone.

---

## 4. Results

**Goal:** Report the numbers. Tables and figures first, prose second.

### Metrics we use

| Metric | What it measures | How we compute it |
|--------|-----------------|-------------------|
| **Accuracy** | % of questions answered correctly | Exact match: predicted letter vs ground-truth letter (MCQ); test-case pass rate (code) |
| **Wall-clock latency** | Total and per-question time | `time.time()` around each question |
| **Token cost** | Total tokens consumed (proxy for $) | From litellm usage tracking (if available) |
| **Parse failure rate** | % of questions where FINAL ANSWER was not extractable | `parse_answer()` returns None |
| **Agreement rate** | % of questions where all debate models initially agreed | Computed from debate-round outputs before synthesis |

### Statistical tests

| Test | When to use | Link |
|------|-------------|------|
| **McNemar's test** | Comparing two systems on the same question set (paired binary outcomes) | https://en.wikipedia.org/wiki/McNemar%27s_test |
| **Benjamini-Hochberg** | FDR correction when making multiple pairwise comparisons | https://en.wikipedia.org/wiki/False_discovery_rate#Benjamini%E2%80%93Hochberg_procedure |
| **Exact binomial CI** | 95% confidence interval on accuracy | https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval |
| **Mixed-effects logistic regression** | Per-question random effects (ICE used this) | Search: "mixed effects logistic regression benchmark" |

### Tips
- Lead with the main results table. Readers look at tables before
  reading prose.
- The **cost-accuracy scatter** is the most important figure. If
  dissenter is on the Pareto frontier (more accurate per token than
  alternatives), that's the headline result.
- Report negative results honestly. If debate doesn't help on easy
  questions, say so — it's expected and it's informative.

---

## 5. Discussion

**Goal:** Interpret the results. What do they mean? Why did debate
help where it did? What are the failure modes?

### Key questions to address
- **Where does debate help?** Hard questions (low single-model accuracy),
  multi-step reasoning, questions with genuine trade-offs.
- **Where does it hurt?** Easy factual recall, questions where all models
  share the same bias, very long contexts that degrade synthesis.
- **Is disagreement predictive?** Compute entropy of debate-round answers
  per question. Correlate with difficulty (single-model accuracy). If
  strong: this is independently publishable.
- **Cost-accuracy tradeoff:** Is the extra compute worth it? For which
  question types?

### Search terms
- "when does LLM debate help"
- "multi-agent debate failure modes"
- "LLM sycophancy in debate"
- "ensemble diversity accuracy tradeoff"
- "calibration LLM confidence"

### Tips
- Don't just restate the numbers. Explain *why* the results look the
  way they do. Mechanistic explanations > summary.
- The "disagreement as difficulty signal" finding (if it holds) is the
  most novel contribution. Give it space.
- Acknowledge the cost. Multi-round debate is 3-10× more expensive.
  Be honest about when it's worth it and when it isn't.

---

## 6. Conclusion

**Goal:** One page max. Restate thesis, summarize results, point to
future work.

### Tips
- Three sentences max for the summary. The reader already read the paper.
- Future work bullets: larger benchmarks (MMLU-PRO, MATH), dynamic role
  inference, disagreement-guided routing (skip debate for easy questions),
  human evaluation on open-ended tasks.
- End with the thesis restated: "Disagreement is the signal, not the
  problem."

---

## Benchmarks — Direct Links

| Benchmark | Link | Size | How to get it |
|-----------|------|------|---------------|
| **GPQA-Diamond** | https://huggingface.co/datasets/Idavidrein/gpqa | 198 MCQ | Gated — accept license, then `python scripts/fetch_datasets.py --dataset gpqa` |
| **HumanEval** | https://huggingface.co/datasets/openai_humaneval | 164 code | Open — `python scripts/fetch_datasets.py --dataset humaneval` |
| **MMLU-PRO** (future) | https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro | 12K+ | Open |
| **MATH** (future) | https://huggingface.co/datasets/hendrycks/competition_math | 12.5K | Open |
| **AlpacaEval 2.0** (LLM judge, not ground truth) | https://github.com/tatsu-lab/alpaca_eval | 805 | Open |

---

## General Writing Tips

- **Figures > tables > prose.** If you can show it as a figure, don't
  describe it in words. If you can show it as a table, don't describe
  it as prose.
- **Active voice.** "We evaluate" not "An evaluation was performed."
- **Present tense for method.** "dissenter runs models in parallel"
  not "dissenter ran models."
- **Past tense for results.** "dissenter achieved X% accuracy" not
  "dissenter achieves."
- **Cite on first mention.** Every tool and paper gets a citation the
  first time it appears. After that, just the name.
- **Avoid "novel" and "state-of-the-art."** Let the results speak.
  Reviewers discount self-congratulation.
