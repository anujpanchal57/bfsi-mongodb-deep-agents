#!/usr/bin/env python
"""Demo diagnostics: platform reachability, Atlas, collections, VFS backend
sync/indexes, S3, seed workspace, known hybrid retrieval query."""
import json
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import collections, load_settings
from src.platform_client import platform_health
from src.storage.atlas_repository import AtlasRepository
from src.storage.s3_repository import S3Repository


def main():
    settings = load_settings()
    out: dict = {"platform": platform_health(settings)}

    try:
        repo = AtlasRepository(settings)
        repo.ping()
        out["atlas"] = "ok"
    except Exception as exc:
        out["atlas"] = f"error: {exc}"
        print(json.dumps(out, indent=2))
        sys.exit(1)

    existing = set(repo.db.list_collection_names())
    out["collections"] = {name: ("ok" if name in existing else "missing")
                          for name in collections(settings).values()}

    try:
        s3 = S3Repository(settings)
        s3.health()
        out["s3"] = "ok"
    except Exception as exc:
        out["s3"] = f"error: {exc}"

    out["vfs_chunks_under_demo_prefix"] = repo.vfs_chunk_count(settings.s3_prefix)

    ws = repo.get("workspaces", settings.workspace_id)
    out["seed_workspace"] = "ok" if ws else f"missing: {settings.workspace_id}"

    if ws and out.get("s3") == "ok":
        try:
            from src.demo_agent.backend import grep_text, sync_and_verify
            out["backend_sync"] = sync_and_verify(settings)
            hits = grep_text(settings, "CON-7781 accrual variance")
            out["known_retrieval_query"] = {
                "results": len(hits),
                "top_path": hits[0]["path"] if hits else None,
            }
        except Exception as exc:
            out["backend"] = f"error: {exc}"

    print(json.dumps(out, indent=2, default=str))
    failed = (out["atlas"] != "ok" or out["s3"] != "ok"
              or out["seed_workspace"] != "ok"
              or any(v == "missing" for v in out["collections"].values()))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
