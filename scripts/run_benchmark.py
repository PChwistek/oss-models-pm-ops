#!/usr/bin/env python3
"""Benchmark PM workflows across Opus 4.8 and orchestrated OSS models.

This script is intentionally dependency-free. It:
- inspects an arbitrary codebase
- generates deterministic ground-truth checks
- runs a control track with Opus 4.8
- runs an orchestrated track with open-source models
- records latency, token usage, and estimated cost
- writes deterministic scores and an optional GPT-5.5 blind judge report
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import os
import random
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "control": "openai/gpt-5.5",
    "judge": "anthropic/claude-opus-4.8",
    "orchestrator": "deepseek/deepseek-v4-flash",
    "code": "qwen/qwen3-coder-flash",
    "drafting": "qwen/qwen3-30b-a3b",
    "cheap": "qwen/qwen3-8b",
}

# Dollars per 1M tokens. Keep this as an editable snapshot; OpenRouter prices move.
PRICES = {
    "anthropic/claude-opus-4.8": (5.00, 25.00),
    "openai/gpt-5.5": (5.00, 30.00),
    "deepseek/deepseek-v4-flash": (0.098, 0.196),
    "qwen/qwen3-coder-flash": (0.195, 0.975),
    "qwen/qwen3-30b-a3b": (0.12, 0.50),
    "qwen/qwen3-8b": (0.05, 0.40),
}

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    ".turbo",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "target",
    "vendor",
}

TEXT_EXTS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".py",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".kt",
    ".php",
    ".cs",
    ".swift",
    ".sql",
    ".prisma",
    ".graphql",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".css",
    ".scss",
    ".html",
}

IMPORTANT_NAMES = {
    "package.json",
    "pnpm-workspace.yaml",
    "turbo.json",
    "tsconfig.json",
    "next.config.js",
    "next.config.ts",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
}


@dataclasses.dataclass
class FileSnippet:
    path: str
    content: str
    truncated: bool


@dataclasses.dataclass
class Snapshot:
    root: Path
    files: list[str]
    snippets: list[FileSnippet]
    tech_stack: list[str]
    routes: list[str]
    data_models: list[str]
    tests: list[str]
    entrypoints: list[str]


@dataclasses.dataclass
class CallResult:
    task: str
    track: str
    model: str
    content: str
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    error: str | None = None


def read_text(path: Path, max_bytes: int) -> tuple[str, bool]:
    try:
        data = path.read_bytes()
    except OSError:
        return "", False
    truncated = len(data) > max_bytes
    data = data[:max_bytes]
    try:
        return data.decode("utf-8"), truncated
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), truncated


def walk_codebase(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for filename in filenames:
            path = Path(current) / filename
            if filename in IMPORTANT_NAMES or path.suffix in TEXT_EXTS:
                files.append(path)
    return sorted(files, key=lambda p: str(p.relative_to(root)))


def rank_file(root: Path, path: Path) -> tuple[int, str]:
    rel = str(path.relative_to(root))
    name = path.name
    if name in IMPORTANT_NAMES:
        return (0, rel)
    if "schema" in rel.lower() or path.suffix in {".prisma", ".sql"}:
        return (1, rel)
    if "/api/" in f"/{rel}" or "route." in name or "routes" in rel.lower():
        return (2, rel)
    if any(part in rel.lower() for part in ["service", "feature", "model", "component"]):
        return (3, rel)
    if ".test." in rel or ".spec." in rel or "/test" in f"/{rel}".lower():
        return (5, rel)
    return (4, rel)


def parse_package_json(content: str) -> list[str]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    deps: dict[str, Any] = {}
    for key in ["dependencies", "devDependencies", "peerDependencies"]:
        value = parsed.get(key)
        if isinstance(value, dict):
            deps.update(value)
    known = []
    mapping = {
        "next": "Next.js",
        "react": "React",
        "express": "Express",
        "@nestjs/core": "NestJS",
        "prisma": "Prisma",
        "@prisma/client": "Prisma",
        "drizzle-orm": "Drizzle ORM",
        "zod": "Zod",
        "langchain": "LangChain",
        "@langchain/langgraph": "LangGraph",
        "postgres": "PostgreSQL",
        "pg": "PostgreSQL",
        "tailwindcss": "Tailwind CSS",
        "jest": "Jest",
        "vitest": "Vitest",
        "playwright": "Playwright",
        "typescript": "TypeScript",
    }
    for dep, label in mapping.items():
        if dep in deps:
            known.append(label)
    return sorted(set(known))


def infer_tech_stack(root: Path, snippets: list[FileSnippet]) -> list[str]:
    tech: set[str] = set()
    suffixes = {Path(s.path).suffix for s in snippets}
    if suffixes & {".ts", ".tsx"}:
        tech.add("TypeScript")
    if suffixes & {".js", ".jsx", ".mjs", ".cjs"}:
        tech.add("JavaScript")
    if suffixes & {".py"}:
        tech.add("Python")
    if suffixes & {".go"}:
        tech.add("Go")
    if suffixes & {".rs"}:
        tech.add("Rust")
    for snippet in snippets:
        if snippet.path.endswith("package.json"):
            tech.update(parse_package_json(snippet.content))
        if snippet.path.endswith("pyproject.toml"):
            tech.add("Python")
        if snippet.path.endswith("go.mod"):
            tech.add("Go")
        if snippet.path.endswith("Cargo.toml"):
            tech.add("Rust")
        if snippet.path.endswith("schema.prisma"):
            tech.add("Prisma")
    return sorted(tech)


def infer_routes(snippets: list[FileSnippet]) -> list[str]:
    routes: set[str] = set()
    for snippet in snippets:
        path = snippet.path
        content = snippet.content
        if "/api/" in f"/{path}" and re.search(r"export\s+async\s+function\s+(GET|POST|PUT|PATCH|DELETE)", content):
            route_path = path
            route_path = re.sub(r"^.*?/app/api", "/api", route_path)
            route_path = re.sub(r"/route\.[tj]sx?$", "", route_path)
            methods = sorted(set(re.findall(r"export\s+async\s+function\s+(GET|POST|PUT|PATCH|DELETE)", content)))
            routes.add(f"{','.join(methods)} {route_path}")
        for method, route in re.findall(r"(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)", content):
            routes.add(f"{method.upper()} {route} ({path})")
        for method, route in re.findall(r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)", content):
            routes.add(f"{method.upper()} {route} ({path})")
    return sorted(routes)


def infer_data_models(snippets: list[FileSnippet]) -> list[str]:
    models: set[str] = set()
    for snippet in snippets:
        path = snippet.path
        content = snippet.content
        for model in re.findall(r"^\s*model\s+(\w+)\s*\{", content, flags=re.MULTILINE):
            models.add(f"Prisma model {model} ({path})")
        for table in re.findall(r"(?:pgTable|mysqlTable|sqliteTable)\(\s*['\"]([^'\"]+)", content):
            models.add(f"Drizzle table {table} ({path})")
        for schema in re.findall(r"new\s+Schema\s*\(", content):
            models.add(f"Mongoose schema ({path})")
        for zod in re.findall(r"(?:const|export\s+const)\s+(\w+Schema)\s*=\s*z\.object", content):
            models.add(f"Zod schema {zod} ({path})")
    return sorted(models)


def infer_entrypoints(files: list[str]) -> list[str]:
    candidates = []
    names = {
        "src/index.ts",
        "src/index.tsx",
        "src/main.ts",
        "src/app.ts",
        "app.py",
        "main.py",
        "server.js",
        "index.js",
        "cmd/main.go",
    }
    for file in files:
        if file in names or file.endswith("/page.tsx") or file.endswith("/layout.tsx"):
            candidates.append(file)
    return sorted(candidates[:20])


def inspect_codebase(root: Path, max_files: int, max_file_bytes: int) -> Snapshot:
    all_paths = walk_codebase(root)
    ranked = sorted(all_paths, key=lambda p: rank_file(root, p))[:max_files]
    snippets = []
    for path in ranked:
        content, truncated = read_text(path, max_file_bytes)
        snippets.append(FileSnippet(str(path.relative_to(root)), content, truncated))
    files = [str(p.relative_to(root)) for p in all_paths]

    # Use a broader scan for deterministic ground truth than for model context.
    # The model only sees selected snippets; eval extraction should still catch routes
    # and schemas that were not selected for context due to token limits.
    detection_paths = []
    for path in all_paths:
        rel = str(path.relative_to(root)).lower()
        if (
            path.name in IMPORTANT_NAMES
            or "/api/" in f"/{rel}"
            or "route." in rel
            or "routes" in rel
            or "schema" in rel
            or "model" in rel
            or path.suffix in {".prisma", ".sql"}
        ):
            detection_paths.append(path)
    detection_snippets = []
    seen = {s.path for s in snippets}
    for path in detection_paths[:300]:
        rel = str(path.relative_to(root))
        if rel in seen:
            continue
        content, truncated = read_text(path, max_file_bytes)
        detection_snippets.append(FileSnippet(rel, content, truncated))
    eval_snippets = snippets + detection_snippets

    tech_stack = infer_tech_stack(root, eval_snippets)
    routes = infer_routes(eval_snippets)
    data_models = infer_data_models(eval_snippets)
    tests = [f for f in files if re.search(r"(test|spec)\.[tj]sx?$|/tests?/|/spec/", f)]
    entrypoints = infer_entrypoints(files)
    return Snapshot(root, files, snippets, tech_stack, routes, data_models, tests, entrypoints)


def snapshot_to_context(snapshot: Snapshot, max_chars: int = 120_000) -> str:
    parts = [
        f"# Codebase context: {snapshot.root.name}",
        "",
        "## Discovered facts",
        f"- Files indexed: {len(snapshot.files)}",
        f"- Tech stack: {', '.join(snapshot.tech_stack) or 'unknown'}",
        f"- Entry points: {', '.join(snapshot.entrypoints[:10]) or 'unknown'}",
        f"- Routes: {', '.join(snapshot.routes[:20]) or 'none detected'}",
        f"- Data models: {', '.join(snapshot.data_models[:20]) or 'none detected'}",
        f"- Tests: {', '.join(snapshot.tests[:20]) or 'none detected'}",
        "",
        "## Selected files",
    ]
    for snippet in snapshot.snippets:
        label = f"### {snippet.path}"
        if snippet.truncated:
            label += " (truncated)"
        parts.extend([label, "```", snippet.content, "```", ""])
    context = "\n".join(parts)
    if len(context) > max_chars:
        return context[:max_chars] + "\n\n[context truncated]\n"
    return context


def ground_truth(snapshot: Snapshot) -> dict[str, Any]:
    return {
        "codebase": snapshot.root.name,
        "files_indexed": len(snapshot.files),
        "known_files": snapshot.files,
        "tech_stack": snapshot.tech_stack,
        "routes": snapshot.routes,
        "data_models": snapshot.data_models,
        "tests": snapshot.tests,
        "entrypoints": snapshot.entrypoints,
        "checks": {
            "codebase_review": {
                "must_mention_any_tech": snapshot.tech_stack,
                "must_mention_any_routes": snapshot.routes[:10],
                "must_mention_any_models": snapshot.data_models[:10],
            },
            "tickets": {
                "must_reference_real_files": snapshot.files[:80],
            },
            "prfaq": {
                "should_reference_real_capabilities": snapshot.tech_stack + snapshot.routes[:5] + snapshot.data_models[:5],
            },
        },
    }


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = PRICES.get(model, (0.0, 0.0))
    return (prompt_tokens / 1_000_000 * prompt_price) + (completion_tokens / 1_000_000 * completion_price)


def call_openrouter(model: str, messages: list[dict[str, str]], task: str, track: str, dry_run: bool) -> CallResult:
    prompt_text = "\n".join(m.get("content", "") for m in messages)
    if dry_run:
        content = f"[DRY RUN] {track}/{task} would call {model}."
        prompt_tokens = estimate_tokens(prompt_text)
        completion_tokens = estimate_tokens(content)
        return CallResult(task, track, model, content, 0.0, prompt_tokens, completion_tokens, prompt_tokens + completion_tokens, estimate_cost(model, prompt_tokens, completion_tokens))

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required unless --dry-run is set")

    body = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/PChwistek/oss-models-pm-ops",
            "X-OpenRouter-Title": "oss-models-pm-ops",
        },
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        latency = time.perf_counter() - start
        prompt_tokens = estimate_tokens(prompt_text)
        return CallResult(task, track, model, "", latency, prompt_tokens, 0, prompt_tokens, 0.0, f"HTTP {exc.code}: {error_body[:1000]}")
    except Exception as exc:  # noqa: BLE001 - CLI should capture API failures in reports.
        latency = time.perf_counter() - start
        prompt_tokens = estimate_tokens(prompt_text)
        return CallResult(task, track, model, "", latency, prompt_tokens, 0, prompt_tokens, 0.0, str(exc))
    latency = time.perf_counter() - start
    content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = parsed.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or estimate_tokens(prompt_text))
    completion_tokens = int(usage.get("completion_tokens") or estimate_tokens(content))
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    return CallResult(task, track, model, content, latency, prompt_tokens, completion_tokens, total_tokens, estimate_cost(model, prompt_tokens, completion_tokens))


def system_prompt(role: str) -> dict[str, str]:
    return {"role": "system", "content": role}


def user_prompt(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def prompt_codebase_review(context: str) -> str:
    return f"""Analyze this codebase for a product manager.

