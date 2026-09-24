#!/usr/bin/env python
"""Validate the seeded workspace against the manifest, including hybrid
retrieval targets via the VFS backend's grep.

Usage: python scripts/validate_seed.py --workspace-id accrual_review_demo_2026_06
"""
import argparse
import json
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.demo_agent.backend import grep_text
from src.mockdata import load_manifest
from src.seeding import validate_seed
from src.storage.atlas_repository import AtlasRepository
from src.storage.s3_repository import S3Repository


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", required=True)
    args = ap.parse_args()

    settings = load_settings(require_real=True)
    result = validate_seed(AtlasRepository(settings), S3Repository(settings),
                           load_manifest(), args.workspace_id,
                           search_fn=partial(grep_text, settings))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
