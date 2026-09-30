import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Settings
from src.seeding import run_seed
from src.storage.memory_repository import InMemoryRepository
from src.storage.s3_repository import S3Repository
from src.tools import ToolContext


@pytest.fixture()
def settings(tmp_path):
    return Settings(s3_backend="local", local_s3_root=str(tmp_path / "s3"),
                    s3_bucket="demo-bucket", embedding_provider="deterministic")


@pytest.fixture()
def repo(settings):
    return InMemoryRepository(settings)


@pytest.fixture()
def s3(settings):
    return S3Repository(settings)


@pytest.fixture()
def seeded(settings, repo, s3):
    """Offline seed: no backend sync, no retrieval validation (both are
    owned by the VFS backend, which needs real Atlas + S3 + Bedrock)."""
    report = run_seed(repo, s3, reset=True)
    assert report["ok"], report
    return {"settings": settings, "repo": repo, "s3": s3,
            "workspace_id": report["workspace_id"]}


@pytest.fixture()
def ctx(seeded):
    return ToolContext(repo=seeded["repo"], s3=seeded["s3"],
                       settings=seeded["settings"])
