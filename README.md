# OSS Models PM Ops

`oss-models-pm-ops` is a proof-of-concept benchmark for PM workflows on real codebases.

It compares two approaches:

- **Control:** `anthropic/claude-opus-4.8` handles each PM task end-to-end.
- **Experiment:** an orchestrated workflow routes subtasks to open-source models via OpenRouter.

The goal is not to ship a production PM tool yet. The goal is to generate a useful, reproducible article about when orchestrated open-source models are good enough for product-management work, and where they still fall short.

## Why This Exists

PM work over a codebase is rarely one task. It is a bundle of smaller tasks:

- Read the codebase and understand architecture.
- Research the competitive landscape.
- Explain a feature in plain English.
- Turn code context into engineering tickets.
- Write a PRFAQ grounded in implementation reality.

Frontier models can do this end-to-end. This repo tests whether a cheaper open-source pipeline can get close by decomposing the work and assigning each subtask to a model suited to the job.

## What It Benchmarks

The benchmark runs five PM tasks against a target codebase:

1. **Codebase review** — architecture, data flow, key modules, risks.
2. **Competitive research** — competitor matrix, market trends, differentiation.
3. **ELI5** — plain-English feature explanation for non-technical stakeholders.
4. **Tickets** — engineering tickets grounded in real files/modules.
5. **PRFAQ** — press release plus internal/customer/technical FAQ.

## Model Map

| Role | Model |
|---|---|
| Control | `anthropic/claude-opus-4.8` |
| Orchestrator / synthesis | `deepseek/deepseek-v4-flash` |
| Code understanding | `qwen/qwen3-coder-flash` |
| Drafting / explanation | `qwen/qwen3-30b-a3b` |
| Cheap parallel worker | `qwen/qwen3-8b` |
| Judge | `openai/gpt-5.5` |

Prices are snapshotted in `scripts/run_benchmark.py` and should be refreshed from OpenRouter before publishing final numbers.

## How The Harness Works

Before calling models, the harness inspects the target codebase and generates a `ground-truth.json` file with checkable facts:

- Tech stack
- Entry points
- API routes
- Data models / schemas
- Tests
- Real file paths

It then runs both tracks and writes:

- `control/*.md` — Opus outputs
- `orchestrated/*.md` — open-source pipeline outputs
- `deterministic-scores.json` — file/tech/route/schema grounding checks
- `cost-latency.md` — token usage, estimated cost, and latency for every model call
- `judge-feedback.md` — optional GPT-5.5 blind judging
- `comparison-table.md` — article-ready summary

## Usage

### 1. Dry run without API calls

Use this first to verify the harness can inspect the target codebase and generate the expected output structure without spending any tokens.

```bash
python3 scripts/run_benchmark.py /path/to/codebase \
  --feature "AI-powered meal planning" \
  --dry-run \
  --skip-judge
```

This writes a timestamped output directory like:

```text
output/benchmark-20260616-042204/
```

The dry run should produce `ground-truth.json`, `codebase-context.md`, placeholder model outputs, and cost/latency estimates based on prompt sizes.

### 2. Run the benchmark without the GPT-5.5 judge

Use this when you want real model outputs and latency/cost measurements, but do not want to spend on the judge yet.

```bash
export OPENROUTER_API_KEY="sk-or-..."

python3 scripts/run_benchmark.py /path/to/codebase \
  --feature "AI-powered meal planning" \
  --competitors "Paprika,Mealime,Yummly,Copy Me That" \
  --skip-judge
```

### 3. Run the full benchmark with GPT-5.5 judging

Use this for article-ready results after you are confident the prompt, feature, competitors, and codebase path are right.

```bash
export OPENROUTER_API_KEY="sk-or-..."

python3 scripts/run_benchmark.py /path/to/codebase \
  --feature "AI-powered meal planning" \
  --competitors "Paprika,Mealime,Yummly,Copy Me That"
```

Outputs are written to `output/benchmark-<timestamp>/`.

### 4. Re-run with a different feature

The codebase path and feature are independent. To test a different PM workflow, keep the same codebase and change `--feature`:

```bash
python3 scripts/run_benchmark.py /path/to/codebase \
  --feature "Add team workspaces and role-based access control" \
  --competitors "Notion,Airtable,Coda" \
  --skip-judge
```

### 5. Re-run with more or less code context

If the codebase is large, tune how many files and bytes per file are included in model prompts:

```bash
python3 scripts/run_benchmark.py /path/to/codebase \
  --feature "AI-powered meal planning" \
  --max-files 40 \
  --max-file-bytes 16000 \
  --skip-judge
```

The deterministic ground-truth extraction scans broadly for routes and schemas even when prompt context is capped.

## Output Review

Each run writes a timestamped folder under `output/`. The important files are:

| File | Purpose |
|---|---|
| `ground-truth.json` | Codebase-derived eval facts: tech stack, routes, schemas, files |
| `codebase-context.md` | Exact context sent into model prompts |
| `control/*.md` | Opus 4.8 outputs for each PM task |
| `orchestrated/*.md` | Open-source orchestration outputs for each PM task |
| `deterministic-scores.json` | Auto-scored grounding checks |
| `cost-latency.md` | Per-call model, latency, token usage, and estimated cost |
| `judge-feedback.md` | GPT-5.5 blind judge feedback if judge was enabled |
| `comparison-table.md` | Summary table for article drafting |
| `run-metadata.json` | Feature, codebase path, competitors, models, price snapshot |

Recommended review order:

1. Open `ground-truth.json` and correct any obvious missed facts in your notes.
2. Read `control/01-codebase-review.md` and `orchestrated/01-codebase-review.md` side by side.
3. Check `cost-latency.md` for actual latency and cost deltas.
4. Review `deterministic-scores.json` for fake file references and missed grounding.
5. Add your own human review notes before turning the run into article claims.

## Reproducibility Notes

- Every run creates a new timestamped output directory.
- Model outputs are stochastic, so expect some variation between runs.
- Prices in the script are a snapshot; refresh them from OpenRouter before publishing exact cost claims.
- `OPENROUTER_API_KEY` is read from the environment and should never be committed.
- Generated benchmark outputs are ignored by git via `output/benchmark-*/`.

## OpenCode Assets

This repo also includes OpenCode skills and agents that describe the intended workflow:

- `.opencode/agents/pm-orchestrator.md`
- `.opencode/agents/codebase-analyst.md`
- `.opencode/agents/competitive-analyst.md`
- `.opencode/agents/eli5-expert.md`
- `.opencode/agents/ticket-engineer.md`
- `.opencode/agents/prfaq-writer.md`

The benchmark script is the reproducible path. The OpenCode assets are the product-design layer and a prototype of what a native task-governance workflow could look like.

## Article Angle

A useful article should not claim open-source models are universally better. It should show the tradeoff honestly:

> I tested Opus 4.8 against an orchestrated open-source PM workflow on a real codebase. Here is what matched, what failed, how much latency changed, and what OpenRouter could productize as a governance layer.

The most valuable output is not a perfect benchmark. It is the combination of:

- Real model outputs
- Latency and cost measurements
- Deterministic grounding checks
- Human review notes
- A concrete product proposal for OpenRouter
