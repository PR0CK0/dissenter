# Benchmark datasets

Datasets used to evaluate dissenter. All are in the normalized JSONL
format defined by `src/dissenter/benchmark/datasets.py`.

## Format

One question per line, each line is a JSON object:

```json
{
  "id": "gpqa_d_001",
  "type": "mcq",
  "question": "What is ...",
  "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "B",
  "metadata": {"domain": "physics", "source": "gpqa_diamond"}
}
```

`type` is `mcq`, `numeric`, or `code`. `choices` only applies to MCQ.

## Committed datasets

| File | Purpose |
|------|---------|
| `test-mini.jsonl` | 5 hand-written sanity questions for pipeline smoke tests |

## Fetched datasets (gitignored)

These are downloaded from Hugging Face via `scripts/fetch_datasets.py`:

| File | Source | Size | License | Notes |
|------|--------|------|---------|-------|
| `gpqa_diamond.jsonl` | `Idavidrein/gpqa` (`gpqa_diamond`) | 198 | CC-BY-4.0, gated | PhD-level science MCQ |
| `humaneval.jsonl` | `openai_humaneval` | 164 | MIT | Python code generation |

### Fetching

```bash
# Install the optional benchmark deps
uv pip install -e '.[benchmark]'

# Individually
python scripts/fetch_datasets.py --dataset gpqa
python scripts/fetch_datasets.py --dataset humaneval

# All at once
python scripts/fetch_datasets.py --dataset all
```

### GPQA is gated

GPQA-Diamond requires accepting the dataset license before download:

1. Visit https://huggingface.co/datasets/Idavidrein/gpqa
2. Accept the terms
3. `huggingface-cli login` (create a token at https://huggingface.co/settings/tokens)
4. Then run the fetch script

### HumanEval is open

No login required — just run the fetch script.

## Reproducibility

- GPQA fetching uses `seed=42` for answer shuffling, so the same question has
  the same ground-truth letter across runs.
- Datasets are gitignored to keep the repo small, but the fetch script makes
  reproduction trivial — anyone with HF access gets the same JSONL.

## Running a benchmark

Once you have a dataset file, run:

```bash
dissenter benchmark datasets/gpqa_diamond.jsonl \
  -c configs/bench-ministral-baseline.toml \
  -o results/gpqa-ministral.json
```
