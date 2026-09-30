"""Platform integration tests — run against `agentengine dev up` or a deployed
agent. Skipped by default; they need the real stack (Atlas + S3 + Bedrock +
LLM provider + SDK).

    AGENT_ENGINE_URL=http://localhost:8000 pytest tests/test_platform_integration.py
"""
import os
import uuid

import pytest

from src.config import load_settings
from src.platform_client import invoke_agent

pytestmark = pytest.mark.skipif(
    not os.environ.get("AGENT_ENGINE_URL"),
    reason="AGENT_ENGINE_URL not set — platform integration tests skipped")


@pytest.fixture()
def settings():
    return load_settings()


def test_full_flow_durable_resume_and_pack(settings):
    ws = settings.workspace_id
    session = f"it-{uuid.uuid4().hex[:8]}"

    r1 = invoke_agent(settings, "Review the open accrual variance.",
                      session_id=session, payload={"workspace_id": ws})
    assert r1, "empty invoke response"

    # Resume in a fresh request — session durability is platform-owned.
    r2 = invoke_agent(settings, "Please continue.", session_id=session,
                      payload={"workspace_id": ws})
    assert r2

    from src.storage.atlas_repository import AtlasRepository
    repo = AtlasRepository(settings)
    runs = repo.find("runs", {"workspace_id": ws}, limit=20)
    assert runs, "agent did not persist a run record"
    latest = sorted(runs, key=lambda r: r.get("updated_at", ""))[-1]
    assert latest.get("evidence_references"), "no evidence references persisted"
    assert latest.get("handoff_ids"), "no durable handoff recorded"

    h = repo.get("handoffs", latest["handoff_ids"][-1])
    assert h["status"] == "completed"
    assert h["result"]["evidence_references"]

    pack = repo.get("packs", f"pack-{latest['_id']}")
    if pack is None:
        invoke_agent(settings, "Generate the reviewer pack.",
                     session_id=session, payload={"workspace_id": ws})
        pack = repo.get("packs", f"pack-{latest['_id']}")
    assert pack["human_decision_required"]["required"] is True
    assert any(g["gap"] == "invoice_support"
               for g in pack["missing_or_stale_evidence"])


def test_retrieval_targets_via_backend(settings):
    """AC-3: exact-match and semantic retrieval through the VFS backend."""
    from src.demo_agent.backend import grep_text
    exact = grep_text(settings, "CON-7781")
    assert any("CON-7781" in (m["text"] or "") for m in exact)
    sem = grep_text(settings, "support for the June cloud-services accrual variance")
    assert sem, "semantic query returned no evidence"
