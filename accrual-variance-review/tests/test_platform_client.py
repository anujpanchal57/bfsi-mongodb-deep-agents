"""Offline checks for the platform invoke contract (URL resolution, body,
headers). No network: urllib.request.urlopen is stubbed."""
import json

import src.platform_client as pc
from src.config import Settings


def _settings(**kw):
    base = dict(agent_engine_url="", agent_engine_api_key="",
                agent_engine_project_id="", agent_engine_workspace_id="")
    base.update(kw)
    return Settings(**base)


def test_local_dev_url():
    s = _settings(agent_engine_url="http://localhost:3000/")
    assert pc._invoke_url(s) == "http://localhost:3000/invoke"


def test_deployed_url_from_env_ids():
    s = _settings(agent_engine_project_id="p1", agent_engine_workspace_id="w1")
    assert pc._invoke_url(s) == (
        "https://agentengine.mongodb.com/api/v1/projects/p1"
        "/workspaces/w1/invoke")


def test_deployed_url_from_state_json(tmp_path, monkeypatch):
    state = tmp_path / ".agentengine" / "state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"project_id": "p2", "workspace_id": "w2"}))
    monkeypatch.setattr(pc.Path, "resolve",
                        lambda self: tmp_path / "src" / "platform_client.py")
    s = _settings()
    assert pc._invoke_url(s).endswith("/projects/p2/workspaces/w2/invoke")


def test_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(pc, "_state_json_ids", lambda: ("", ""))
    s = _settings()
    try:
        pc._invoke_url(s)
    except pc.PlatformNotConfigured:
        return
    raise AssertionError("expected PlatformNotConfigured")


def test_invoke_body_and_headers(monkeypatch):
    captured = {}

    class Resp:
        headers = {"X-Session-ID": "sess-1"}

        def read(self):
            return json.dumps({"success": True, "response": "hi"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = dict(req.header_items())
        return Resp()

    monkeypatch.setattr(pc.urllib.request, "urlopen", fake_urlopen)
    s = _settings(agent_engine_url="http://localhost:3000")
    out = pc.invoke_agent(s, "Review the variance.", session_id="sess-1",
                          payload={"workspace_id": "ws"})
    assert captured["url"] == "http://localhost:3000/invoke"
    assert captured["body"] == {"message": "Review the variance.",
                                "payload": {"workspace_id": "ws"}}
    assert captured["headers"].get("X-session-id") == "sess-1"
    assert out["session_id"] == "sess-1"
