"""HTTP client for invoking the deployed/dev agent.

Isolated on purpose: the invoke route/shape is the one platform contract we
code against — adjust HERE only. Uses stdlib urllib so the UI and CLI work
without the platform extras installed.

Contract (docs: Invoke an Agent):
- deployed: POST {base}/api/v1/projects/{project_id}/workspaces/{workspace_id}/invoke
- local dev (`agentengine dev up` UI): POST {base}/invoke   (same body)
- body: {"message": str, "payload": dict?}   (payload = JSON metadata)
- session: X-Session-ID request header; the platform returns it in the same
  response header. Reusing session IDs reuses sandbox reservations.
- auth: Authorization: Bearer <api key>
"""
from __future__ import annotations

import json
import urllib.request
import uuid
from pathlib import Path

from src.config import Settings

DEFAULT_BASE_URL = "https://agentengine.mongodb.com"


class PlatformNotConfigured(RuntimeError):
    pass


def _state_json_ids() -> tuple[str, str]:
    """Read project/workspace IDs from .agentengine/state.json (agentengine init)."""
    state = Path(__file__).resolve().parent.parent / ".agentengine" / "state.json"
    if state.is_file():
        try:
            data = json.loads(state.read_text())
            return data.get("project_id", ""), data.get("workspace_id", "")
        except (json.JSONDecodeError, OSError):
            pass
    return "", ""


def _invoke_url(settings: Settings) -> str:
    base = (settings.agent_engine_url or "").rstrip("/")
    project_id = settings.agent_engine_project_id
    workspace_id = settings.agent_engine_workspace_id
    if not (project_id and workspace_id):
        project_id, workspace_id = _state_json_ids()
    if project_id and workspace_id:
        base = base or DEFAULT_BASE_URL
        return (f"{base}/api/v1/projects/{project_id}"
                f"/workspaces/{workspace_id}/invoke")
    if base:
        return f"{base}/invoke"  # local `agentengine dev up` UI
    raise PlatformNotConfigured(
        "Agent endpoint is not configured. Run `agentengine dev up` and set "
        "AGENT_ENGINE_URL to the printed ui URL, or run `agentengine init` "
        "(writes .agentengine/state.json) / set AGENT_ENGINE_PROJECT_ID and "
        "AGENT_ENGINE_WORKSPACE_ID for the deployed agent.")


def invoke_agent(settings: Settings, message: str, session_id: str | None = None,
                 payload: dict | None = None, timeout_s: int = 300) -> dict:
    """Invoke the agent on the platform (deployed or `agentengine dev up`).

    The chat message carries the user's request; structured metadata rides in
    the top-level `payload` object. Session continuity is via the
    X-Session-ID header, not the payload.
    """
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    body: dict = {"message": message}
    if payload:
        body["payload"] = payload
    req = urllib.request.Request(
        _invoke_url(settings),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "X-Session-ID": session_id,
                 **({"Authorization": f"Bearer {settings.agent_engine_api_key}"}
                    if settings.agent_engine_api_key else {})},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        result = json.loads(resp.read())
        result.setdefault("session_id", resp.headers.get("X-Session-ID", session_id))
        return result


def platform_health(settings: Settings, timeout_s: int = 15) -> str:
    """Best-effort reachability probe of the configured base URL.

    No documented health endpoint exists; for real status use
    `agentengine dev status` (local) or `agentengine deploy get` (deployed).
    """
    base = settings.agent_engine_url or DEFAULT_BASE_URL
    try:
        req = urllib.request.Request(
            base,
            headers=({"Authorization": f"Bearer {settings.agent_engine_api_key}"}
                     if settings.agent_engine_api_key else {}))
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return f"reachable ({resp.status})"
    except Exception as exc:
        return f"error: {exc}"
