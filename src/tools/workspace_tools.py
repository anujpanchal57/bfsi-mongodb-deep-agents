"""Workspace tools (FR-1, FR-2, FR-5, FR-7). Narrow, validated, idempotent."""
from __future__ import annotations

import uuid

from src.models import new_run, utcnow
from src.reviewer_pack import build_reviewer_pack
from src.tools import ToolContext, ToolError, require_workspace, tool


@tool
def get_workspace(ctx: ToolContext, workspace_id: str) -> dict:
    ws = require_workspace(ctx, workspace_id)
    ws = dict(ws)
    ws["artifact_count"] = ctx.repo.count("artifacts", {"workspace_id": workspace_id})
    return ws


@tool
def list_workspace_artifacts(ctx: ToolContext, workspace_id: str,
                             filters: dict | None = None) -> list[dict]:
    require_workspace(ctx, workspace_id)
    filt = {"workspace_id": workspace_id}
    for k in ("artifact_type", "period", "ingestion_status"):
        if filters and filters.get(k):
            filt[k] = filters[k]
    arts = ctx.repo.find("artifacts", filt, limit=1000)
    return [{k: a.get(k) for k in (
        "_id", "artifact_id", "filename", "artifact_type", "period", "entity",
        "vendor", "contract", "version", "content_hash", "ingestion_status",
        "source_uri", "tags", "created_at")} for a in arts]


@tool
def start_workflow_run(ctx: ToolContext, workspace_id: str,
                       session_id: str, goal: str) -> dict:
    """Create a durable business-state run record (FR-5). Platform session
    durability comes from the checkpointer; this records the demo's workflow
    state so the UI and reviewer pack can read it."""
    require_workspace(ctx, workspace_id)
    run = new_run(f"run-{uuid.uuid4().hex[:12]}", workspace_id, session_id, goal)
    ctx.repo.upsert("runs", run)
    return run


@tool
def save_working_note(ctx: ToolContext, workspace_id: str, run_id: str,
                      note: str) -> dict:
    require_workspace(ctx, workspace_id)
    run = ctx.repo.get("runs", run_id)
    if not run or run.get("workspace_id") != workspace_id:
        raise ToolError("run_not_found", f"Run '{run_id}' not in workspace.")
    notes = list(run.get("working_notes", []))
    notes.append({"note": note, "created_at": utcnow()})
    ctx.repo.patch("runs", run_id, {"working_notes": notes})
    return {"run_id": run_id, "notes": len(notes)}


@tool
def update_workflow_state(ctx: ToolContext, workspace_id: str, run_id: str,
                          state_patch: dict) -> dict:
    """Durable state write (FR-5). Only allowlisted fields may be patched."""
    require_workspace(ctx, workspace_id)
    run = ctx.repo.get("runs", run_id)
    if not run or run.get("workspace_id") != workspace_id:
        raise ToolError("run_not_found", f"Run '{run_id}' not in workspace.")
    allowed = {"state", "findings", "evidence_references", "open_questions",
               "handoff_ids", "pending_human_decisions",
               "last_successful_action", "next_action"}
    patch = {k: v for k, v in state_patch.items() if k in allowed}
    ctx.repo.patch("runs", run_id, patch)
    if "state" in patch:
        ctx.repo.patch("workspaces", workspace_id, {"current_step": patch["state"]})
    return {"run_id": run_id, "patched": sorted(patch)}


@tool
def generate_reviewer_pack(ctx: ToolContext, workspace_id: str,
                           run_id: str) -> dict:
    """Generate the structured reviewer pack (FR-7) with human-decision
    labels (FR-8). The agent proposes; humans decide."""
    require_workspace(ctx, workspace_id)
    run = ctx.repo.get("runs", run_id)
    if not run or run.get("workspace_id") != workspace_id:
        raise ToolError("run_not_found", f"Run '{run_id}' not in workspace.")
    try:
        pack = build_reviewer_pack(ctx.repo, workspace_id, run_id)
    except ValueError as exc:
        raise ToolError("pack_failed", str(exc))
    return {"pack_id": pack["pack_id"], "markdown": pack["markdown"],
            "human_decision_required": pack["human_decision_required"]}