Return markdown with: architecture, data flow, key modules, tech stack, test coverage, risks, and specific file references.

{context}
"""


def prompt_competitive(context: str, feature: str, competitors: list[str] | None = None) -> str:
    competitor_text = ", ".join(competitors or []) or "infer 3 plausible competitors from the product context"
    return f"""Produce competitive research for this feature: {feature}

Competitors: {competitor_text}

Use this codebase context to understand the product category. Return a comparison matrix, market trends, and differentiation opportunities. Label claims as confirmed, likely, or speculative.

{context[:40_000]}
"""


def prompt_eli5(context: str, feature: str, codebase_review: str | None = None) -> str:
    review = f"\n\nPrior codebase review:\n{codebase_review}" if codebase_review else ""
    return f"""Explain this feature in plain English for an executive audience: {feature}

Include: one-sentence summary, analogy, simple explanation, business impact, tradeoffs, and one technical detail worth knowing. Minimize jargon and ground the explanation in the actual codebase.{review}

{context[:60_000]}
"""


def prompt_tickets(context: str, feature: str, codebase_review: str | None = None) -> str:
    review = f"\n\nPrior codebase review:\n{codebase_review}" if codebase_review else ""
    return f"""Generate 3-7 engineering tickets for this feature: {feature}

Each ticket must reference real files or modules from the codebase and include acceptance criteria, dependencies, and complexity. Avoid generic tickets.{review}

