"""Offline checks for build_llm() provider wiring. No network: construction
of every client is lazy; AWS creds are faked via env for the bedrock branch."""
import os

import pytest

from src.demo_agent.llm import DEFAULT_MODELS, build_llm


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL",
                "LLM_AUTH_HEADER",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_bedrock_default_provider(clean_env):
    clean_env.setenv("AWS_ACCESS_KEY_ID", "test")
    clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test")
    from langchain_aws import ChatBedrockConverse
    llm = build_llm()
    assert isinstance(llm, ChatBedrockConverse)
    assert llm.model_id == DEFAULT_MODELS["bedrock"]
    assert llm.region_name == "us-east-1"


def test_bedrock_requires_aws_credentials(clean_env, monkeypatch):
    clean_env.setenv("LLM_PROVIDER", "bedrock")
    import boto3
    monkeypatch.setattr(boto3, "Session",
                        lambda *a, **k: type("S", (), {"get_credentials": lambda self: None})())
    with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID"):
        build_llm()


def test_bedrock_model_override(clean_env):
    clean_env.setenv("AWS_ACCESS_KEY_ID", "test")
    clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test")
    clean_env.setenv("LLM_MODEL", "us.amazon.nova-pro-v1:0")
    clean_env.setenv("AWS_REGION", "us-west-2")
    llm = build_llm()
    assert llm.model_id == "us.amazon.nova-pro-v1:0"
    assert llm.region_name == "us-west-2"


def test_openai_branch(clean_env):
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("LLM_API_KEY", "test")
    from langchain_openai import ChatOpenAI
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == DEFAULT_MODELS["openai"]


def test_anthropic_branch(clean_env):
    clean_env.setenv("LLM_PROVIDER", "anthropic")
    clean_env.setenv("LLM_API_KEY", "test")
    from langchain_anthropic import ChatAnthropic
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == DEFAULT_MODELS["anthropic"]


def test_api_key_providers_require_key(clean_env):
    clean_env.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        build_llm()


def test_unknown_provider_rejected(clean_env):
    clean_env.setenv("LLM_PROVIDER", "wat")
    with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER"):
        build_llm()


def test_gateway_base_url_openai(clean_env):
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("LLM_API_KEY", "test")
    clean_env.setenv("LLM_BASE_URL", "https://llm-gw.corp.example.com/v1")
    llm = build_llm()
    assert llm.openai_api_base == "https://llm-gw.corp.example.com/v1"


def test_gateway_base_url_anthropic(clean_env):
    clean_env.setenv("LLM_PROVIDER", "anthropic")
    clean_env.setenv("LLM_API_KEY", "test")
    clean_env.setenv("LLM_BASE_URL", "https://llm-gw.corp.example.com")
    llm = build_llm()
    assert llm.anthropic_api_url == "https://llm-gw.corp.example.com"


def test_gateway_custom_auth_header(clean_env):
    """APIM-style gateway: key travels in the header LLM_AUTH_HEADER names."""
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("LLM_API_KEY", "sub-key-123")
    clean_env.setenv("LLM_BASE_URL", "https://llm-gw.corp.example.com/v1")
    clean_env.setenv("LLM_AUTH_HEADER", "api-key")
    llm = build_llm()
    assert llm.default_headers == {"api-key": "sub-key-123"}


def test_gateway_base_url_ignored_for_bedrock(clean_env):
    clean_env.setenv("AWS_ACCESS_KEY_ID", "test")
    clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test")
    clean_env.setenv("LLM_BASE_URL", "https://llm-gw.corp.example.com")
    from langchain_aws import ChatBedrockConverse
    llm = build_llm()
    assert isinstance(llm, ChatBedrockConverse)  # no base_url applied
