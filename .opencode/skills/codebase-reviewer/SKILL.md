---
name: codebase-reviewer
description: "Use when you need to analyze a codebase and produce a PM-friendly summary of architecture, data flow, key modules, risks, and tech stack. Invoked by the pm-orchestrator agent to delegate code understanding."
---

# Codebase Reviewer

Analyzes a source code directory and produces a structured architectural summary for product managers. Decomposes into parallel file reading, then synthesizes.

## Sub-task decomposition

```
Orchestrator: "Review the codebase at path X"
  │
  ├─ Step 1: Discover structure (orchestrator itself)
  │     "List directory tree depth 2, identify entry points"
  │
  ├─ Step 2: Read files in parallel (Qwen3 30B or Coder Flash — one call per file/batch)
  │     ├─ worker: "Read src/api/routes.ts" 
  │     ├─ worker: "Read src/models/user.ts"
  │     ├─ worker: "Read src/services/payment.ts"
  │     └─ worker: "Read src/utils/helpers.ts"
  │     (all parallel via OpenRouter API calls)
  │
  ├─ Step 3: Synthesize architecture (DeepSeek V4 Flash)
  │     "Given these file summaries, describe the architecture pattern, data flow, and key modules"
  │
  └─ Step 4: Identify risks (DeepSeek V4 Flash)
        "From the architecture, what are the top 3 risks a PM should know about?"
```

## Model routing

| Subtask | Model | Why |
|---|---|---|
| Discover structure | Orchestrator itself | Cheap planning |
| Read files (parallel) | qwen/qwen3-coder-flash | Best code understanding, can go deep on each file |
| Synthesize architecture | deepseek/deepseek-v4-flash | Strong reasoning to connect patterns |
| Identify risks | deepseek/deepseek-v4-flash | Needs critical thinking |

## Execution pattern

Use bash+curl to call OpenRouter API for parallel file reads. Collect results, then pass to synthesis step.

## Output

A structured report covering: architecture pattern, data flow, key modules, tech stack, test coverage, risks.

## Output directory structure: output/benchmark-[timestamp]/orchestrated/01-codebase-review.md", "filePath": "/Users/philipchwistek/coding/openrouter_tests/pm-workflow-benchmark/.opencode/skills/codebase-reviewer/SKILL.md"}