{context[:70_000]}
"""


def prompt_prfaq(context: str, feature: str, codebase_review: str | None = None, competitive: str | None = None) -> str:
    prior = ""
    if codebase_review:
        prior += f"\n\nCodebase review:\n{codebase_review}"
    if competitive:
        prior += f"\n\nCompetitive research:\n{competitive}"
    return f"""Write a PRFAQ for this feature: {feature}

Use Amazon Working Backwards format. Include Press Release, Internal FAQ, Customer FAQ, and Technical FAQ. Ground technical answers in real files, APIs, routes, schemas, or modules from the codebase. Do not fabricate implementation details.{prior}

{context[:70_000]}
"""


def run_control(context: str, feature: str, competitors: list[str] | None, dry_run: bool) -> tuple[dict[str, str], list[CallResult]]:
    tasks = {
        "01-codebase-review": prompt_codebase_review(context),
        "02-competitive-research": prompt_competitive(context, feature, competitors),
        "03-eli5": prompt_eli5(context, feature),
        "04-tickets": prompt_tickets(context, feature),
        "05-prfaq": prompt_prfaq(context, feature),
    }
    outputs: dict[str, str] = {}
    calls: list[CallResult] = []
    for task, prompt in tasks.items():
        result = call_openrouter(
            MODELS["control"],
            [system_prompt("You are an expert product manager and senior technical product thinker."), user_prompt(prompt)],
            task,
            "control",
            dry_run,
        )
        calls.append(result)
        outputs[task] = result.content or f"ERROR: {result.error}"
    return outputs, calls


def summarize_file(snippet: FileSnippet, dry_run: bool) -> CallResult:
    prompt = f"""Summarize this source file for a PM-oriented codebase review.

