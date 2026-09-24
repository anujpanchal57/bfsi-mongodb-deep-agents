"""HTTP client for invoking the deployed/dev agent.

Isolated on purpose: the exact invoke route/shape is the one platform
contract we code against blind — adjust HERE only. Uses stdlib urllib so the
UI and CLI work without the platform extras installed.
"""
from __future__ import annotations

import json
import urllib.request
import uuid

from src.config import Settings


class PlatformNotConfigured(RuntimeError):
    pass


def invoke_agent(settings: Settings, message: str, session_id: str | None = None,
                 payload: dict | None = None, timeout_s: int = 300) -> dict:
    """Invoke the agent on the platform (deployed or `agentengine dev up`).

    Request follows the platform's payload contract: structured input rides
    in input.payload; the chat message carries the user's request.
    """
    if not settings.agent_engine_url:
        raise PlatformNotConfigured(
            "AGENT_ENGINE_URL is not set. Run `agentengine dev up` locally or "
            "set it to the deployed agent's URL.")
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    body = {
        "input": {
            "message": message,
            "payload": {"session_id": session_id, **(payload or {})},
        }
    }
    req = urllib.request.Request(
        f"{settings.agent_engine_url.rstrip('/')}/invoke",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {settings.agent_engine_api_key}"}
                    if settings.agent_engine_api_key else {})},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read())


def platform_health(settings: Settings, timeout_s: int = 15) -> str:
    if not settings.agent_engine_url:
        return "not_configured"
    try:
        req = urllib.request.Request(
            f"{settings.agent_engine_url.rstrip('/')}/health",
            headers=({"Authorization": f"Bearer {settings.agent_engine_api_key}"}
                     if settings.agent_engine_api_key else {}))
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return f"ok ({resp.status})"
    except Exception as exc:
        return f"error: {exc}"
