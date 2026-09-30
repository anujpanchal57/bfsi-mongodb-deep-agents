"""Synthetic source-artifact generation from the versioned manifest.

Generates every demo source file deterministically. No external business
system is called and no real company data is used. Files are written to an
ephemeral local staging directory, then uploaded to S3; local staging is an
intermediate step only, never the demo source of truth.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "manifests" / "mock_accrual_v1.json"


def load_manifest(path: Path | str = MANIFEST_PATH) -> dict:
    return json.loads(Path(path).read_text())


def artifact_id(dataset_version: str, logical_id: str) -> str:
    digest = hashlib.sha1(f"{dataset_version}:{logical_id}".encode()).hexdigest()[:8]
    return f"art-{logical_id}-{digest}"


def render_artifact(logical_id: str, ws: dict, sc: dict) -> bytes:
    """Render one synthetic source artifact. All values cross-referenced."""
    cur, prior = sc["current_period"], sc["prior_period"]
    wid = ws["workspace_id"]
    header = f"workspace_id,period,entity,vendor_id,vendor_name,contract_id,gl_account,cost_center,booked_amount,expected_amount,variance,currency,invoice_status\n"

    if logical_id == "accrual_extract_current":
        row = (f"{wid},{cur},{sc['entity']},{sc['vendor_id']},\"{sc['vendor_name']}\","
               f"{sc['contract_id']},{sc['gl_account']},{sc['cost_center']},"
               f"{sc['booked_accrual']},{sc['expected_accrual']},{sc['variance']},"
               f"{sc['currency']},invoice_support_missing\n")
        return (header + row).encode()

    if logical_id == "accrual_extract_prior":
        row = (f"{wid},{prior},{sc['entity']},{sc['vendor_id']},\"{sc['vendor_name']}\","
               f"{sc['contract_id']},{sc['gl_account']},{sc['cost_center']},"
               f"{sc['prior_period_accrual']},{sc['prior_period_accrual']},"
               f"{sc['prior_period_variance']},{sc['currency']},invoice_received\n")
        return (header + row).encode()

    if logical_id == "rate_schedule":
        return (
            "contract_id,service_category,monthly_rate,currency,effective_date\n"
            f"{sc['contract_id']},{sc['service_category']},{sc['monthly_rate']},"
            f"{sc['currency']},{sc['rate_effective_date']}\n"
        ).encode()

    if logical_id == "vendor_contract":
        return f"""# Vendor Services Agreement {sc['contract_id']}

## Parties
This synthetic agreement is between **{sc['entity']}** (workspace `{wid}`) and
**{sc['vendor_name']}** (vendor ID **{sc['vendor_id']}**), collectively "the parties".
All names and identifiers are fictional and generated for demonstration only.

## Term
- Effective date: {sc['contract_start']}
- Expiry date: {sc['contract_end']}
- Renewal clause: auto-renews for successive 12-month terms unless either party
  gives 60 days written notice.

## Fees and rate evidence
- Service category: {sc['service_category']}
- Fixed monthly fee: {sc['currency']} {sc['monthly_rate']:,} per month, effective
  {sc['rate_effective_date']} per the attached rate schedule for {sc['contract_id']}.
- Billing: monthly in arrears; invoices due within 30 days of month end.

## Cost allocation
Charges are allocated to cost center {sc['cost_center']} and GL account
{sc['gl_account']} of entity {sc['entity']}.
""".encode()

    if logical_id == "reconciliation_workpaper":
        return f"""# Reconciliation Workpaper — {sc['contract_id']} — {cur}

Workspace: {wid} | Entity: {sc['entity']} | Cost center: {sc['cost_center']}

## Calculation
- Expected accrual (per contract {sc['contract_id']} monthly rate): {sc['currency']} {sc['expected_accrual']:,}
- Booked accrual (current-period extract {cur}): {sc['currency']} {sc['booked_accrual']:,}
- **Variance: {sc['currency']} {sc['variance']:,} (booked below expected)**

## Prior-period comparison ({prior})
- Prior-period booked and expected both {sc['currency']} {sc['prior_period_accrual']:,};
  variance {sc['currency']} {sc['prior_period_variance']:,}. The {cur} variance is new.

## Review status
- Preparer: {sc['preparer']}
- Reviewer: {sc['reviewer']}
- Status: pending_human_review — invoice support for the June cloud-services
  accrual variance has not been received from {sc['vendor_name']}.
