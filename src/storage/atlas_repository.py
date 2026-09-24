"""Atlas repository: business-state access for workspaces, artifacts, runs,
handoffs, and reviewer packs. Upsert-based writes for idempotency.

Searchable chunks/embeddings are owned by langchain-mongodb-deepagents-vfs
(MongoFilesystemBackend) in its own database/collection — not here.
"""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.collection import Collection

from src.config import Settings, collections
from src.models import utcnow


class AtlasRepository:
    def __init__(self, settings: Settings, client: MongoClient | None = None):
        self.settings = settings
        self.client = client or MongoClient(settings.mongodb_uri)
        self.db = self.client[settings.mongodb_database]
        self.cols = collections(settings)

    def _c(self, name: str) -> Collection:
        return self.db[self.cols[name]]

    def upsert(self, coll: str, doc: dict) -> None:
        doc = dict(doc)
        doc["updated_at"] = utcnow()
        self._c(coll).replace_one({"_id": doc["_id"]}, doc, upsert=True)

    def patch(self, coll: str, _id: str, patch: dict) -> None:
        patch = dict(patch)
        patch["updated_at"] = utcnow()
        self._c(coll).update_one({"_id": _id}, {"$set": patch})

    def get(self, coll: str, _id: str) -> dict | None:
        return self._c(coll).find_one({"_id": _id})

    def find(self, coll: str, filt: dict, limit: int = 100) -> list[dict]:
        return list(self._c(coll).find(filt).limit(limit))

    def count(self, coll: str, filt: dict) -> int:
        return self._c(coll).count_documents(filt)

    def delete_where(self, coll: str, filt: dict) -> int:
        return self._c(coll).delete_many(filt).deleted_count

    def delete_vfs_chunks(self, source_path_prefix: str) -> int:
        """Reset support: delete VFS backend chunks under the demo prefix."""
        col = self.client[self.settings.vfs_db][self.settings.vfs_chunks_collection]
        return col.delete_many(
            {"source_path": {"$regex": f"^{source_path_prefix}"}}).deleted_count

    def vfs_chunk_count(self, source_path_prefix: str) -> int:
        col = self.client[self.settings.vfs_db][self.settings.vfs_chunks_collection]
        return col.count_documents(
            {"source_path": {"$regex": f"^{source_path_prefix}"}})

    def ping(self) -> bool:
        self.client.admin.command("ping")
        return True
