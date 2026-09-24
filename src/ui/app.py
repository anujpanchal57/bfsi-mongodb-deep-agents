"""Thin demo UI. Business-state views read Atlas directly; agent interaction
goes through the platform invoke API (deployed agent or `agentengine dev up`)
— no direct agent runtime here.
"""
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import load_settings
from src.models import HUMAN_CONTROLLED_ACTIONS
from src.platform_client import PlatformNotConfigured, invoke_agent, platform_health
from src.storage.atlas_repository import AtlasRepository

st.set_page_config(page_title="Accrual Variance Review — Agent Engine Demo",
                   layout="wide")

settings = load_settings()
repo = AtlasRepository(settings)

st.title("Month-End Accrual Variance Review")
st.caption(f"MongoDB Agent Engine + Deep Agents VFS + Atlas + S3 — "
           f"platform: {platform_health(settings)}")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"

workspaces = repo.find("workspaces", {}, limit=100)
if not workspaces:
    st.error("No workspaces found. Run `make seed` first.")
    st.stop()

ws_ids = [w["_id"] for w in workspaces]
ws_id = st.sidebar.selectbox("Workspace", ws_ids,
                             index=ws_ids.index(settings.workspace_id)
                             if settings.workspace_id in ws_ids else 0)
ws = repo.get("workspaces", ws_id)

tab_ws, tab_agent, tab_handoff, tab_pack = st.tabs(
    ["Workspace", "Agent", "Handoff", "Reviewer pack"])

with tab_ws:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Period", ws["period"])
    c2.metric("Entity", ws["entity"])
    c3.metric("Status", ws["status"])
    c4.metric("Current step", ws["current_step"])
    st.subheader("Open evidence gaps")
    st.write(ws.get("open_evidence_gaps") or "None")
    st.subheader("Artifacts")
    arts = repo.find("artifacts", {"workspace_id": ws_id}, limit=1000)
    st.dataframe([{k: a.get(k) for k in
                   ("filename", "artifact_type", "period", "ingestion_status",
                    "source_uri")} for a in arts])
    st.caption("Chunking/embeddings/search: MongoFilesystemBackend "
               "(Atlas $rankFusion hybrid; Bedrock Titan embeddings).")

with tab_agent:
    st.write(f"Session: `{st.session_state.session_id}`")
    msg = st.text_input("Your request",
                        value="Review the open accrual variance.")
    col_a, col_b, col_c = st.columns(3)
    send = col_a.button("Send to agent")
    resume = col_b.button("Resume session")
    new_session = col_c.button("New session (simulate break)")

    if new_session:
        st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"
        st.rerun()

    if send or resume:
        try:
            with st.spinner("Agent working…"):
                resp = invoke_agent(
                    settings,
                    "Please continue." if resume else msg,
                    session_id=st.session_state.session_id,
                    payload={"workspace_id": ws_id})
            st.json(resp)
        except PlatformNotConfigured as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Invoke failed: {exc}")

    st.subheader("Durable run state (from Atlas, not the conversation)")
    runs = repo.find("runs", {"workspace_id": ws_id}, limit=20)
    for r in sorted(runs, key=lambda r: r.get("updated_at", "")):
        with st.expander(f"{r['_id']} — {r['state']}"):
            st.json({"goal": r.get("goal"), "state": r.get("state"),
                     "next_action": r.get("next_action"),
                     "open_questions": r.get("open_questions"),
                     "evidence_references": r.get("evidence_references"),
                     "handoff_ids": r.get("handoff_ids")})
    if any(r.get("state") == "human_decision_required" for r in runs):
        st.warning("HUMAN DECISION REQUIRED — the agent cannot approve, "
                   "post, or close this item.")

with tab_handoff:
    runs = repo.find("runs", {"workspace_id": ws_id}, limit=100)
    hids = sorted({h for r in runs for h in r.get("handoff_ids", [])})
    if not hids:
        st.info("No handoffs yet.")
    for hid in hids:
        h = repo.get("handoffs", hid)
        with st.expander(f"{hid} — {h['status']} — {h['task'][:80]}"):
            st.json({"scope": h.get("scope"), "status": h.get("status")})
            if h.get("result"):
                st.subheader("Findings")
                for f in h["result"].get("finding", []):
                    st.write(f"- {f.get('detail', f)}")
                st.subheader("Unresolved questions")
                for q in h["result"].get("unresolved_questions", []):
                    st.write(f"- {q}")
                st.subheader("Evidence references")
                st.dataframe(h["result"].get("evidence_references", []))

with tab_pack:
    packs = repo.find("packs", {"workspace_id": ws_id}, limit=10)
    if not packs:
        st.info("No reviewer pack yet — run the agent to completion.")
    for p in packs:
        st.error("HUMAN DECISION REQUIRED — no approve/post/close action is "
                 "available to the agent.")
        st.markdown(p.get("markdown", ""))
        st.download_button("Download reviewer pack", p.get("markdown", ""),
                           file_name=f"{p['_id']}.md", key=p["_id"])
        st.caption("Human-controlled: " + ", ".join(HUMAN_CONTROLLED_ACTIONS))