Return: purpose, key exports/functions, data flow relevance, risks, and notable dependencies.

File: {snippet.path}

```
{snippet.content[:10_000]}
```
"""
    return call_openrouter(MODELS["code"], [system_prompt("You are a concise codebase analyst."), user_prompt(prompt)], f"file-summary:{snippet.path}", "orchestrated", dry_run)


def run_parallel(items: list[Any], fn, max_workers: int) -> list[Any]:
    if not items:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(fn, items))


def run_orchestrated(snapshot: Snapshot, context: str, feature: str, competitors: list[str] | None, dry_run: bool) -> tuple[dict[str, str], list[CallResult]]:
    outputs: dict[str, str] = {}
    calls: list[CallResult] = []

    # Codebase review: parallel file summaries, then synthesize.
    file_summary_calls = run_parallel(snapshot.snippets[:12], lambda s: summarize_file(s, dry_run), max_workers=4)
    calls.extend(file_summary_calls)
    file_summaries = "\n\n".join(f"## {c.task}\n{c.content or 'ERROR: ' + str(c.error)}" for c in file_summary_calls)
    synth_prompt = f"""Synthesize these file summaries into a PM-friendly codebase review.

Also use these discovered facts:
- Tech stack: {', '.join(snapshot.tech_stack)}
- Routes: {', '.join(snapshot.routes[:20])}
- Data models: {', '.join(snapshot.data_models[:20])}
- Tests: {', '.join(snapshot.tests[:20])}

