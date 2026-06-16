---
name: prfaq-writer
description: "Use when you need to write a PRFAQ (Press Release + FAQ) for a feature grounded in an existing codebase. Invoked by the pm-orchestrator agent."
---

# PRFAQ Writer

Produces a PRFAQ document (Amazon Working Backwards format). Depends on competitive-analyst for market intelligence. Decomposes into: press release draft, FAQ generation in parallel, synthesis.

## Sub-task decomposition

```
Orchestrator: "Write a PRFAQ for feature Y"
  │
  ├─ [from competitive-analyst] Competitive research report
  │     Runs competitive-analyst skill first (separate skill, feeds in)
  │
  ├─ Step 1: Draft press release (DeepSeek V4 Flash)
  │     "Using codebase context and competitive research, draft the press release: headline, subheadline, body, leadership quote"
  │
  ├─ Step 2: Identify FAQ topics in parallel (Qwen3 30B)
  │     ├─ worker: "What internal FAQs should we anticipate?"
  │     └─ worker: "What customer FAQs should we anticipate?"
  │     (parallel)
  │
  ├─ Step 3: Write FAQ answers in parallel (Qwen3 8B — one per question)
  │     ├─ worker: "Answer FAQ 1: migration path"
  │     ├─ worker: "Answer FAQ 2: data model changes"  
  │     ├─ worker: "Answer FAQ 3: competitive differentiation"
  │     └─ worker: "Answer FAQ 4: performance impact"
  │     (parallel — each FAQ is independent)
  │
  └─ Step 4: Synthesize final PRFAQ (DeepSeek V4 Flash)
        "Compile everything into the final PRFAQ document. Ensure consistency. Check that all claims reference real code."
```

## Model routing

| Subtask | Model | Why |
|---|---|---|
| Draft press release | deepseek/deepseek-v4-flash | Strategic writing needs reasoning |
| Identify FAQ topics (parallel) | qwen/qwen3-30b-a3b | Light analysis, cheap |
| Write FAQ answers (parallel) | qwen/qwen3-8b | Formulaic Q&A, cheapest |
| Synthesize final | deepseek/deepseek-v4-flash | Needs cross-reference + consistency check |

## Execution pattern

competitive-analyst → Step 1 (sequential) → Step 2 (parallel) → Step 3 (parallel) → Step 4 (sequential).

## Output

A markdown PRFAQ with sections: Press Release, Internal FAQ, Customer FAQ, Technical FAQ. All claims grounded in codebase.

## Output directory

`output/benchmark-[timestamp]/orchestrated/05-prfaq.md`
