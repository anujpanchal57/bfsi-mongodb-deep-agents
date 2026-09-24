"""Specialist subagent declaration for App.deep_agent(subagents=[...]).

Dispatch happens through deepagents' built-in `task()` tool; the durable
handoff *record* is written by the orchestrator via create_specialist_handoff.
"""
from __future__ import annotations

from src.demo_agent.prompts import SPECIALIST_PROMPT

VARIANCE_SPECIALIST = {
    "name": "variance_specialist",
    "description": (
        "Scoped accrual-variance analyst: compares current- vs prior-period "
        "accrual extracts, checks contract/rate evidence, and returns "
        "findings with evidence references and unresolved questions. Never "
        "approves, posts, or closes anything."),
    "system_prompt": SPECIALIST_PROMPT,
}
