#!/usr/bin/env python
"""Generate synthetic source artifacts locally (staging only) and print hashes.

Usage: python scripts/generate_source_artifacts.py [--out data/generated/staging]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mockdata import generate_source_artifacts, load_manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/generated/staging")
    args = ap.parse_args()

    manifest = load_manifest()
    gen = generate_source_artifacts(manifest, staging_dir=Path(args.out))
    print(f"Staged {len(gen['files'])} artifacts under {gen['staging_dir']} "
          "(staging only — the demo source of truth is S3):")
    for lid, f in gen["files"].items():
        print(f"  {f['s3_key']}  sha256={f['sha256'][:16]}…")


if __name__ == "__main__":
    main()
