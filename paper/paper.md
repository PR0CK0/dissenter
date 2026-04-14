# Disagreement as Signal: Adversarial Multi-Round Debate Improves LLM Ensemble Accuracy on Hard Benchmarks

**Authors:** Kayla Taylor, Dr. Tyler T. Procko, Dr. Omar Ochoa

**Abstract**

<!-- 150-250 words. Fill after results are in. Structure: -->
<!-- Problem: existing LLM ensembles chase consensus, treat disagreement as noise -->
<!-- Gap: no apples-to-apples benchmark comparison of open-source ensemble tools -->
<!-- Method: dissenter — role-differentiated adversarial debate with multi-round context passing -->
<!-- Results: [accuracy numbers on GPQA-D and HumanEval vs baselines + competitors] -->
<!-- Contribution: (1) first standardized evaluation of open-source LLM ensemble tools, (2) evidence that structured disagreement improves accuracy on hard reasoning tasks -->

---

## 1. Introduction

<!-- 1-2 pages. Three beats: -->

### 1.1 The Problem with Consensus

<!-- LLM ensembles exist (MoA, llm-council, consilium, llm-consortium). They all chase convergence. For factual questions this works. For hard reasoning where models legitimately disagree, eliminating disagreement throws away the most useful signal. -->

### 1.2 Disagreement as a Feature

<!-- Architectural decisions, PhD-level science (GPQA), competition math — these are domains where the right answer depends on reasoning chains, not recall. When models disagree, that tells you where the question is genuinely hard. A tool that surfaces and structures that disagreement should produce better answers than one that suppresses it. -->

### 1.3 Contributions

<!-- Bullet list: -->
<!-- 1. dissenter: open-source adversarial debate engine with role-differentiated prompting, multi-round context passing, and mutual critique -->
<!-- 2. First standardized benchmark comparison of 4 open-source LLM ensemble tools (dissenter, llm-council, llm-consortium, consilium) + baselines on GPQA-Diamond and HumanEval -->
<!-- 3. Evidence that inter-model disagreement rate correlates with question difficulty — disagreement is predictive, not just noise -->

---

## 2. Background

<!-- 1-2 pages. General landscape: what are LLM ensembles, why do people use them, what approaches exist at a high level. Don't compare to dissenter here — just set the stage. Save the head-to-head positioning for Related Work (Section 6) after the reader has seen your method and results. -->

### 2.1 LLM Ensemble Methods

<!-- The general idea: combine outputs from multiple LLMs to get better answers than any single model. -->
<!-- Three families (per the LLM Ensemble Survey arXiv 2502.18036): -->
<!--   - Before inference: routing/selection (pick the best model per query) -->
<!--   - During inference: token/span-level ensembling -->
<!--   - After inference: response selection, cascading, aggregation -->
<!-- dissenter falls in the "after inference" family — multi-round response aggregation with context passing. -->

### 2.2 Mixture of Agents

<!-- MoA (arXiv 2406.04692): canonical proposer→aggregator architecture. 3 layers of open-source LLMs. AlpacaEval 65.1% LC win rate. -->
<!-- Key insight: "collaborativeness" — some models improve when they see others' outputs. -->
<!-- Limitation: all models receive the same neutral prompt. No role differentiation. -->

### 2.3 Self-Consistency and Majority Voting

<!-- Wang et al. (2022): sample N chain-of-thought reasoning chains from one model, take the majority answer. -->
<!-- This is our majority-vote baseline. Simple, cheap, surprisingly effective. -->
<!-- Rethinking MoA (arXiv 2502.00674) found that Self-MoA (single model, diverse samples) beats Mixed-MoA (multiple models). Implication: diversity of framing > diversity of model. -->

### 2.4 Multi-Agent Debate

<!-- Irving et al. (2018): AI safety via debate — two agents argue before a judge. Theoretical alignment mechanism. -->
<!-- Applied debate: models assigned opposing positions, forced to engage with each other's arguments. -->
<!-- ICE (medRxiv 2024): iterative critique and ensemble. 3 models, up to 9 rounds. +45% on GPQA-Diamond. Closest to dissenter's --deep mode. -->

### 2.5 Mixture of Experts (MoE) — Disambiguation

<!-- MoE (Switch Transformer, GShard) is intra-model routing: different parameters activated for different tokens. -->
<!-- MoA / multi-agent debate are inter-model: different complete models or prompts for the same input. -->
<!-- Clarify this distinction — the names are confusingly similar but the approaches are fundamentally different. -->

