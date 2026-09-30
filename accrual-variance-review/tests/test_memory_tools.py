"""Offline checks for the memory tools. app.memory is stubbed — no platform,
no Voyage, no Atlas."""
import json

from src.demo_agent.memory_tools import register_memory


class _FakeMemory:
    def __init__(self):
        self.saved = []

    def build_context(self, query, max_tokens, enabled_sources):
        assert enabled_sources == {"episodic", "semantic", "taxonomic"}
        return type("Ctx", (), {"formatted_context": f"memories for: {query}"})()

    def save_semantic(self, label, text):
        self.saved.append((label, text))


class _FakeApp:
    def __init__(self):
        self.memory = _FakeMemory()
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


def _app():
    app = _FakeApp()
    register_memory(app)
    return app


def test_recall_context_returns_formatted_context():
    app = _app()
    out = app.tools["recall_context"]("past CON-7781 reviews")
    assert "past CON-7781 reviews" in out


def test_remember_fact_saves_semantic_memory():
    app = _app()
    out = json.loads(app.tools["remember_fact"]("cc-410-reviewer",
                                                "The reviewer for CC-410 is Priya."))
    assert out == {"saved": "cc-410-reviewer"}
    assert app.memory.saved == [("cc-410-reviewer", "The reviewer for CC-410 is Priya.")]


def test_remember_fact_refuses_approval_content():
    """The human boundary extends into memory: decisions are never stored."""
    app = _app()
    for label, text in [
        ("variance-decision", "Approved the INR 35,000 variance."),
        ("june-item", "Post the adjustment and close the item."),
        ("signoff", "Reviewer signed off on CON-7781."),
    ]:
        out = json.loads(app.tools["remember_fact"](label, text))
        assert out["saved"] is None, text
        assert "refused" in out["error"]
    assert app.memory.saved == []