{file_summaries}
"""
    result = call_openrouter(MODELS["orchestrator"], [system_prompt("You synthesize codebase intelligence for PMs."), user_prompt(synth_prompt)], "01-codebase-review", "orchestrated", dry_run)
    calls.append(result)
    outputs["01-codebase-review"] = result.content or f"ERROR: {result.error}"

    # Competitive research. If competitors are provided, fan out per competitor. Otherwise infer in one pass.
    comp_list = competitors or ["Competitor A", "Competitor B", "Competitor C"]
    def research_competitor(name: str) -> CallResult:
        prompt = f"Research {name} for this feature area: {feature}. Return pricing, positioning, target customer, strengths, weaknesses, and confidence labels. If the competitor name is generic, infer a plausible competitor from the codebase context.\n\n{context[:20_000]}"
        return call_openrouter(MODELS["cheap"], [system_prompt("You are a pragmatic competitive research assistant."), user_prompt(prompt)], f"competitor:{name}", "orchestrated", dry_run)

    competitor_calls = run_parallel(comp_list[:5], research_competitor, max_workers=min(5, len(comp_list)))
    calls.extend(competitor_calls)
    competitor_notes = "\n\n".join(f"## {c.task}\n{c.content or 'ERROR: ' + str(c.error)}" for c in competitor_calls)
    market_prompt = f"""Synthesize this competitive research for feature: {feature}