---

## 3. Method

<!-- 2-3 pages. How dissenter works. -->

### 3.1 Architecture Overview

<!-- Diagram: Question → Config → Round 1 (parallel, role-differentiated) → Context → Round 2 → ... → Final (chairman or dual-arbiter) → Decision -->
<!-- Each round receives all prior rounds as context. Models run in parallel within a round. -->

### 3.2 Role-Differentiated Prompting

<!-- Why: Rethinking MoA showed that diversity of framing > diversity of model. -->
<!-- How: each model gets an adversarial role prompt (devil's advocate, skeptic, pragmatist, etc.) stored as external TOML files. Same model with 3 different roles produces more diverse reasoning than 3 different models with the same prompt. -->
<!-- Role catalog: table of roles, their mandates, and typical round assignments. -->

### 3.3 Multi-Round Debate with Context Passing

<!-- Round N receives all outputs from rounds 1..N-1 as context. This forces models to engage with prior arguments rather than reasoning in isolation. -->
<!-- Configurable depth: 2-round (debate → final) up to N-round. -->

### 3.4 Mutual Critique (--deep)

<!-- Inspired by ICE (iterative critique and ensemble). -->
<!-- After the last debate round, each model receives: -->
<!--   - The original question -->
<!--   - Its own prior response -->
<!--   - All other models' responses -->
<!-- Produces a critique: where others are wrong, what everyone missed, revised stance. -->
<!-- The critique round is then included in the context for the final synthesis. -->
<!-- Connection to ICE results: their +45% on GPQA-Diamond came from this pattern. -->

### 3.5 Synthesis

<!-- Single chairman: one model synthesizes all debate context into a structured decision (ADR format in production, answer-only in benchmark mode). -->
<!-- Dual-arbiter: conservative + liberal produce side-by-side recommendations, merged by a combine_model. (Not used in benchmark mode — we need one answer.) -->

### 3.6 Benchmark Mode

<!-- Modified synthesis prompt that produces a parseable FINAL ANSWER line. -->
<!-- Same debate engine, same rounds, same context passing — only the final output format changes. -->
<!-- Answer parser with progressive regex fallbacks for robustness. -->

---

## 4. Experimental Setup

<!-- 2 pages. Everything needed to reproduce. -->

### 4.1 Datasets

<!-- Table: -->
<!-- | Dataset | Size | Type | Source | License | -->
<!-- | GPQA-Diamond | 198 | MCQ (PhD science) | Idavidrein/gpqa | CC-BY-4.0 (gated) | -->
<!-- | HumanEval | 164 | Code generation | openai_humaneval | MIT | -->

<!-- Why these two: -->
<!-- - GPQA-D: hard enough that single models err significantly; direct comparison to ICE; ground truth (MCQ) -->
<!-- - HumanEval: different reasoning type (code); exact-match via test execution; well-established baseline -->

<!-- Answer shuffling: GPQA choices shuffled with seed=42 for reproducibility. -->

### 4.2 Models

<!-- List the exact model IDs and versions used. For local runs: ollama model + version hash. For API: provider/model-id. -->
<!-- Fairness constraint: all systems use the same underlying model(s) so we isolate the effect of the orchestration strategy. -->

### 4.3 Systems Under Evaluation

<!-- Table: -->
<!-- | System | Mode | Description | -->
<!-- | Single model | baseline | One model, one shot, no debate | -->
<!-- | Majority vote (N=3) | baseline | Same model × 3, majority answer | -->
<!-- | Majority vote (N=5) | baseline | Same model × 5, majority answer | -->
<!-- | dissenter (2-round) | ours | debate (2 roles) → chairman | -->
<!-- | dissenter (3-round) | ours | debate → refine → chairman | -->
<!-- | dissenter (--deep) | ours | debate → critique → chairman | -->
<!-- | llm-council | competitor | generate → peer rank → synthesize | -->
<!-- | llm-consortium | competitor | semantic agreement + arbiter | -->
<!-- | consilium | competitor | cross-pollination → ACH synthesis | -->

### 4.4 Evaluation Metrics

<!-- Primary: accuracy (% of questions answered correctly) -->
<!-- Secondary: -->
<!--   - Wall-clock latency (total and per-question) -->
<!--   - Token cost (for API models; estimated from litellm usage tracking) -->
<!--   - Parse failure rate (FINAL ANSWER line not extractable) -->
<!--   - Agreement rate (% of questions where all debate models gave the same answer before synthesis) -->

### 4.5 Statistical Tests

<!-- Paired analysis: McNemar's test for comparing two systems on the same question set. -->
<!-- Multiple comparisons: Benjamini-Hochberg FDR correction when comparing > 2 systems. -->
<!-- Confidence intervals: exact binomial 95% CI on accuracy. -->
<!-- Following the statistical rigor of ICE (mixed-effects models, FDR correction). -->

---

## 5. Results

<!-- 2-3 pages. Tables and charts. Fill after running benchmarks. -->

### 5.1 Main Results

<!-- Table: System × Dataset accuracy matrix -->
<!-- | System | GPQA-Diamond | HumanEval | -->
<!-- | Single model | X.X% | X.X% | -->
<!-- | Majority (3) | X.X% | X.X% | -->
<!-- | dissenter 2-round | X.X% | X.X% | -->
<!-- | dissenter --deep | X.X% | X.X% | -->
<!-- | llm-council | X.X% | X.X% | -->
<!-- | ... | ... | ... | -->

### 5.2 Cost-Accuracy Frontier

<!-- THE money chart. Scatter plot: x = total tokens (or $), y = accuracy. -->
<!-- Shows where dissenter sits on the Pareto frontier vs baselines and competitors. -->
<!-- Key question: does the extra cost of multi-round debate produce proportional accuracy gains? -->

### 5.3 Per-Domain Breakdown (GPQA)

<!-- GPQA-Diamond has domain labels (physics, chemistry, biology, etc.) -->
<!-- Table: System × Domain accuracy. Where does debate help most? Likely on the hardest domains. -->

### 5.4 Effect of Debate Depth

<!-- Compare: no debate (single) → 2-round → 3-round → --deep -->
<!-- At what point do diminishing returns set in? -->
<!-- Per-question analysis: which questions flipped from wrong → right with more rounds? -->

### 5.5 Ablation: Role Differentiation

<!-- Same models, same rounds, but all with the generic "analyst" role vs differentiated roles. -->
<!-- Tests the Rethinking MoA hypothesis: does framing diversity actually help? -->

---

## 6. Related Work

<!-- 1-2 pages. NOW that the reader has seen your method (Section 3) and results (Section 5), do the detailed head-to-head comparison. This is where you differentiate dissenter from each competing approach with specific design-choice contrasts. -->

### 6.1 Comparison with Academic Ensemble Methods

<!-- MoA: same layered architecture but no role differentiation; identical prompts at each layer. -->
<!-- ICE: closest to --deep mode. ICE iterates until consensus; dissenter preserves disagreement. ICE uses medical MCQ; we test on broader domains. -->
<!-- Self-MoA: supports our claim that framing diversity > model diversity, but Self-MoA doesn't use adversarial roles. -->

### 6.2 Comparison with Open-Source Tools

<!-- Table: design choices across all tools (adapted from README). -->
<!-- | Feature | dissenter | llm-council | llm-consortium | consilium | -->
<!-- | Role-differentiated prompts | ✓ | ✗ | ✗ | ✗ | -->
<!-- | Multi-round context passing | ✓ | ✗ | partial | partial | -->
<!-- | Mutual critique (--deep) | ✓ | partial | ✗ | ✓ | -->
<!-- | Published benchmarks | ✓ (this paper) | ✗ | ✗ | ✗ | -->
<!-- | ... | ... | ... | ... | ... | -->

<!-- For each tool: what they do well, what they miss, how dissenter's results compare (referencing Section 5). -->

### 6.3 Broader Context

<!-- AI safety via debate (Irving 2018) — theoretical ancestor. -->
<!-- Constitutional AI (Anthropic) — iterative refinement cousin. -->
<!-- Self-consistency (Wang 2022) — our majority-vote baseline is a direct implementation. -->

---

## 7. Discussion

<!-- 1-2 pages. Interpretation and implications. -->

### 7.1 Where Debate Helps

<!-- Categorize questions by: difficulty (single-model accuracy), domain, reasoning type. -->
<!-- Hypothesis: debate helps most on questions where single models disagree (high entropy across runs). -->

### 7.2 Disagreement as a Difficulty Signal

<!-- Core claim: inter-model disagreement rate during the debate round is predictive of question difficulty. -->
<!-- Method: for each question, compute the entropy of debate-round answers. Correlate with single-model accuracy. -->
<!-- If the correlation is strong: disagreement is not noise — it's a calibrated signal that the question is genuinely hard. -->
<!-- This finding is independently publishable regardless of the accuracy results. -->

### 7.3 When Debate Hurts

<!-- Failure modes: -->
<!-- - Easy factual questions where debate introduces doubt ("maybe it's not B...") -->
<!-- - Questions where all models are confidently wrong in the same way (debate amplifies shared bias) -->
<!-- - Token budget exhaustion: long debates produce long contexts that degrade synthesis quality -->

### 7.4 Practical Implications

<!-- When should practitioners use debate vs single-model? -->
<!-- Cost threshold: debate is worth it only on questions above X difficulty. -->
<!-- Possible hybrid: use disagreement rate as a routing signal — if models agree, skip debate; if they disagree, run full pipeline. -->

---

## 8. Limitations and Threats to Validity

<!-- Honest about what we can't claim. ~0.5 page. -->

<!-- - Dataset size: GPQA-D (198) and HumanEval (164) are small. Results may not generalize to larger benchmarks. -->
<!-- - Model pool: [specify which models]. Results are model-specific. -->
<!-- - Cost: multi-round debate is 3-10× more expensive than single-model inference. For easy questions this is wasted spend. -->
<!-- - Competitor wrappers: best-effort, may not represent each tool at its best configuration. -->
<!-- - No human evaluation: all metrics are automated (MCQ ground truth, code test cases). Open-ended quality not measured. -->
<!-- - Benchmark mode ≠ production mode: the answer-focused synthesis prompt is simpler than the ADR prompt. Results may not transfer to production ADR quality. -->

---

## 9. Conclusion

<!-- ~0.5 page. Three beats: -->
<!-- 1. What we showed: structured adversarial debate [improves/matches/doesn't improve] accuracy on hard benchmarks vs single models and competing ensemble tools. -->
<!-- 2. The disagreement signal: inter-model disagreement during debate is predictive of question difficulty — it's a feature, not a bug. -->
<!-- 3. Practical implication: for hard reasoning tasks, spending compute on structured debate produces better answers than spending the same compute on more samples from a single model (majority voting). -->
<!-- 4. Future work: larger benchmarks (MMLU-PRO, MATH), dynamic role inference, disagreement-guided routing, human evaluation on open-ended tasks. -->

---

## References

<!-- Use numbered references. Key citations: -->

<!-- [1] Wang et al., "Mixture-of-Agents Enhances Large Language Model Capabilities," arXiv 2406.04692, 2024. -->
<!-- [2] Golde & Atias, "ICE: Iterative Consensus Ensemble of LLMs," medRxiv, 2024. -->
<!-- [3] Zhi et al., "A Survey on LLM Ensemble," arXiv 2502.18036, 2025. -->
<!-- [4] Li et al., "Rethinking Mixture-of-Agents: Is Mixing Different Agents the Key to Stronger LLMs?," arXiv 2502.00674, 2025. -->
<!-- [5] Karpathy, "llm-council," GitHub, 2024. https://github.com/karpathy/llm-council -->
<!-- [6] Thomas, "llm-consortium," GitHub, 2024. https://github.com/irthomasthomas/llm-consortium -->
<!-- [7] Li, "consilium," GitHub, 2024. https://github.com/terry-li-hm/consilium -->
<!-- [8] Wang et al., "Self-Consistency Improves Chain of Thought Reasoning in Language Models," ICLR 2023. -->
<!-- [9] Irving et al., "AI safety via debate," arXiv 1805.00899, 2018. -->
<!-- [10] ReConcile, ACL 2024 — cross-lab multi-agent debate. -->
<!-- [11] CALM, 2024 — identity anchoring bias in LLM debate. -->
<!-- [12] Peacemaker/Troublemaker, 2024 — sycophancy in multi-round debate. -->

---

## Appendices

### A. Role Prompts

<!-- Table or listing of each role's full prompt text (from src/dissenter/roles/*.toml). -->
<!-- This is important for reproducibility — the exact framing is the intervention. -->

### B. Configuration Files

<!-- Full TOML for each benchmark config used (from configs/bench-*.toml). -->
<!-- Readers can copy these verbatim to reproduce. -->

### C. Per-Question Results

<!-- Link to supplementary data (results.json files) or a table of per-question outcomes. -->
<!-- Optional: include in a supplementary zip. -->

### D. Benchmark Infrastructure

<!-- Brief description of dissenter benchmark mode: how it wraps the debate engine, the answer parser regex, the code executor, the analysis tooling. -->
<!-- Enough for someone to reproduce or extend. -->
