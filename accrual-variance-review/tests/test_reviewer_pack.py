"""Reviewer pack (FR-7, FR-8, AC-5, AC-7): built from durable business state,
independent of how the agent runtime produced it."""
import pytest

from src.models import new_handoff, new_run
from src.reviewer_pack import build_reviewer_pack


@pytest.fixture()
def pack(seeded):
    repo, ws = seeded["repo"], seeded["workspace_id"]
    run = new_run("run-test1", ws, "s-test", "review the variance")
    run.update({
        "state": "specialist_completed",
        "findings": [{"type": "variance_summary",
                      "classification": "evidence_observed",
                      "detail": "Booked 1,240,000 vs expected 1,275,000 INR."}],
        "evidence_references": [
            {"artifact_id": "art-accrual_extract_current-x",
             "filename": "accrual_extract_current.csv",
             "source_uri": "s3://demo-bucket/agent-engine-demo/source/2026-06/accrual_extract_current.csv"}],
        "handoff_ids": ["hof-test1"],
    })
    repo.upsert("runs", run)
    h = new_handoff("hof-test1", ws, "run-test1", "analyze variance",
                    {"artifact_ids": ["a1"], "period": "2026-06",
                     "entity": "demo_finance_india"})
    h["status"] = "completed"
    h["result"] = {"finding": [{"detail": "Variance INR 35,000 is new."}],
                   "evidence_references": [{"artifact_id": "a1"}],
                   "unresolved_questions": ["Invoice support missing."],
                   "recommended_next_step": "Request invoice; human review.",
                   "assumptions": ["Rate schedule applies for full period."]}
    repo.upsert("handoffs", h)
    return build_reviewer_pack(repo, ws, "run-test1")


def test_pack_contains_required_sections(pack):
    for key in ("objective", "period", "entity", "executive_summary",
                "findings", "evidence_table", "missing_or_stale_evidence",
                "assumptions_and_uncertainty", "specialist_output",
                "proposed_next_step", "human_decision_required", "run_id",
                "generated_at"):
        assert key in pack, f"missing section: {key}"


def test_pack_evidence_references(pack):
    assert pack["evidence_table"]
    for e in pack["evidence_table"]:
        assert e.get("artifact_id") and e.get("source_uri")


def test_gap_is_evidence_required_not_invented(pack):
    gaps = pack["missing_or_stale_evidence"]
    assert any(g["gap"] == "invoice_support" for g in gaps)
    assert all(g["classification"] == "evidence_required" for g in gaps)


def test_human_boundary(pack):
    hd = pack["human_decision_required"]
    assert hd["required"] is True
    assert hd["human_controlled_actions"]
    assert pack["human_review_status"] == "pending"
    assert "HUMAN DECISION REQUIRED" in pack["markdown"]


def test_specialist_output_included(pack):
    assert pack["specialist_output"][0]["handoff_id"] == "hof-test1"
    assert pack["assumptions_and_uncertainty"] == [
        "Rate schedule applies for full period."]


def test_render_tolerates_string_findings(seeded):
    """LLM-persisted findings may be plain strings (observed live: the
    specialist returned finding as list[str) — render must not crash."""
    from src.reviewer_pack import render_markdown
    repo, ws = seeded["repo"], seeded["workspace_id"]
    run = new_run("run-str", ws, "s-str", "review the variance")
    run.update({"state": "specialist_completed",
                "findings": ["Booked 1,240,000 vs expected 1,275,000 INR."],
                "handoff_ids": ["hof-str"]})
    repo.upsert("runs", run)
    h = new_handoff("hof-str", ws, "run-str", "analyze variance",
                    {"artifact_ids": [], "period": "2026-06",
                     "entity": "demo_finance_india"})
    h["status"] = "completed"
    h["result"] = {"finding": ["Variance INR 35,000 is new."],
                   "evidence_references": [],
                   "unresolved_questions": ["Invoice support missing."],
                   "recommended_next_step": "Request invoice.",
                   "assumptions": []}
    repo.upsert("handoffs", h)
    from src.reviewer_pack import build_reviewer_pack
    pack = build_reviewer_pack(repo, ws, "run-str")
    assert "Variance INR 35,000 is new." in pack["markdown"]
    assert pack["human_decision_required"]["required"] is True
