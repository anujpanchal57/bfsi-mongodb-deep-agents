#!/usr/bin/env python
"""CLI smoke test against the RUNNING agent (deployed or `agentengine dev up`):
invoke -> (platform-managed interrupt/resume via durable sessions) ->
reviewer pack.

Usage: AGENT_ENGINE_URL=http://localhost:3000 python scripts/smoke_demo.py
(AGENT_ENGINE_URL = the ui URL printed by `agentengine dev up`; for the
deployed agent, leave it unset and rely on .agentengine/state.json or
AGENT_ENGINE_PROJECT_ID/AGENT_ENGINE_WORKSPACE_ID.)
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.platform_client import PlatformNotConfigured, invoke_agent
from src.storage.atlas_repository import AtlasRepository


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", default=None)
    ap.add_argument("--session-id", default=f"smoke-{uuid.uuid4().hex[:8]}")
    args = ap.parse_args()

    settings = load_settings()
    ws = args.workspace_id or settings.workspace_id

    try:
        print("=== 1. invoke: review the variance (fresh session) ===")
        r1 = invoke_agent(settings, "Review the open accrual variance.",
                          session_id=args.session_id,
                          payload={"workspace_id": ws})
        print(json.dumps(r1, indent=2, default=str)[:3000])

        print("\n=== 2. resume: same session id, new process ===")
        r2 = invoke_agent(settings, "Please continue.",
                          session_id=args.session_id,
                          payload={"workspace_id": ws})
        print(json.dumps(r2, indent=2, default=str)[:3000])
    except PlatformNotConfigured as exc:
        sys.exit(str(exc))

    print("\n=== 3. durable business state in Atlas ===")
    repo = AtlasRepository(load_settings())
    runs = repo.find("runs", {"workspace_id": ws}, limit=10)
    latest = sorted(runs, key=lambda r: r.get("updated_at", ""))[-1] if runs else None
    if not latest:
        sys.exit("No run record found — the agent did not persist state.")
    print(json.dumps({"run_id": latest["_id"], "state": latest["state"],
                      "open_questions": latest.get("open_questions"),
                      "handoff_ids": latest.get("handoff_ids")}, indent=2))
    pack = repo.get("packs", f"pack-{latest['_id']}")
    if pack:
        print("\n=== 4. reviewer pack ===")
        print(pack["markdown"][:2000])
        assert pack["human_decision_required"]["required"] is True
        assert pack["missing_or_stale_evidence"], "expected evidence gap in pack"
        print("\nSmoke demo PASSED. Stopped at human decision required.")
    else:
        print("No reviewer pack yet — ask the agent to generate it "
              "(or invoke again with 'generate the reviewer pack').")


if __name__ == "__main__":
    main()
