"""Synthetic session data for demo mode — no real user data."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .models import SessionSummary

_PROJECTS = [
    ("webapp/frontend", "frontend"),
    ("webapp/backend", "backend"),
    ("infra/deploy", "deploy"),
    ("libs/auth", "auth"),
    ("docs/api-reference", "api-reference"),
    ("ml/training-pipeline", "training-pipeline"),
    ("mobile/ios-app", "ios-app"),
    ("tools/cli-utils", "cli-utils"),
]

_PROMPTS = {
    "coding": [
        "Add rate limiting middleware to the Express API endpoints",
        "Refactor the authentication module to use JWT instead of session cookies",
        "Fix the race condition in the WebSocket connection handler",
        "Write unit tests for the new payment processing service",
        "Implement pagination for the /users endpoint with cursor-based navigation",
        "Debug why the Docker container fails to start on ARM64",
        "Add TypeScript types for the REST API response objects",
        "Optimize the database query that's causing N+1 selects on the dashboard",
        "Create a CLI tool that generates migration files from schema changes",
        "Implement retry logic with exponential backoff for the S3 upload service",
    ],
    "research": [
        "Search for papers on transformer attention mechanisms published after 2024",
        "Compare RLHF vs DPO training approaches for our use case",
        "Analyze the benchmark results from the latest fine-tuning run",
        "Summarize the key findings from the distillation experiments",
        "Review the ablation study results and identify the best hyperparameters",
    ],
    "writing": [
        "Draft the architecture decision record for migrating to event sourcing",
        "Write the onboarding guide for new contributors to the project",
        "Update the API documentation to reflect the v3 breaking changes",
        "Create a runbook for the database failover procedure",
        "Write a post-mortem for the production incident last Thursday",
    ],
    "ops": [
        "Set up the CI/CD pipeline for the new microservice",
        "Configure Terraform modules for the staging environment",
        "Debug why the health check is failing on the load balancer",
        "Set up log aggregation with structured JSON logging",
        "Automate the certificate rotation process for the API gateway",
    ],
    "data": [
        "Build an ETL pipeline to ingest data from the new vendor API",
        "Write SQL queries to generate the monthly analytics report",
        "Clean and normalize the customer dataset for the ML training job",
        "Create a data validation pipeline with Great Expectations",
    ],
}

_APPROVAL_PROMPTS = [
    "yes, go ahead",
    "looks good, commit it",
    "perfect, let's ship it",
    "do it",
    "yes that's exactly right",
]

_CORRECTION_PROMPTS = [
    "no, actually use the async version instead",
    "wrong approach — we need to handle the edge case first",
    "don't use that library, it's deprecated",
    "actually, let's refactor this differently",
    "instead of a class, make it a simple function",
]

_BRANCHES = [
    "main", "main", "main",
    "feat/auth-refactor",
    "feat/rate-limiting",
    "fix/websocket-race",
    "feat/pagination",
    "chore/ci-pipeline",
    "feat/etl-pipeline",
    "docs/api-v3",
    "fix/docker-arm64",
    "feat/payment-service",
    "experiment/distillation",
]

_MODELS = [
    "claude-sonnet-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-opus-4-5",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]

_TOOLS = [
    ("Read", 35), ("Bash", 28), ("Edit", 22), ("Write", 18), ("Grep", 15),
    ("Glob", 12), ("Task", 8), ("WebFetch", 5), ("AskUserQuestion", 3),
]

_TOPIC_MAP = {
    "coding": ["version-control", "observability"],
    "research": ["experimentation", "continual-learning"],
    "writing": ["communication"],
    "ops": ["observability", "training-infra"],
    "data": ["exploration", "taxonomy"],
}

_SLUGS = [
    "keen-leaping-fountain", "bright-dancing-meadow", "swift-flowing-river",
    "calm-silver-mountain", "bold-crimson-falcon", "quiet-amber-forest",
    "warm-golden-sunrise", "cool-sapphire-lake", "wild-emerald-valley",
    "deep-violet-horizon", "soft-copper-twilight", "pure-crystal-stream",
    "free-scarlet-phoenix", "dark-cobalt-thunder", "light-ivory-breeze",
    "sharp-jade-arrow", "still-onyx-shadow", "vast-pearl-ocean",
    "true-coral-beacon", "raw-slate-whisper", "brave-teal-summit",
    "fair-bronze-echo", "fine-ruby-spark", "lone-azure-drift",
]


def generate_demo_sessions(count: int = 42) -> list[SessionSummary]:
    """Generate synthetic sessions for demo/screenshot purposes."""
    random.seed(2026)
    now = datetime.now(timezone.utc)
    sessions: list[SessionSummary] = []

    for i in range(count):
        project_path, project_short = random.choice(_PROJECTS)
        domain = random.choice(list(_PROMPTS.keys()))
        prompts_pool = _PROMPTS[domain]

        first_prompt = random.choice(prompts_pool)
        num_prompts = random.randint(3, 20)
        human_prompts = [first_prompt]

        for _ in range(num_prompts - 1):
            roll = random.random()
            if roll < 0.2:
                human_prompts.append(random.choice(_APPROVAL_PROMPTS))
            elif roll < 0.3:
                human_prompts.append(random.choice(_CORRECTION_PROMPTS))
            else:
                human_prompts.append(random.choice(prompts_pool))

        # Timestamps spread over the last 14 days
        hours_ago = random.uniform(0.5, 14 * 24)
        started = now - timedelta(hours=hours_ago)
        duration = random.uniform(5, 180)
        ended = started + timedelta(minutes=duration)

        # Tools
        num_tools = random.randint(3, 7)
        selected_tools = random.sample(_TOOLS, num_tools)
        tool_counts = [(t, random.randint(1, c)) for t, c in selected_tools]
        total_tool_calls = sum(c for _, c in tool_counts)

        # Topics
        topics = list(_TOPIC_MAP.get(domain, []))
        if random.random() > 0.5:
            topics.append("agents")
        topics = sorted(set(topics))

        # Trust signals
        approvals = sum(1 for p in human_prompts if any(kw in p.lower() for kw in ["yes", "go ahead", "looks good", "perfect", "do it"]))
        corrections = sum(1 for p in human_prompts if any(kw in p.lower() for kw in ["no,", "actually", "wrong", "don't", "instead"]))

        model = random.choice(_MODELS)
        branch = random.choice(_BRANCHES)
        slug = _SLUGS[i % len(_SLUGS)]
        is_active = i < 3  # first 3 are "active"

        sessions.append(SessionSummary(
            session_id=f"{i:08x}-demo-{slug[:8]}-{random.randint(1000,9999)}",
            project_key=project_path.replace("/", "-"),
            project_path=f"/home/dev/{project_path}",
            project_short=project_short,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_minutes=round(duration, 1),
            total_entries=num_prompts * 4 + total_tool_calls,
            human_prompt_count=num_prompts,
            tool_call_count=total_tool_calls,
            model=model,
            first_prompt=first_prompt,
            human_prompts=human_prompts,
            topics=topics,
            top_tools=sorted(tool_counts, key=lambda x: -x[1])[:6],
            tools_used=sorted(t for t, _ in tool_counts),
            domains=[domain] + (["coding"] if domain != "coding" and random.random() > 0.6 else []),
            file_types=random.sample(["py", "ts", "json", "yaml", "md", "sql", "tf", "sh"], random.randint(2, 5)),
            git_branch=branch,
            correction_count=corrections,
            approval_count=approvals,
            slug=slug,
            cwd=f"/home/dev/{project_path}",
            version="2.1.63",
            permission_mode=random.choice(["default", "default", "default", "acceptEdits"]),
            subagent_count=random.randint(0, 5),
            total_input_tokens=random.randint(50000, 500000),
            total_output_tokens=random.randint(5000, 80000),
            is_active=is_active,
        ))

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions
