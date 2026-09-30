"""LLM connection. Provider/model come from the environment (LLM_PROVIDER,
LLM_MODEL). Credentials: openai/anthropic use LLM_API_KEY; bedrock uses the
boto3 default credential chain (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY [/
AWS_SESSION_TOKEN], profile, or role) — no LLM_API_KEY. Secrets live in .env
locally and in platform secrets when deployed — never in source.

The model is passed UNWRAPPED to app.deep_agent(); the SDK wraps it in
SecureWrappedLLM internally. Do not wrap with app.llm() (double-registration
fails startup).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

DEFAULT_MODELS = {
    "bedrock": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # inference profile
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
}


def build_llm(temperature: float = 0) -> BaseChatModel:
    provider = os.environ.get("LLM_PROVIDER", "bedrock").lower()
    if provider not in DEFAULT_MODELS:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={provider!r}; expected one of: "
            + ", ".join(DEFAULT_MODELS))
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider]

    if provider == "bedrock":
        import boto3
        if boto3.Session().get_credentials() is None:
            raise RuntimeError(
                "LLM_PROVIDER=bedrock but no AWS credentials resolved. Set "
                "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (/ AWS_SESSION_TOKEN) "
                "in .env locally, or `agentengine secret set` them when deployed.")
        from langchain_aws import ChatBedrockConverse
        return ChatBedrockConverse(
            model_id=model,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            temperature=temperature)

    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is missing; add it to .env or platform secrets "
            "(agentengine secret set LLM_API_KEY)")

    # Optional corporate LLM gateway: an OpenAI- or Anthropic-compatible
    # endpoint (LLM_PROVIDER selects the API dialect). The gateway host must
    # also be allowlisted in agent.yaml egress when deployed.
    base_url = os.environ.get("LLM_BASE_URL") or None
    # Some gateways (e.g. Azure API Management) require the key in a custom
    # header such as `api-key` instead of / in addition to `Authorization:
    # Bearer`. LLM_AUTH_HEADER names that header; the key value is reused.
    auth_header = os.environ.get("LLM_AUTH_HEADER") or None
    extra_headers = {auth_header: api_key} if auth_header else None

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key, base_url=base_url,
                             default_headers=extra_headers,
                             temperature=temperature)

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url,
                      default_headers=extra_headers, temperature=temperature)
