"""Business tools: offline coverage via a fake App collecting @app.tool()
registrations (the real App needs the platform SDK)."""
import json

import pytest

from src.demo_agent import tools as agent_tools


class FakeApp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


@pytest.fixture()
def platform_tools(ctx, monkeypatch):
    monkeypatch.setattr(agent_tools, "_ctx", ctx)
    app = FakeApp()
    agent_tools.register(app)
    return app.tools


def test_all_business_tools_registered(platform_tools):
    expected = {"get_workspace", "list_workspace_artifacts",
                "start_workflow_run", "update_workflow_state",
                "save_working_note", "create_specialist_handoff",
                "get_handoff", "save_specialist_result",
                "generate_reviewer_pack"}
    assert expected <= set(platform_tools)
    # No approval/posting/closure tool is ever exposed.
    assert not any(any(bad in name for bad in ("approve", "post", "close"))
                   for name in platform_tools)


def test_get_workspace(platform_tools, ctx):
    out = json.loads(platform_tools["get_workspace"](ctx.settings.workspace_id))
    assert out["period"] == "2026-06"
    assert out["artifact_count"] == 7
    assert out["open_evidence_gaps"] == ["invoice_support"]


def test_run_state_roundtrip(platform_tools, ctx):
    ws = ctx.settings.workspace_id
    run = json.loads(platform_tools["start_workflow_run"](ws, "s1", "review"))
    rid = run["_id"]
    patch = {"state": "evidence_review", "open_questions": ["missing invoice"]}
    platform_tools["update_workflow_state"](ws, rid, patch)
    stored = ctx.repo.get("runs", rid)
    assert stored["state"] == "evidence_review"
    assert stored["open_questions"] == ["missing invoice"]
    assert ctx.repo.get("workspaces", ws)["current_step"] == "evidence_review"


def test_handoff_record_roundtrip(platform_tools, ctx):
    ws = ctx.settings.workspace_id
    rid = json.loads(platform_tools["start_workflow_run"](ws, "s1", "review"))["_id"]
    h = json.loads(platform_tools["create_specialist_handoff"](
        ws, rid, "analyze variance",
        {"artifact_ids": ["a1"], "period": "2026-06", "entity": "demo_finance_india"}))
    assert h["status"] == "created"
    res = json.loads(platform_tools["save_specialist_result"](
        ws, h["_id"],
        {"finding": [{"detail": "variance confirmed"}],
         "evidence_references": [{"artifact_id": "a1"}],
         "unresolved_questions": ["invoice missing"],
         "recommended_next_step": "human review"}))
    assert res["status"] == "completed"
    assert json.loads(platform_tools["get_handoff"](ws, h["_id"]))["result"]


def test_specialist_result_requires_expected_fields(platform_tools, ctx):
    ws = ctx.settings.workspace_id
    rid = json.loads(platform_tools["start_workflow_run"](ws, "s1", "review"))["_id"]
    h = json.loads(platform_tools["create_specialist_handoff"](
        ws, rid, "t", {"artifact_ids": [], "period": "p", "entity": "e"}))
    out = json.loads(platform_tools["save_specialist_result"](
        ws, h["_id"], {"finding": []}))
    assert out["error"]["code"] == "invalid_result"


def test_generate_reviewer_pack_via_tool(platform_tools, ctx):
    ws = ctx.settings.workspace_id
    rid = json.loads(platform_tools["start_workflow_run"](ws, "s1", "review"))["_id"]
    platform_tools["update_workflow_state"](ws, rid, {
        "findings": [{"type": "variance_summary", "detail": "v",
                      "classification": "evidence_observed"}],
        "evidence_references": [{"artifact_id": "a1",
                                 "source_uri": "s3://demo-bucket/x"}]})
    out = json.loads(platform_tools["generate_reviewer_pack"](ws, rid))
    assert out["human_decision_required"]["required"] is True
    assert "HUMAN DECISION REQUIRED" in out["markdown"]
