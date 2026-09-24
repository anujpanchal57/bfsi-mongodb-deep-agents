"""In-memory repository with the same surface as AtlasRepository.

Non-production: unit tests and offline development only.
"""
from __future__ import annotations

from typing import Any

from src.models import utcnow


class InMemoryRepository:
    """Drop-in for AtlasRepository in tests."""

    def __init__(self, settings=None):
        self.settings = settings
        self.store: dict[str, dict[str, dict]] = {
            k: {} for k in
            ("workspaces", "artifacts", "runs", "handoffs", "packs")
        }
        self.vfs_chunks: dict[str, dict] = {}  # source_path -> doc

    def upsert(self, coll: str, doc: dict) -> None:
        doc = dict(doc)
        doc["updated_at"] = utcnow()
        self.store[coll][doc["_id"]] = doc

    def patch(self, coll: str, _id: str, patch: dict) -> None:
        if _id in self.store[coll]:
            self.store[coll][_id].update(patch)
            self.store[coll][_id]["updated_at"] = utcnow()

    def get(self, coll: str, _id: str) -> dict | None:
        return self.store[coll].get(_id)

    def _match(self, doc: dict, filt: dict) -> bool:
        for k, v in filt.items():
            cur: Any = doc
            for part in k.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return False
                cur = cur[part]
            if cur != v:
                return False
        return True

    def find(self, coll: str, filt: dict, limit: int = 100) -> list[dict]:
        return [d for d in self.store[coll].values() if self._match(d, filt)][:limit]

    def count(self, coll: str, filt: dict) -> int:
        return len(self.find(coll, filt, limit=10**9))

    def delete_where(self, coll: str, filt: dict) -> int:
        doomed = [k for k, d in self.store[coll].items() if self._match(d, filt)]
        for k in doomed:
            del self.store[coll][k]
        return len(doomed)

    def delete_vfs_chunks(self, source_path_prefix: str) -> int:
        doomed = [k for k in self.vfs_chunks if k.startswith(source_path_prefix)]
        for k in doomed:
            del self.vfs_chunks[k]
        return len(doomed)

    def vfs_chunk_count(self, source_path_prefix: str) -> int:
        return sum(1 for k in self.vfs_chunks if k.startswith(source_path_prefix))

    def ping(self) -> bool:
        return True
