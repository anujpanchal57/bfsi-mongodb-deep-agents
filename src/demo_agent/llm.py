"""LLM connection. Provider/model/key come from the environment
(LLM_PROVIDER, LLM_MODEL, LLM_API_KEY); credentials live in .env locally and
in platform secrets when deployed — never in source.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def build_llm(temperature: float = 0) -> BaseChatModel:
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is missing; add it to .env or platform secrets "
            "(agentengine secret set LLM_API_KEY)")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=os.environ.get("LLM_MODEL", "claude-sonnet-4-5"),
            api_key=api_key, temperature=temperature)

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        api_key=api_key, temperature=temperature)
