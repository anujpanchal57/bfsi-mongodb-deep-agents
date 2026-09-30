"""Seed pipeline (FR-3a): generate -> upload/verify S3 -> register in Atlas
-> backend sync (chunk/embed/index owned by langchain-mongodb-deepagents-vfs)
-> seed workflow state -> validate. Idempotent; reset is scoped to the demo
namespace only (workspace-prefixed business docs, demo-prefix VFS chunks,
and objects under the configured S3 prefix).

Chunking/embedding/indexing are NOT done here — the VFS backend owns them
(Bedrock Titan embeddings by default). Offline/unit-test paths pass
sync_fn=None and search_fn=None, which skips backend sync and retrieval
validation.
"""
from __future__ import annotations

import json
from typing import Callable

from src.mockdata import (build_evidence_index, cleanup_staging,
                          generate_source_artifacts, load_manifest)
from src.models import new_workspace, utcnow
from src.storage.s3_repository import sha256_bytes

SearchFn = Callable[[str, int], list[dict]]


def reset_demo_namespace(repo, s3, workspace_id: str, dataset_version: str) -> dict:
    """Delete ONLY demo-namespace data: business docs for this workspace,
    VFS backend chunks under the demo S3 prefix, and S3 objects under the
    configured demo prefix."""
    deleted = {}
    for coll in ("workspaces", "artifacts", "runs", "handoffs", "packs"):
        filt = ({"_id": workspace_id} if coll == "workspaces"
                else {"workspace_id": workspace_id})
        deleted[coll] = repo.delete_where(coll, filt)
    deleted["packs"] += repo.delete_where("packs", {"workspace_id": workspace_id})
    deleted["vfs_chunks"] = repo.delete_vfs_chunks(s3.settings.s3_prefix)
    deleted["s3_objects"] = s3.delete_prefix("")
    return deleted


def upload_and_verify(s3, gen: dict) -> dict:
    """Upload every generated artifact + the evidence index; verify hashes.

    Fails before any Atlas write if an object is missing or mismatched.
    """
    s3_uris = {}
    for lid, f in gen["files"].items():
        data = f["path"].read_bytes()
        s3_uris[lid] = s3.put(f["s3_key"], data)

    index_key = gen["manifest"]["evidence_index_key"]
    index_doc = build_evidence_index(gen, s3_uris)
    index_bytes = json.dumps(index_doc, indent=2).encode()
    s3.put(index_key, index_bytes)

    failures = []
    for lid, f in gen["files"].items():
        if not s3.exists(f["s3_key"]):
            failures.append(f"missing object: {f['s3_key']}")
        elif s3.hash(f["s3_key"]) != f["sha256"]:
            failures.append(f"hash mismatch: {f['s3_key']}")
    if not s3.exists(index_key) or s3.hash(index_key) != sha256_bytes(index_bytes):
        failures.append(f"evidence index missing/mismatched: {index_key}")
    if failures:
        raise RuntimeError("S3 upload verification failed: " + "; ".join(failures))
    return {"s3_uris": s3_uris, "evidence_index": index_doc,
            "evidence_index_key": index_key}


def register_artifacts(repo, gen: dict, s3_uris: dict, workspace_id: str) -> list[dict]:
    sc = gen["manifest"]["scenario"]
    registered = []
    for lid, f in gen["files"].items():
        doc = {
            "_id": f["artifact_id"],
            "artifact_id": f["artifact_id"],
            "workspace_id": workspace_id,
            "s3_key": f["s3_key"],
            "source_uri": s3_uris[lid],
            "filename": f["filename"],
            "artifact_type": f["artifact_type"],
            "period": f["period"],
            "entity": sc["entity"],
            "vendor": sc["vendor_id"],
            "contract": sc["contract_id"],
            "version": f["version"],
            "content_hash": f["sha256"],
            "ingestion_status": "registered",  # backend sync flips searchable state
            "tags": ["synthetic", "demo", f"dataset:{gen['manifest']['dataset_version']}"],
            "created_at": utcnow(),
        }
        repo.upsert("artifacts", doc)
        registered.append(doc)
    return registered


def seed_workflow_state(repo, manifest: dict, workspace_id: str) -> None:
    ws = manifest["workspace"]
    repo.upsert("workspaces", new_workspace(
        workspace_id, ws["period"], ws["entity"], ws["owner"]))
    repo.patch("workspaces", workspace_id, {
        "open_evidence_gaps": manifest["expected_evidence_gaps"]})


