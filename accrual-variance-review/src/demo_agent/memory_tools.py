"""Memory tools: cross-session recall and durable facts via the platform
memory service (app.memory). Per-request user/session scoping is resolved by
the platform runtime — never passed by the model.

Boundary: memory stores CONTEXT, never decisions. remember_fact refuses
anything that looks like an approval — approvals are human-only and are not
memorialized. See specs/memory_enablement_spec.md §0.
"""
from __future__ import annotations

import json
import re

# Approval-shaped content must not be persisted as a "fact" — it would let a
# retrieved memory masquerade as a decision in a later session.
_FORBIDDEN = re.compile(
    r"\b(approv\w*|post(?:ing|ed)?\s+(?:the\s+)?(?:adjustment|entry|journal)|"
    r"close[sd]?\s+(?:the\s+)?(?:item|variance|period)|sign(?:ed)?[- ]off)\b",
    re.IGNORECASE)


def register_memory(app) -> None:
    """Register memory tools on the SDK App instance."""

    @app.tool()
    def recall_context(query: str, max_tokens: int = 1500) -> str:
        """Recall cross-session memory relevant to the query: past review
        episodes, known facts about vendors/cost centers, domain term
        definitions. Memory is context, NOT evidence — evidence still
        requires path:line citations from the workspace corpus."""
        ctx = app.memory.build_context(
            query=query,
            max_tokens=max_tokens,
            enabled_sources={"episodic", "semantic", "taxonomic"},
        )
        return ctx.formatted_context or "(no relevant memory)"

    @app.tool()
    def remember_fact(label: str, text: str) -> str:
        """Save a durable labeled fact (semantic memory) for context that
        should outlive this session, e.g. 'the reviewer for CC-410 is Priya'.
        NEVER for approvals, postings, or closures — those are human-only
        decisions and are not stored."""
        if _FORBIDDEN.search(f"{label} {text}"):
            return json.dumps({
                "saved": None,
                "error": "refused: approval/decision content is not stored "
                         "in memory — human decisions live in the approval "
                         "record, not in agent memory"})
        app.memory.save_semantic(label=label, text=text)
        return json.dumps({"saved": label})
