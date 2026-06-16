---
name: pm-workflow-benchmark
description: "Benchmark comparing GPT-5.5 (end-to-end) vs orchestrated open-source models on PM tasks. Dynamically generates eval ground truths from any codebase. Uses Claude Opus 4.8 as blind judge."
---

# PM Workflow Benchmark

Runs a controlled experiment comparing two approaches to PM work from any codebase. Dynamically generates evaluation ground truths from the codebase itself, then scores both tracks against them.

For reproducible results, use the executable harness:

```bash
python3 scripts/run_benchmark.py <codebase-path> --feature "<feature-description>"
```

The OpenCode skill describes the intended workflow. The script is the source of truth for latency, cost, and deterministic scoring.

## Invocation

```
/benchmark <codebase-path> --feature "<feature-description>"
```

## How it works

### Phase 0: Codebase analysis and eval generation

Before the benchmark runs, the system analyzes the target codebase to generate ground-truth checkables:

1. **Discover structure**: directory tree, entry points, config files
2. **Extract ground truths**:
   - Tech stack (frameworks, languages, databases, ORMs)
   - API routes (HTTP methods, paths, request/response shapes)
   - Data models (schemas, entities, relationships, fields)
   - Test coverage (test files, what they test, patterns)
   - Key modules and their responsibilities
   - Architecture patterns
3. **Generate eval items**: a JSON file of checkable facts that any correct output must match:

```json
{
  "codebase_review": {
    "must_mention": ["tech stack items", "route count", "ORM used"],
    "must_not_hallucinate": ["non-existent frameworks", "fake routes"]
  },
  "eli5": {
    "must_correctly_explain": ["core data flow", "key abstraction"]
  },
  "tickets": {
    "must_reference_files": ["specific source files"],
    "must_not_reference": ["non-existent files"]
  },
  "prfaq": {
    "must_reference": ["real data models", "real APIs"],
    "must_not_fabricate": ["features not implied by codebase"]
  }
}
```

### Phase 1: Run control track (GPT-5.5)

```
Task 1: Codebase Review  → Single GPT-5.5 call: "Analyze this codebase"
Task 2: Competitive Research  → Single GPT-5.5 call: "Research competitors for [feature]"
Task 3: ELI5             → Single GPT-5.5 call: "Explain [feature] in plain English"
Task 4: Tickets          → Single GPT-5.5 call: "Generate tickets for [feature]"
Task 5: PRFAQ            → Single GPT-5.5 call: "Write a PRFAQ for [feature]"
```

### Phase 2: Run orchestrated track (open-source models)

| Skill | Model | Subtasks | Parallelism | Est. cost |
|---|---|---|---|---|
| codebase-reviewer | Qwen3 Coder Flash + DeepSeek V4 Flash | discover → parallel reads → synthesize → risks | Yes (file reads) | ~$0.015 |
| competitive-analyst | Qwen3 8B + Qwen3 30B + DeepSeek V4 Flash | dimensions → parallel research → trends → matrix | Yes (per competitor) | ~$0.008 |
| eli5-writer | Qwen3 Coder Flash + Qwen3 30B + DeepSeek V4 Flash | extract tech → analogy → write → quality check | No (sequential) | ~$0.012 |
| ticket-generator | Qwen3 Coder Flash + Qwen3 8B + DeepSeek V4 Flash | scope → parallel modules → parallel tickets → link | Yes (both phases) | ~$0.015 |
| prfaq-writer | DeepSeek V4 Flash + Qwen3 30B + Qwen3 8B | (uses competitive output) → PR → parallel FAQs → synthesize | Yes (FAQ phases) | ~$0.012 |

### Phase 3: Judge (GPT-5.5 + deterministic checks)

Two scoring layers:

**A) Deterministic checks** (auto-scored against ground truth):

| Check | What it verifies |
|---|---|
| File references | Does the output mention real files from the codebase? |
| Tech stack accuracy | Are listed technologies actually in use? |
| Route/model accuracy | Are described endpoints and schemas real? |
| Hallucination count | How many non-existent files, APIs, or features? |

**B) Subjective rubric** (Opus 4.8 blind judge):

| Criterion | Weight | Definition |
|---|---|---|
| Technical accuracy | 30% | Correctly reflects the actual codebase |
| Actionability | 25% | Can a PM act on this? Specific and concrete |
| Clarity | 20% | Well-structured for the target audience |
| Completeness | 15% | No obvious gaps |
| Hallucination rate | 10% | Fabricated content |

### Output structure

```
output/benchmark-<timestamp>/
├── ground-truth.json              ← Dynamically generated eval items
├── control/
│   ├── 01-codebase-review.md
│   ├── 02-competitive-research.md
│   ├── 03-eli5.md
│   ├── 04-tickets.md
│   └── 05-prfaq.md
├── orchestrated/
│   ├── 01-codebase-review.md
│   ├── 02-competitive-research.md
│   ├── 03-eli5.md
│   ├── 04-tickets.md
│   └── 05-prfaq.md
├── deterministic-scores.md
├── judge-feedback.md
└── comparison-table.md
```

### Comparison table format

```
+--------------------+---------+--------------+----------+
| Criterion          | GPT-5.5 | Orchestrated | Delta    |
+--------------------+---------+--------------+----------+
| Technical accuracy | 94      | 86           | -8       |
| Actionability      | 91      | 83           | -8       |
| Clarity            | 95      | 88           | -7       |
| Completeness       | 90      | 85           | -5       |
| Hallucination rate | 98      | 90           | -8       |
+--------------------+---------+--------------+----------+
| Overall (weighted) | 93.2    | 85.8         | -7.4     |
| Est. cost          | $1.42   | $0.06        | 24x less |
+--------------------+---------+--------------+----------+
```
