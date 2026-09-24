"""Configuration. Fail fast with a clear message when required variables are missing."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv optional
    pass


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    mongodb_uri: str = ""
    mongodb_database: str = "agent_engine_demo"
    workspace_collection: str = "agent_workspaces"
    artifacts_collection: str = "workspace_artifacts"
    runs_collection: str = "agent_runs"
    handoffs_collection: str = "agent_handoffs"
    packs_collection: str = "reviewer_packs"
    aws_region: str = "ap-south-1"
    s3_bucket: str = ""
    s3_prefix: str = "agent-engine-demo/"
    dataset_version: str = "v1"
    workspace_id: str = "accrual_review_demo_2026_06"
    # VFS backend embedding provider: bedrock (default) | openai |
    # deterministic (unit tests / offline only, non-production)
    embedding_provider: str = "bedrock"
    embedding_model: str = ""
    llm_provider: str = "openai"
    llm_model: str = ""
    agent_engine_url: str = ""     # deployed agent or local `agentengine dev up`
    agent_engine_api_key: str = ""
    s3_backend: str = "s3"  # "local" = unit tests only
    local_s3_root: str = "data/generated/local_s3"
    log_level: str = "INFO"

    # VFS backend's own Atlas location (from langchain-mongodb-deepagents-vfs
    # defaults; used by reset/diagnose to scope to demo-prefix chunks only).
    vfs_db: str = "langchain_mongodb_deepagents_vfs"
    vfs_chunks_collection: str = "demo_chunks"

    extra: dict = field(default_factory=dict)


_ENV_MAP = {
    "MONGODB_URI": "mongodb_uri",
    "MONGODB_DATABASE": "mongodb_database",
    "MONGODB_WORKSPACE_COLLECTION": "workspace_collection",
    "MONGODB_ARTIFACTS_COLLECTION": "artifacts_collection",
    "MONGODB_RUNS_COLLECTION": "runs_collection",
    "MONGODB_HANDOFFS_COLLECTION": "handoffs_collection",
    "MONGODB_PACKS_COLLECTION": "packs_collection",
    "AWS_REGION": "aws_region",
    "S3_BUCKET": "s3_bucket",
    "S3_PREFIX": "s3_prefix",
    "DEMO_DATASET_VERSION": "dataset_version",
    "DEMO_WORKSPACE_ID": "workspace_id",
    "EMBEDDING_PROVIDER": "embedding_provider",
    "EMBEDDING_MODEL": "embedding_model",
    "LLM_PROVIDER": "llm_provider",
    "LLM_MODEL": "llm_model",
    "AGENT_ENGINE_URL": "agent_engine_url",
    "AGENT_ENGINE_API_KEY": "agent_engine_api_key",
    "S3_BACKEND": "s3_backend",
    "LOCAL_S3_ROOT": "local_s3_root",
    "LOG_LEVEL": "log_level",
}


def load_settings(require_real: bool = False) -> Settings:
    """Load settings from environment.

    require_real=True enforces the conference-demo path (real Atlas + S3 +
    real embedding provider). Tests and offline dev use require_real=False.
    """
    s = Settings()
    for env, attr in _ENV_MAP.items():
        val = os.environ.get(env)
        if val:
            setattr(s, attr, val)

    if not s.s3_prefix.endswith("/"):
        s.s3_prefix += "/"

    if require_real:
        missing = []
        if not s.mongodb_uri:
            missing.append("MONGODB_URI")
        if s.s3_backend == "s3" and not s.s3_bucket:
            missing.append("S3_BUCKET (or set S3_BACKEND=local for tests only)")
        if s.embedding_provider == "deterministic":
            missing.append("EMBEDDING_PROVIDER (deterministic mode is non-production)")
        if missing:
            raise ConfigError(
                "Missing required configuration for the real demo path: "
                + ", ".join(missing)
            )
    return s


def collections(s: Settings) -> dict:
    return {
        "workspaces": s.workspace_collection,
        "artifacts": s.artifacts_collection,
        "runs": s.runs_collection,
        "handoffs": s.handoffs_collection,
        "packs": s.packs_collection,
    }
