"""Business-state tools exposed to the agent via @app.tool().

Thin bridges over src/tools/* (validation, logging, structured errors live
there). The model never gets raw collection access. Tools return JSON strings
per the SDK tool contract.
"""
from __future__ import annotations

import json

from src.config import load_settings
from src.tools import ToolContext
from src.tools.handoff_tools import (create_specialist_handoff as _create_handoff,
                                     get_handoff as _get_handoff,
                                     save_specialist_result as _save_result)
from src.tools.workspace_tools import (
    generate_reviewer_pack as _gen_pack,
    get_workspace as _get_workspace,
    list_workspace_artifacts as _list_artifacts,
    save_working_note as _save_note,
    start_workflow_run as _start_run,
    update_workflow_state as _update_state)

_ctx: ToolContext | None = None


def _get_ctx() -> ToolContext:
    """Lazy singleton: one Atlas + S3 connection set per AER process."""
    global _ctx
    if _ctx is None:
        from src.storage.atlas_repository import AtlasRepository
        from src.storage.s3_repository import S3Repository
        settings = load_settings()
        _ctx = ToolContext(repo=AtlasRepository(settings),
                           s3=S3Repository(settings), settings=settings)
    return _ctx


def _json(payload) -> str:
    return json.dumps(payload, default=str)


def register(app) -> None:
    """Register all business tools on the SDK App instance."""

    @app.tool()
    def get_workspace(workspace_id: str) -> str:
        """Load workspace metadata: period, entity, status, current step,
        open evidence gaps, artifact count."""
        return _json(_get_workspace(_get_ctx(), workspace_id))

    @app.tool()
    def list_workspace_artifacts(workspace_id: str,
                                 artifact_type: str = "") -> str:
        """List registered artifacts (id, filename, type, period, ingestion
        status, source URI). Optionally filter by artifact_type."""
        filters = {"artifact_type": artifact_type} if artifact_type else None
        return _json(_list_artifacts(_get_ctx(), workspace_id, filters=filters))

    @app.tool()
    def start_workflow_run(workspace_id: str, session_id: str, goal: str) -> str:
        """Create the durable run record for this review. Call first; keep the
        returned run_id for all later state updates."""
        return _json(_start_run(_get_ctx(), workspace_id, session_id, goal))

    @app.tool()
    def update_workflow_state(workspace_id: str, run_id: str,
                              state_patch: dict) -> str:
        """Persist workflow state: state, findings, evidence_references,
        open_questions, handoff_ids, pending_human_decisions, next_action.
        Call after every major step so work resumes after a session break."""
        return _json(_update_state(_get_ctx(), workspace_id, run_id, state_patch))

    @app.tool()
    def save_working_note(workspace_id: str, run_id: str, note: str) -> str:
        """Append a working note to the durable run record."""
        return _json(_save_note(_get_ctx(), workspace_id, run_id, note))

    @app.tool()
    def create_specialist_handoff(workspace_id: str, run_id: str, task: str,
                                  scope: dict) -> str:
        """Create the durable handoff record for the variance specialist
        (scope: artifact_ids, period, entity). Then dispatch the work with
        task("variance_specialist", ...)."""
        return _json(_create_handoff(_get_ctx(), workspace_id, run_id, task, scope))

    @app.tool()
    def get_handoff(workspace_id: str, handoff_id: str) -> str:
        """Read a handoff record and its result, if completed."""
        return _json(_get_handoff(_get_ctx(), workspace_id, handoff_id))

    @app.tool()
    def save_specialist_result(workspace_id: str, handoff_id: str,
                               result: dict) -> str:
        """Persist the specialist's result. Required keys: finding,
        evidence_references, unresolved_questions, recommended_next_step."""
        return _json(_save_result(_get_ctx(), workspace_id, handoff_id, result))

    @app.tool()
    def generate_reviewer_pack(workspace_id: str, run_id: str) -> str:
        """Generate the reviewer pack: findings, evidence table, evidence
        gaps, specialist output, proposed next step, and the explicit
        human-decision-required banner. This PROPOSES; it never approves."""
        return _json(_gen_pack(_get_ctx(), workspace_id, run_id))
