"""Specialist handoff tools (FR-6)."""
from __future__ import annotations

import hashlib

from src.models import new_handoff, utcnow
from src.tools import ToolContext, ToolError, require_workspace, tool

_VALID_STATUS = {"created", "running", "completed", "blocked"}


@tool
def create_specialist_handoff(ctx: ToolContext, workspace_id: str, run_id: str,
                              task: str, scope: dict) -> dict:
    require_workspace(ctx, workspace_id)
    run = ctx.repo.get("runs", run_id)
    if not run or run.get("workspace_id") != workspace_id:
        raise ToolError("run_not_found", f"Run '{run_id}' not in workspace.")
    # Deterministic handoff id -> idempotent re-creation.
    hid = "hof-" + hashlib.sha1(
        f"{run_id}:{task}".encode()).hexdigest()[:12]
    existing = ctx.repo.get("handoffs", hid)
    if existing:
        return existing
    handoff = new_handoff(hid, workspace_id, run_id, task, scope)
    ctx.repo.upsert("handoffs", handoff)
    ids = list(run.get("handoff_ids", []))
    if hid not in ids:
        ids.append(hid)
    ctx.repo.patch("runs", run_id, {"handoff_ids": ids})
    return handoff


@tool
def get_handoff(ctx: ToolContext, workspace_id: str, handoff_id: str) -> dict:
    require_workspace(ctx, workspace_id)
    h = ctx.repo.get("handoffs", handoff_id)
    if not h or h.get("workspace_id") != workspace_id:
        raise ToolError("handoff_not_found", f"Handoff '{handoff_id}' not found.")
    return h


@tool
def save_specialist_result(ctx: ToolContext, workspace_id: str,
                           handoff_id: str, result: dict) -> dict:
    require_workspace(ctx, workspace_id)
    h = ctx.repo.get("handoffs", handoff_id)
    if not h or h.get("workspace_id") != workspace_id:
        raise ToolError("handoff_not_found", f"Handoff '{handoff_id}' not found.")
    # Tolerate the model emitting the specialist's "EVIDENCE:" label as a key.
    if "evidence_references" not in result and "evidence" in result:
        result["evidence_references"] = result.pop("evidence")
    required = set(h.get("expected_output", []))
    missing = required - set(result)
    if missing:
        raise ToolError(
            "invalid_result",
            f"Specialist result missing fields: {sorted(missing)} "
            f"(received keys: {sorted(result)}). Pass ALL required keys; "
            f"use an empty list for evidence_references when the specialist "
            f"reported 'evidence required'.")
    ctx.repo.patch("handoffs", handoff_id,
                   {"status": "completed", "result": result,
                    "completed_at": utcnow()})
    return {"handoff_id": handoff_id, "status": "completed"}
