"""Reviewer-pack generation (FR-7) with explicit human-decision labels (FR-8)."""
from __future__ import annotations

from src.models import HUMAN_CONTROLLED_ACTIONS, utcnow


def build_reviewer_pack(repo, workspace_id: str, run_id: str) -> dict:
    ws = repo.get("workspaces", workspace_id)
    run = repo.get("runs", run_id)
    if not ws or not run:
        raise ValueError("workspace or run not found")

    artifacts = repo.find("artifacts", {"workspace_id": workspace_id}, limit=1000)
    approval = next((a for a in artifacts
                     if a.get("artifact_type") == "approval_record"), None)

    specialist = []
    for hid in run.get("handoff_ids", []):
        h = repo.get("handoffs", hid)
        if h and h.get("result"):
            specialist.append({"handoff_id": hid, "task": h["task"],
                               "status": h["status"], **h["result"]})

    gaps = ws.get("open_evidence_gaps", [])
    pack = {
        "pack_id": f"pack-{run_id}",
        "workspace_id": workspace_id,
        "run_id": run_id,
        "objective": run.get("goal"),
        "period": ws.get("period"),
        "entity": ws.get("entity"),
        "executive_summary": _summary(run, specialist, gaps),
        "variance_under_review": _variance_section(run),
        "findings": run.get("findings", []),
        "evidence_table": run.get("evidence_references", []),
        "missing_or_stale_evidence": [
            {"gap": g, "classification": "evidence_required",
             "detail": "Seeded evidence gap; requires human follow-up."}
            for g in gaps
        ],
        "assumptions_and_uncertainty": _assumptions(specialist),
        "specialist_output": specialist,
        "proposed_next_step": _next_step(gaps),
        "human_decision_required": {
            "required": True,
            "approval_status": (approval or {}).get("approval_status",
                                                    "pending_human_review"),
            "human_controlled_actions": HUMAN_CONTROLLED_ACTIONS,
            "note": "The agent gathers and analyzes evidence only. Approval, "
                    "posting, materiality, and closure are human decisions.",
        },
        "generated_at": utcnow(),
        "human_review_status": "pending",
        "version": 1,
    }
    pack["markdown"] = render_markdown(pack)
    repo.upsert("packs", {**{k: v for k, v in pack.items() if k != "markdown"},
                          "_id": pack["pack_id"], "markdown": pack["markdown"]})
    return pack


def _summary(run, specialist, gaps) -> str:
    s = f"Accrual variance review '{run.get('goal')}' reached state '{run.get('state')}'."
    if specialist:
        s += " Specialist variance analysis is complete."
    if gaps:
        s += f" Open evidence gaps: {', '.join(gaps)}."
    return s + " Human decision required before any approval or posting."


def _variance_section(run) -> dict:
    for f in run.get("findings", []):
        if isinstance(f, dict) and f.get("type") == "variance_summary":
            return f
    return {"detail": "See findings.", "classification": "agent_inference"}


def _assumptions(specialist) -> list[str]:
    out: list[str] = []
    for s in specialist:
        out += s.get("assumptions", [])
    return out


def _next_step(gaps) -> str:
    if gaps:
        return ("Obtain the missing evidence (" + ", ".join(gaps) +
                "), then the finance controller reviews and decides.")
    return "Finance controller reviews the pack and records a human decision."


def render_markdown(pack: dict) -> str:
    lines = [
        f"# Reviewer Pack — {pack['workspace_id']}",
        "",
        f"**Period:** {pack['period']}  |  **Entity:** {pack['entity']}  |  "
        f"**Run:** {pack['run_id']}  |  **Generated:** {pack['generated_at']}",
        "",
        "> **HUMAN DECISION REQUIRED** — this pack proposes; it never approves, "
        "posts, or closes.",
        "",
        "## Objective", str(pack["objective"]), "",
        "## Executive summary", pack["executive_summary"], "",
        "## Findings",
    ]
    for f in pack["findings"]:
        if isinstance(f, dict):
            lines.append(f"- [{f.get('classification','evidence_observed')}] "
                         f"{f.get('detail', f)}")
        else:  # LLM-persisted findings may be plain strings
            lines.append(f"- [evidence_observed] {f}")
    lines += ["", "## Evidence table",
              "| Artifact | File | Chunk | Source |",
              "| --- | --- | --- | --- |"]
    for e in pack["evidence_table"]:
        lines.append(f"| {e.get('artifact_id','')} | {e.get('filename','')} "
                     f"| {e.get('chunk_id','')} | {e.get('source_uri','')} |")
    lines += ["", "## Evidence still required"]
    for m in pack["missing_or_stale_evidence"]:
        lines.append(f"- **{m['gap']}** — {m['detail']}")
    lines += ["", "## Assumptions and uncertainty"]
    for a in pack["assumptions_and_uncertainty"] or ["None recorded."]:
        lines.append(f"- {a}")
    lines += ["", "## Specialist output"]
    for s in pack["specialist_output"] or ["None."]:
        if isinstance(s, dict):
            lines.append(f"### {s['handoff_id']} — {s['task']} ({s['status']})")
            for f in s.get("finding", []):
                lines.append(
                    f"- {f.get('detail', f) if isinstance(f, dict) else f}")
            for q in s.get("unresolved_questions", []):
                lines.append(f"- Unresolved: {q}")
    lines += ["", "## Proposed next step", pack["proposed_next_step"], "",
              "## Human-controlled actions (agent must never perform)",
              *[f"- {a}" for a in pack["human_decision_required"]["human_controlled_actions"]]]
    return "\n".join(lines)
