"""Shared data shapes and constants. Plain dicts at the Atlas boundary."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# Actions that must never be exposed to the agent (FR-8).
HUMAN_CONTROLLED_ACTIONS = [
    "accounting_policy_judgment",
    "materiality_determination",
    "journal_approval_or_posting",
    "valuation_or_provision_decision",
    "final_reporting",
    "regulatory_closure_or_communication",
]

# Workflow steps of the orchestrator state machine, in order.
WORKFLOW_STEPS = [
    "created",
    "evidence_review",
    "gap_detection",
    "handoff_created",
    "specialist_completed",
    "reviewer_pack_generated",
    "human_decision_required",
]


def new_workspace(workspace_id: str, period: str, entity: str, owner: str) -> dict:
    now = utcnow()
    return {
        "_id": workspace_id,
        "process": "accrual_review",
        "period": period,
        "entity": entity,
        "owner": owner,
        "status": "in_progress",
        "current_step": "created",
        "open_evidence_gaps": [],
        "created_at": now,
        "updated_at": now,
    }


def new_run(run_id: str, workspace_id: str, session_id: str, goal: str,
            parent_run_id: str | None = None) -> dict:
    now = utcnow()
    return {
        "_id": run_id,
        "workspace_id": workspace_id,
        "session_id": session_id,
        "parent_run_id": parent_run_id,
        "goal": goal,
        "state": "created",
        "user_request": goal,
        "findings": [],
        "evidence_references": [],
        "open_questions": [],
        "handoff_ids": [],
        "pending_human_decisions": [],
        "last_successful_action": None,
        "next_action": "gather_evidence",
        "created_at": now,
        "updated_at": now,
    }


def new_handoff(handoff_id: str, workspace_id: str, parent_run_id: str,
                task: str, scope: dict) -> dict:
    return {
        "_id": handoff_id,
        "handoff_id": handoff_id,
        "workspace_id": workspace_id,
        "parent_run_id": parent_run_id,
        "task": task,
        "scope": scope,
        "expected_output": [
            "finding",
            "evidence_references",
            "unresolved_questions",
            "recommended_next_step",
        ],
        "status": "created",
        "result": None,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