""".encode()

    if logical_id == "exception_log":
        return json.dumps({
            "workspace_id": wid, "period": cur, "entity": sc["entity"],
            "exceptions": [
                {
                    "exception_id": "EXC-001",
                    "type": "missing_invoice_support",
                    "severity": "high",
                    "description": (
                        f"Missing invoice support file '{sc['missing_artifact']}' "
                        f"for vendor {sc['vendor_id']} contract {sc['contract_id']} "
                        f"period {cur}; variance {sc['currency']} {sc['variance']:,} "
                        "cannot be substantiated without it."),
                    "owner": sc["preparer"],
                    "due_date": "2026-07-05",
                    "linked_artifact_ids": [
                        artifact_id(ws.get("_dataset_version", "v1"), "accrual_extract_current"),
                        artifact_id(ws.get("_dataset_version", "v1"), "reconciliation_workpaper"),
                    ],
                    "expected_artifact": sc["missing_artifact"],
                },
                {
                    "exception_id": "EXC-002",
                    "type": "stale_approval",
                    "severity": "medium",
                    "description": (
                        f"Approval record for {sc['contract_id']} remains "
                        f"'{sc['approval_status']}'; no human decision recorded."),
                    "owner": sc["reviewer"],
                    "due_date": "2026-07-03",
                    "linked_artifact_ids": [
                        artifact_id(ws.get("_dataset_version", "v1"), "approval_record")],
                },
            ],
        }, indent=2).encode()

    if logical_id == "approval_record":
        return json.dumps({
            "workspace_id": wid, "period": cur, "entity": sc["entity"],
            "vendor_id": sc["vendor_id"], "contract_id": sc["contract_id"],
            "approval_status": sc["approval_status"],
            "approver_role": "finance_controller",
            "variance_amount": sc["variance"], "currency": sc["currency"],
            "decision": None, "decision_by": None, "decision_at": None,
            "note": "Human decision required. The agent must not approve, post, "
                    "or close this item.",
        }, indent=2).encode()

    raise ValueError(f"Unknown artifact logical_id: {logical_id}")


def generate_source_artifacts(manifest: dict, staging_dir: Path | None = None) -> dict:
    """Generate all source files into an ephemeral staging dir.

    Returns {"staging_dir": Path, "files": {logical_id: {"path", "sha256",
    "s3_key", ...}}}. Caller uploads to S3 and may delete staging afterwards.
    """
    ws = dict(manifest["workspace"])
    ws["_dataset_version"] = manifest["dataset_version"]
    sc = manifest["scenario"]
    version = manifest["dataset_version"]

    own_dir = staging_dir is None
    staging = staging_dir or Path(tempfile.mkdtemp(prefix="demo_staging_"))
    staging.mkdir(parents=True, exist_ok=True)

    files = {}
    for spec in manifest["artifacts"]:
        data = render_artifact(spec["logical_id"], ws, sc)
        path = staging / spec["s3_key"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[spec["logical_id"]] = {
            **spec,
            "artifact_id": artifact_id(version, spec["logical_id"]),
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "version": 1,
        }
    return {"staging_dir": staging, "files": files, "own_dir": own_dir,
            "manifest": manifest}


def cleanup_staging(gen: dict) -> None:
    if gen.get("own_dir"):
        shutil.rmtree(gen["staging_dir"], ignore_errors=True)


def build_evidence_index(gen: dict, s3_uris: dict) -> dict:
    """Manifests/v1/evidence_index.json content: artifact IDs, URIs, hashes."""
    manifest = gen["manifest"]
    return {
        "dataset_version": manifest["dataset_version"],
        "workspace_id": manifest["workspace"]["workspace_id"],
        "artifacts": [
            {
                "artifact_id": f["artifact_id"],
                "logical_id": lid,
                "source_uri": s3_uris[lid],
                "s3_key": f["s3_key"],
                "filename": f["filename"],
                "artifact_type": f["artifact_type"],
                "period": f["period"],
                "sha256": f["sha256"],
                "version": f["version"],
            }
            for lid, f in gen["files"].items()
        ],
        "expected_evidence_gaps": manifest["expected_evidence_gaps"],
        "retrieval_targets": manifest["retrieval_targets"],
    }
