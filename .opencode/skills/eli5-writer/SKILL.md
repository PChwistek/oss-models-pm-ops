---
name: eli5-writer
description: "Use when you need to explain a technical feature or implementation in plain English for executives, stakeholders, or non-technical team members. Invoked by the pm-orchestrator agent."
---

# ELI5 Writer

Translates complex technical implementations into plain-English explanations. Decomposes into: extract technical facts, draft analogy, write explanation, quality check.

## Sub-task decomposition

```
Orchestrator: "Explain feature X in plain English"
  │
  ├─ Step 1: Extract technical essence (Qwen3 Coder Flash)
  │     "Read the feature code. What does it do technically? What are the key abstractions and data flow?"
  │
  ├─ Step 2: Draft analogy (Qwen3 30B)
  │     "Given these technical details, draft a real-world analogy that maps cleanly to the technical concepts"
  │
  ├─ Step 3: Write ELI5 (Qwen3 30B)
  │     "Using the technical summary and analogy, write the full ELI5: one-liner, analogy, simple explanation, business impact, tradeoffs"
  │
  └─ Step 4: Quality check (DeepSeek V4 Flash)
        "Review this ELI5. Is it technically accurate? Does the analogy hold? Is jargon minimized?"
```

## Model routing

| Subtask | Model | Why |
|---|---|---|
| Extract technical essence | qwen/qwen3-coder-flash | Code understanding |
| Draft analogy | qwen/qwen3-30b-a3b | Creative task, cheap |
| Write ELI5 | qwen/qwen3-30b-a3b | Text generation, cheap |
| Quality check | deepseek/deepseek-v4-flash | Needs accuracy verification |

## Execution pattern

Sequential (each step depends on previous), but each step is a single OpenRouter API call. No parallelism here.

## Output

A markdown ELI5 document with: one-sentence summary, analogy, how it works, business impact, tradeoffs.

## Output directory: output/benchmark-[timestamp]/orchestrated/02-eli5.md", "filePath": "/Users/philipchwistek/coding/openrouter_tests/pm-workflow-benchmark/.opencode/skills/eli5-writer/SKILL.md"}