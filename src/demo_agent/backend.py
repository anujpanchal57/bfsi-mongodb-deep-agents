"""MongoFilesystemBackend construction + seed-time sync verification.

The backend owns the searchable chunk store (Atlas) and treats S3 as the
source of truth. Embeddings: the package default — AWS Bedrock
amazon.titan-embed-text-v2:0 @ 1024 dims via the boto3 credential chain
(EMBEDDING_PROVIDER=bedrock); OpenAI is the documented alternative.
"""
from __future__ import annotations

from src.config import Settings, load_settings

SDK_HINT = (
    "Install the platform extras first: pip install -e \".[platform]\" "
    "(agent-engine-sdk-langgraph currently ships via the private index or "
    "wheels/ — see deploy/README.md)")


def create_backend(settings: Settings | None = None):
    settings = settings or load_settings(require_real=True)
    try:
        from langchain_mongodb_deepagents_vfs import MongoFilesystemBackend
    except ImportError as exc:
        raise RuntimeError(SDK_HINT) from exc
    return MongoFilesystemBackend(
        s3_bucket_name=settings.s3_bucket,
        mongodb_connection_string=settings.mongodb_uri,
        s3_prefix=settings.s3_prefix,
        aws_region=settings.aws_region,
    )


def sync_and_verify(settings: Settings, warmup_query: str = "accrual") -> dict:
    """Block until the backend's initial sync finishes, then report health.

    A partially failed sync or a watcher that never started leaves a
    collection that looks healthy but is quietly incomplete — surface both.
    """
    backend = create_backend(settings)
    try:
        backend.grep(warmup_query)  # blocks until first sync completes
        init_errors = list(getattr(backend, "init_errors", None) or [])
        report = getattr(backend, "initial_sync_report", None)
        failed = getattr(report, "failed", None) if report else None
        return {
            "ok": not init_errors and not failed,
            "init_errors": init_errors,
            "sync_failed_objects": failed,
        }
    finally:
        backend.stop()


def grep_text(settings: Settings, query: str, top_k: int = 5) -> list[dict]:
    """One-shot hybrid grep for seed validation. Returns plain dicts."""
    backend = create_backend(settings)
    try:
        result = backend.grep(query)
        if getattr(result, "error", None):
            raise RuntimeError(f"grep failed: {result.error}")
        return [{"path": m.get("path"), "line": m.get("line"),
                 "text": m.get("text", "")} for m in (result.matches or [])][:top_k]
    finally:
        backend.stop()
