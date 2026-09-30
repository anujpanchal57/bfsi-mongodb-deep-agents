"""Seed data (AC-8, AC-9, AC-11): determinism, S3 verify, consistency, reset
isolation, idempotent reseed. Backend sync/retrieval validation are covered
by the platform integration tests (need real Atlas + S3 + Bedrock)."""
import hashlib

from src.mockdata import cleanup_staging, generate_source_artifacts, load_manifest
from src.seeding import (reset_demo_namespace, run_seed, upload_and_verify)


def test_generation_is_deterministic(tmp_path):
    manifest = load_manifest()
    g1 = generate_source_artifacts(manifest, tmp_path / "a")
    g2 = generate_source_artifacts(manifest, tmp_path / "b")
    for lid in g1["files"]:
        assert g1["files"][lid]["sha256"] == g2["files"][lid]["sha256"]
        assert g1["files"][lid]["artifact_id"] == g2["files"][lid]["artifact_id"]


def test_upload_verify_fails_on_hash_mismatch(seeded):
    s3 = seeded["s3"]
    manifest = load_manifest()
    gen = generate_source_artifacts(manifest)
    f = next(iter(gen["files"].values()))
    f["path"].write_bytes(b"corrupted")
    f["sha256"] = hashlib.sha256(b"original").hexdigest()
    try:
        failed = False
        try:
            upload_and_verify(s3, gen)
        except RuntimeError:
            failed = True
        assert failed, "hash mismatch must stop the pipeline before Atlas writes"
    finally:
        cleanup_staging(gen)


def test_variance_consistent_across_artifacts(seeded):
    import csv, io
    s3, repo = seeded["s3"], seeded["repo"]
    arts = repo.find("artifacts", {"workspace_id": seeded["workspace_id"]})
    extracts = [a for a in arts if a["artifact_type"] == "accrual_extract"]
    assert len(extracts) == 2
    for a in extracts:
        row = list(csv.DictReader(io.StringIO(s3.get(a["s3_key"]).decode())))[0]
        assert float(row["expected_amount"]) - float(row["booked_amount"]) \
            == float(row["variance"])


def test_reseed_is_idempotent(seeded):
    report = run_seed(seeded["repo"], seeded["s3"], reset=False)
    assert report["ok"]
    assert report["artifact_count"] == 7


def test_offline_seed_notes_retrieval_skipped(seeded):
    report = run_seed(seeded["repo"], seeded["s3"], reset=False)
    assert report["backend_sync"] == "skipped (offline mode)"
    assert any("retrieval checks skipped" in n
               for n in report["validation"]["notes"])


def test_reset_isolation(seeded):
    """Reset deletes only the demo namespace; unrelated docs and VFS chunks
    outside the demo prefix survive."""
    repo = seeded["repo"]
    repo.upsert("workspaces", {"_id": "other_workspace", "process": "other"})
    repo.upsert("artifacts", {"_id": "other-art", "workspace_id": "other_workspace"})
    repo.vfs_chunks["agent-engine-demo/source/2026-06/x.md"] = {}
    repo.vfs_chunks["other-tenant/source/y.md"] = {}
    deleted = reset_demo_namespace(repo, seeded["s3"],
                                   seeded["workspace_id"], "v1")
    assert deleted["artifacts"] == 7
    assert deleted["vfs_chunks"] == 1
    assert repo.get("workspaces", "other_workspace") is not None
    assert repo.get("artifacts", "other-art") is not None
    assert "other-tenant/source/y.md" in repo.vfs_chunks
    assert repo.get("workspaces", seeded["workspace_id"]) is None


def test_no_human_supplied_files_needed(seeded):
    """Clean-checkout seed generated all 7 artifacts + evidence index in S3."""
    keys = seeded["s3"].list_keys("")
    assert len([k for k in keys if k.startswith("agent-engine-demo/source/")]) == 7
    assert any(k.endswith("manifests/v1/evidence_index.json") for k in keys)
