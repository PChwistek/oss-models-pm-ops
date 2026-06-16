---
name: ticket-generator
description: "Use when you need to generate structured engineering tickets from codebase context and a feature description. Each ticket references real files and patterns. Invoked by the pm-orchestrator agent."
---

# Ticket Generator

Produces structured, code-grounded engineering tickets. Decomposes into: understand feature scope, identify affected modules, draft tickets in parallel, review.

## Sub-task decomposition

```
Orchestrator: "Generate tickets for feature Y"
  │
  ├─ Step 1: Understand feature scope (Orchestrator itself)
  │     "Given the codebase review and feature description, what modules need to change?"
  │
  ├─ Step 2: Identify affected modules in parallel (Qwen3 Coder Flash)
  │     ├─ worker: "What changes are needed in module A for feature Y?"
  │     ├─ worker: "What changes are needed in module B for feature Y?"
  │     └─ worker: "What new module C needs to be created?"
  │     (parallel — each focuses on one area)
  │
  ├─ Step 3: Draft tickets in parallel (Qwen3 8B — one per ticket)
  │     ├─ worker: "Write ticket 1: implement X in module A"  
  │     ├─ worker: "Write ticket 2: add API endpoint for Y"
  │     ├─ worker: "Write ticket 3: add data model for Z"
  │     └─ worker: "Write ticket 4: write tests for feature Y"
  │     (parallel — each ticket is independent)
  │
  └─ Step 4: Review and link (DeepSeek V4 Flash)
        "Review all tickets. Check for gaps, overlaps, missing dependencies. Link them."
```

## Model routing

| Subtask | Model | Why |
|---|---|---|
| Understand scope | Orchestrator | Cheap planning |
| Identify modules (parallel) | qwen/qwen3-coder-flash | Code understanding per module |
| Draft tickets (parallel) | qwen/qwen3-8b | Cheapest model, tickets are formulaic |
| Review and link | deepseek/deepseek-v4-flash | Needs synthesis and dependency reasoning |

## Execution pattern

Step 1 (sequential) → Step 2 (parallel OpenRouter calls) → Step 3 (parallel OpenRouter calls) → Step 4 (sequential).

## Output

Structured tickets (3-7) each with: title, area/file ref, technical context from codebase, acceptance criteria, dependencies, complexity. All tickets reference real files.

## Output directory

`output/benchmark-[timestamp]/orchestrated/04-tickets.md`
