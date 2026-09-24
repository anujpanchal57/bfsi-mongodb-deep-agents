#!/usr/bin/env python
"""Seed the demo: generate artifacts -> upload/verify S3 -> register in Atlas
-> VFS backend sync (chunk/embed/index; Bedrock Titan by default) -> seed
workflow state -> validate via hybrid grep.

Usage:
  python scripts/seed_mock_data.py --dataset-version v1 --reset
  python scripts/seed_mock_data.py --reset --offline   # tests/dev only:
      no backend sync, no retrieval validation (non-production)
"""
import argparse
import json
import logging
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.seeding import run_seed
from src.storage.atlas_repository import AtlasRepository
from src.storage.memory_repository import InMemoryRepository
from src.storage.s3_repository import S3Repository


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-version", default="v1")
    ap.add_argument("--workspace-id", default=None)
    ap.add_argument("--reset", action="store_true",
                    help="Delete ONLY the demo namespace before seeding.")
    ap.add_argument("--offline", action="store_true",
                    help="Skip backend sync + retrieval validation "
                         "(unit tests / offline dev only, non-production).")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.offline:
        settings = load_settings()
        settings.s3_backend = "local"
        repo = InMemoryRepository(settings)
        s3 = S3Repository(settings)
        sync_fn = search_fn = None
        print("OFFLINE MODE — no backend sync, no retrieval validation.")
    else:
        settings = load_settings(require_real=True)
        from src.demo_agent.backend import grep_text, sync_and_verify
        repo = AtlasRepository(settings)
        s3 = S3Repository(settings)
        sync_fn = partial(sync_and_verify, settings)
        search_fn = partial(grep_text, settings)

    report = run_seed(repo, s3,
                      dataset_version=args.dataset_version,
                      workspace_id=args.workspace_id,
                      reset=args.reset,
                      sync_fn=sync_fn, search_fn=search_fn)

    print("\n=== Seed manifest summary ===")
    print(json.dumps({k: v for k, v in report.items() if k != "reset"},
                     indent=2, default=str))
    if report["reset"]:
        print("reset:", json.dumps(report["reset"]))
    if not report["ok"]:
        sys.exit("Seed validation FAILED — see errors above.")
    print("Seed OK.")


if __name__ == "__main__":
    main()