def validate_seed(repo, s3, manifest: dict, workspace_id: str,
                  search_fn: SearchFn | None = None) -> dict:
    """Fail if expected artifacts, values, or gaps are missing. Retrieval
    target checks run only when search_fn (backend grep) is provided."""
    errors: list[str] = []
    notes: list[str] = []

    ws = repo.get("workspaces", workspace_id)
    if not ws:
        errors.append(f"workspace '{workspace_id}' missing")
    expected_ids = {f["artifact_id"] for f in generate_expected_ids(manifest)}
    arts = repo.find("artifacts", {"workspace_id": workspace_id}, limit=1000)
    found_ids = {a["_id"] for a in arts}
    if expected_ids - found_ids:
        errors.append(f"missing artifacts: {sorted(expected_ids - found_ids)}")

    # Hash alignment between Atlas metadata and S3 objects.
    for a in arts:
        if a.get("s3_key") and s3.exists(a["s3_key"]):
            if s3.hash(a["s3_key"]) != a.get("content_hash"):
                errors.append(f"hash mismatch for {a['filename']}")

    # Variance value consistency inside the seeded extracts.
    import csv, io
    for a in arts:
        if a.get("artifact_type") == "accrual_extract" and a.get("s3_key"):
            rows = list(csv.DictReader(io.StringIO(s3.get(a["s3_key"]).decode())))
            for r in rows:
                booked, expected = float(r["booked_amount"]), float(r["expected_amount"])
                if abs((expected - booked) - float(r["variance"])) > 0.01:
                    errors.append(f"variance inconsistent in {a['filename']}")

    # Retrieval targets via the VFS backend's hybrid grep (real path only).
    if search_fn is not None:
        targets = manifest["retrieval_targets"]
        exact = search_fn(targets["exact_match"], 5)
        if not any(targets["exact_match"] in (m.get("text") or "")
                   for m in exact):
            errors.append("exact-match retrieval target not found")
        if not search_fn(targets["semantic"], 8):
            errors.append("semantic retrieval target returned no evidence")
    else:
        notes.append("retrieval checks skipped (no search_fn — offline mode)")

    gaps = (ws or {}).get("open_evidence_gaps", [])
    for g in manifest["expected_evidence_gaps"]:
        if g not in gaps:
            errors.append(f"expected evidence gap '{g}' missing")
    return {"ok": not errors, "errors": errors, "notes": notes,
            "artifacts": len(arts), "workspace_id": workspace_id}


def generate_expected_ids(manifest: dict) -> list[dict]:
    from src.mockdata import artifact_id
    return [{"artifact_id": artifact_id(manifest["dataset_version"],
                                        a["logical_id"])}
            for a in manifest["artifacts"]]


def run_seed(repo, s3, dataset_version: str = "v1",
             workspace_id: str | None = None, reset: bool = False,
             sync_fn: Callable[[], dict] | None = None,
             search_fn: SearchFn | None = None) -> dict:
    """Full seed pipeline.

    sync_fn: zero-arg callable that runs the VFS backend's initial sync and
    returns a health report (src.demo_agent.backend.sync_and_verify).
    search_fn: backend grep adapter for retrieval validation.
    Both are None only in offline/unit-test mode.
    """
    manifest = load_manifest()
    if dataset_version != manifest["dataset_version"]:
        raise ValueError(f"Unknown dataset version '{dataset_version}'; "
                         f"manifest has '{manifest['dataset_version']}'")
    workspace_id = workspace_id or manifest["workspace"]["workspace_id"]

    reset_report = None
    if reset:
        reset_report = reset_demo_namespace(repo, s3, workspace_id, dataset_version)

    gen = generate_source_artifacts(manifest)
    try:
        upload = upload_and_verify(s3, gen)  # hard-fails before Atlas writes
        registered = register_artifacts(repo, gen, upload["s3_uris"], workspace_id)
        seed_workflow_state(repo, manifest, workspace_id)
    finally:
        cleanup_staging(gen)

    sync_report = sync_fn() if sync_fn else "skipped (offline mode)"
    if isinstance(sync_report, dict) and not sync_report.get("ok"):
        raise RuntimeError(f"VFS backend sync failed: {sync_report}")
    if isinstance(sync_report, dict):
        for a in registered:
            repo.patch("artifacts", a["_id"], {"ingestion_status": "indexed"})

    validation = validate_seed(repo, s3, manifest, workspace_id, search_fn)
    return {
        "workspace_id": workspace_id,
        "dataset_version": dataset_version,
        "reset": reset_report,
        "artifact_count": len(registered),
        "vfs_chunk_count": repo.vfs_chunk_count(s3.settings.s3_prefix)
        if hasattr(repo, "vfs_chunk_count") else None,
        "backend_sync": sync_report,
        "validation": validation,
        "ok": validation["ok"],
    }
