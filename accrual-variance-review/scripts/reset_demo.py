#!/usr/bin/env python
"""Reset ONLY the demo namespace (workspace docs + configured S3 demo prefix).
Never touches unrelated databases, collections, or S3 prefixes.

Usage: python scripts/reset_demo.py --workspace-id accrual_review_demo_2026_06 --confirm
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.seeding import reset_demo_namespace
from src.storage.atlas_repository import AtlasRepository
from src.storage.s3_repository import S3Repository


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", required=True)
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()
    if not args.confirm:
        sys.exit("Pass --confirm to reset the demo namespace.")

    settings = load_settings()
    if settings.workspace_id != args.workspace_id:
        print(f"Warning: resetting '{args.workspace_id}' while "
              f"DEMO_WORKSPACE_ID is '{settings.workspace_id}'.")
    repo = AtlasRepository(settings)
    s3 = S3Repository(settings)
    report = reset_demo_namespace(repo, s3, args.workspace_id,
                                  settings.dataset_version)
    print("Reset boundary: workspace-scoped Atlas docs + S3 prefix "
          f"'{settings.s3_prefix}' only.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
