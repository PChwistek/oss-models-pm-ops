---
name: competitive-analyst
description: "Use when you need to research competitors and produce structured intelligence. Invoked by pm-orchestrator. Feeds into prfaq-writer, ticket-engineer, and strategy decisions."
---

# Competitive Research

Researches competitors and produces structured intelligence. Decomposes into: identify dimensions, research each competitor in parallel, research market trends, synthesize comparison matrix.

## Sub-task decomposition

```
Orchestrator: "Research competitors for feature Y in market X"
  │
  ├─ Step 1: Identify research dimensions (Orchestrator itself)
  │     "What dimensions matter? Pricing, positioning, target customer, key features, strengths, weaknesses."
  │
  ├─ Step 2: Research each competitor in parallel (Qwen3 8B — one per competitor)
  │     ├─ worker: "Research Competitor A: pricing, positioning, strengths, weaknesses"
  │     ├─ worker: "Research Competitor B: pricing, positioning, strengths, weaknesses"
  │     └─ worker: "Research Competitor C: pricing, positioning, strengths, weaknesses"
  │     (parallel — each is independent)
  │
  ├─ Step 3: Research market trends (Qwen3 30B)
  │     "What are the broader market trends affecting this space? Growth rates, consolidation, emerging patterns."
  │
  └─ Step 4: Synthesize comparison matrix (DeepSeek V4 Flash)
        "Given competitor data + trends, produce a structured comparison. Highlight where feature Y would differentiate."
```

## Model routing

| Subtask | Model | Why |
|---|---|---|
| Identify dimensions | Orchestrator | Cheap planning |
| Research per competitor (parallel) | qwen/qwen3-8b | Simple web research, max parallelism |
| Market trends | qwen/qwen3-30b-a3b | Needs synthesis across multiple sources |
| Synthesize matrix | deepseek/deepseek-v4-flash | Needs comparative reasoning + strategic insight |

## Output format

```markdown
## Competitive Analysis: [Feature/Market]

### Comparison Matrix

| Dimension | Competitor A | Competitor B | Competitor C | Our opportunity |
|---|---|---|---|---|
| Pricing | | | | |
| Target customer | | | | |
| Key strength | | | | |
| Key weakness | | | | |

### Market trends

[2-3 paragraph summary of market dynamics]

### Differentiation opportunities

1. Opportunity one (grounded in competitor gaps)
2. Opportunity two
3. Opportunity three
```

## Output directory: output/benchmark-[timestamp]/orchestrated/02-competitive-research.md