Return a comparison matrix, market trends, and differentiation opportunities. Separate confirmed facts from likely/speculative claims.

{competitor_notes}
"""
    result = call_openrouter(MODELS["orchestrator"], [system_prompt("You synthesize market intelligence for product strategy."), user_prompt(market_prompt)], "02-competitive-research", "orchestrated", dry_run)
    calls.append(result)
    outputs["02-competitive-research"] = result.content or f"ERROR: {result.error}"

    # ELI5.
    essence = call_openrouter(MODELS["code"], [system_prompt("You extract technical essence from code context."), user_prompt(prompt_eli5(context, feature, outputs["01-codebase-review"]))], "eli5:technical-essence", "orchestrated", dry_run)
    calls.append(essence)
    analogy = call_openrouter(MODELS["drafting"], [system_prompt("You write crisp product explanations."), user_prompt(f"Draft an ELI5 explanation using this technical essence.\n\n{essence.content}")], "eli5:draft", "orchestrated", dry_run)
    calls.append(analogy)
    review = call_openrouter(MODELS["orchestrator"], [system_prompt("You review explanations for accuracy and clarity."), user_prompt(f"Quality check and improve this ELI5.\n\n{analogy.content}")], "03-eli5", "orchestrated", dry_run)
    calls.append(review)
    outputs["03-eli5"] = review.content or f"ERROR: {review.error}"

    # Tickets.
    module_prompt = f"Identify the modules/files that would likely change for feature: {feature}. Use only real files from this codebase.\n\n{outputs['01-codebase-review']}"
    modules = call_openrouter(MODELS["code"], [system_prompt("You map features to implementation areas."), user_prompt(module_prompt)], "tickets:modules", "orchestrated", dry_run)
    calls.append(modules)
    ticket_prompt = f"Draft 3-7 tickets for feature: {feature}. Reference only real files. Use this module analysis:\n\n{modules.content}\n\nCodebase facts:\n{json.dumps(ground_truth(snapshot), indent=2)[:30_000]}"
    tickets = call_openrouter(MODELS["cheap"], [system_prompt("You draft concise engineering tickets."), user_prompt(ticket_prompt)], "tickets:draft", "orchestrated", dry_run)
    calls.append(tickets)
    ticket_review = call_openrouter(MODELS["orchestrator"], [system_prompt("You review tickets for gaps, dependencies, and hallucinations."), user_prompt(f"Review and improve these tickets. Remove fake files/APIs.\n\n{tickets.content}")], "04-tickets", "orchestrated", dry_run)
    calls.append(ticket_review)
    outputs["04-tickets"] = ticket_review.content or f"ERROR: {ticket_review.error}"

    # PRFAQ.
    faq_topics = call_openrouter(MODELS["drafting"], [system_prompt("You identify stakeholder questions for PRFAQs."), user_prompt(f"Identify customer, internal, and technical FAQ questions for feature: {feature}.\n\nCodebase review:\n{outputs['01-codebase-review']}\n\nCompetitive research:\n{outputs['02-competitive-research']}")], "prfaq:faq-topics", "orchestrated", dry_run)
    calls.append(faq_topics)
    prfaq = call_openrouter(MODELS["orchestrator"], [system_prompt("You write code-grounded PRFAQs."), user_prompt(prompt_prfaq(context, feature, outputs["01-codebase-review"], outputs["02-competitive-research"] + "\n\nFAQ topics:\n" + faq_topics.content))], "05-prfaq", "orchestrated", dry_run)
    calls.append(prfaq)
    outputs["05-prfaq"] = prfaq.content or f"ERROR: {prfaq.error}"

    return outputs, calls


FILE_REF_RE = re.compile(r"[\w./-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|rb|java|kt|php|cs|swift|sql|prisma|json|yaml|yml|toml)")


def score_output(output: str, truth: dict[str, Any]) -> dict[str, Any]:
    lower = output.lower()
    tech_hits = [t for t in truth["tech_stack"] if t.lower() in lower]
    route_hits = [r for r in truth["routes"] if r.split(" ", 1)[-1].split(" (")[0].lower() in lower]
    model_hits = []
    for model in truth["data_models"]:
        parts = model.split(" ")
        if len(parts) > 2 and parts[2].lower() in lower:
            model_hits.append(model)
    known_files = set(truth["known_files"])
    mentioned_files = sorted(set(FILE_REF_RE.findall(output)))
    real_files = [f for f in mentioned_files if f in known_files]
    fake_files = [f for f in mentioned_files if f not in known_files]
    possible = max(1, min(5, len(truth["tech_stack"])) + min(5, len(truth["routes"])) + min(5, len(truth["data_models"])) + 3)
    raw = min(5, len(tech_hits)) + min(5, len(route_hits)) + min(5, len(model_hits)) + min(3, len(real_files))
    penalty = min(20, len(fake_files) * 4)
    score = max(0, round((raw / possible) * 100 - penalty, 1))
    return {
        "score": score,
        "tech_hits": tech_hits,
        "route_hits": route_hits[:10],
        "model_hits": model_hits[:10],
        "real_file_refs": real_files[:20],
        "suspected_fake_file_refs": fake_files[:20],
    }


def deterministic_scores(outputs: dict[str, dict[str, str]], truth: dict[str, Any]) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    for track, track_outputs in outputs.items():
        scores[track] = {}
        for task, output in track_outputs.items():
            scores[track][task] = score_output(output, truth)
    return scores


def judge_outputs(control: dict[str, str], orchestrated: dict[str, str], feature: str, dry_run: bool, skip_judge: bool) -> tuple[str, list[CallResult]]:
    if skip_judge:
        return "GPT-5.5 judge skipped.", []
    random.seed(42)
    calls: list[CallResult] = []
    reports = []
    for task in sorted(control):
        pair = [("A", control[task]), ("B", orchestrated[task])]
        random.shuffle(pair)
        label_map = {label: "control" if content == control[task] else "orchestrated" for label, content in pair}
        prompt = f"""You are an impartial evaluator. Compare two outputs for the same PM workflow task.

Task: {task}
Feature: {feature}

Score each output from 0-100 on technical accuracy, actionability, clarity, completeness, and hallucination risk. Return markdown with a concise explanation and a winner. Do not assume either model is better.

Output {pair[0][0]}:
{pair[0][1]}

Output {pair[1][0]}:
{pair[1][1]}
"""
        result = call_openrouter(MODELS["judge"], [system_prompt("You are a strict but fair model-output evaluator."), user_prompt(prompt)], f"judge:{task}", "judge", dry_run)
        calls.append(result)
        reports.append(f"# Judge report: {task}\n\nBlind mapping: {json.dumps(label_map)}\n\n{result.content or 'ERROR: ' + str(result.error)}")
    return "\n\n---\n\n".join(reports), calls


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def call_table(calls: list[CallResult]) -> str:
    lines = ["| Track | Task | Model | Latency (s) | Prompt tok | Completion tok | Cost | Error |", "|---|---|---|---:|---:|---:|---:|---|"]
    for call in calls:
        err = (call.error or "").replace("|", "\\|")[:120]
        lines.append(f"| {call.track} | {call.task} | `{call.model}` | {call.latency_seconds:.2f} | {call.prompt_tokens} | {call.completion_tokens} | ${call.estimated_cost_usd:.4f} | {err} |")
    return "\n".join(lines)


def comparison_summary(calls: list[CallResult], scores: dict[str, Any]) -> str:
    by_track: dict[str, dict[str, float]] = {}
    for call in calls:
        bucket = by_track.setdefault(call.track, {"cost": 0.0, "latency": 0.0, "calls": 0})
        bucket["cost"] += call.estimated_cost_usd
        bucket["latency"] += call.latency_seconds
        bucket["calls"] += 1
    lines = ["# Benchmark summary", "", "## Cost and latency", "", "| Track | Calls | Total latency (s) | Estimated cost |", "|---|---:|---:|---:|"]
    for track, values in sorted(by_track.items()):
        lines.append(f"| {track} | {int(values['calls'])} | {values['latency']:.2f} | ${values['cost']:.4f} |")
    lines.extend(["", "## Deterministic scores", "", "| Track | Task | Score | Fake file refs |", "|---|---|---:|---:|"])
    for track, task_scores in scores.items():
        for task, data in task_scores.items():
            lines.append(f"| {track} | {task} | {data['score']} | {len(data['suspected_fake_file_refs'])} |")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OSS PM workflow benchmark")
    parser.add_argument("codebase", type=Path, help="Path to codebase to benchmark against")
    parser.add_argument("--feature", required=True, help="Feature to evaluate, e.g. 'AI-powered meal planning'")
    parser.add_argument("--competitors", default="", help="Comma-separated competitors for competitive research")
    parser.add_argument("--out", type=Path, default=Path("output"), help="Output directory root")
    parser.add_argument("--max-files", type=int, default=24, help="Max files to include in codebase context")
    parser.add_argument("--max-file-bytes", type=int, default=12_000, help="Max bytes per selected file")
    parser.add_argument("--dry-run", action="store_true", help="Do not call OpenRouter; write prompts and structure only")
    parser.add_argument("--skip-judge", action="store_true", help="Skip GPT-5.5 judge calls")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = args.codebase.resolve()
    if not root.exists() or not root.is_dir():
        print(f"Codebase path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = args.out / f"benchmark-{timestamp}"
    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()] or None

    snapshot = inspect_codebase(root, args.max_files, args.max_file_bytes)
    truth = ground_truth(snapshot)
    context = snapshot_to_context(snapshot)

    write_text(out_dir / "ground-truth.json", json.dumps(truth, indent=2))
    write_text(out_dir / "codebase-context.md", context)

    control_outputs, control_calls = run_control(context, args.feature, competitors, args.dry_run)
    orchestrated_outputs, orchestrated_calls = run_orchestrated(snapshot, context, args.feature, competitors, args.dry_run)

    for task, content in control_outputs.items():
        write_text(out_dir / "control" / f"{task}.md", content)
    for task, content in orchestrated_outputs.items():
        write_text(out_dir / "orchestrated" / f"{task}.md", content)

    scores = deterministic_scores({"control": control_outputs, "orchestrated": orchestrated_outputs}, truth)
    write_text(out_dir / "deterministic-scores.json", json.dumps(scores, indent=2))
    write_text(out_dir / "deterministic-scores.md", comparison_summary(control_calls + orchestrated_calls, scores))

    judge_report, judge_calls = judge_outputs(control_outputs, orchestrated_outputs, args.feature, args.dry_run, args.skip_judge)
    write_text(out_dir / "judge-feedback.md", judge_report)

    all_calls = control_calls + orchestrated_calls + judge_calls
    write_text(out_dir / "cost-latency.md", call_table(all_calls))
    write_text(out_dir / "comparison-table.md", comparison_summary(all_calls, scores))
    write_text(out_dir / "run-metadata.json", json.dumps({
        "codebase": str(root),
        "feature": args.feature,
        "competitors": competitors,
        "dry_run": args.dry_run,
        "skip_judge": args.skip_judge,
        "models": MODELS,
        "prices_per_1m_tokens": PRICES,
    }, indent=2))

    print(f"Benchmark output written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
