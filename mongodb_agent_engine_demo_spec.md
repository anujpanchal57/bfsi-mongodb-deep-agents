# Demo build specification: Long-running AI agents on MongoDB Agent Engine

## 1. Document purpose

This is the implementation handoff for a conference demo at MongoDB.local Mumbai. Build a working demonstration of a long-running, evidence-driven AI workflow using MongoDB Agent Engine as the runtime, LangChain Deep Agents VFS as the agent workspace abstraction, MongoDB Atlas as the state and retrieval layer, and AWS S3 as the durable object store for source files.

The demo must make the platform value visible: the agent resumes work across sessions, retrieves targeted evidence from a growing document set, coordinates specialist work, and produces a reviewer-oriented output without taking regulated decisions away from humans.

## 2. Source context

The demo is based on the approved session abstract, “Building Durable, Searchable Workspaces for Long-Running AI Agents.” The abstract calls for a demonstration of:

* Persistent, searchable workspaces for LangChain Deep Agents
* AWS S3 for file content and native file operations
* MongoDB Atlas for agent state, memory, metadata, and retrieval
* Vector Search, Full-Text Search, and hybrid search using `$rankFusion`
* Long-running, multi-agent workflows with durable handoffs
* A human-in-the-loop BFSI operating model

Reference materials:

* [Session abstract](https://docs.google.com/document/d/1c5Pu8XdcSZnHfkMi3ft4JSm0UnHJbo5jl8-OFoTym6E/edit)
* [LangChain Deep Agents VFS repository](https://github.com/langchain-ai/langchain-mongodb/tree/main/libs/langchain-mongodb-deepagents-vfs)
* [MongoDB Atlas LangChain integration documentation](https://www.mongodb.com/docs/atlas/ai-integrations/langchain/#deepagents-virtual-file-system)

## 3. Demo objective

Demonstrate this audience takeaway:

> MongoDB Atlas turns an agent workspace into a searchable operational system. Agent Engine runs the workflow, S3 retains source files, and Atlas preserves state, metadata, evidence, and retrieval context so work can continue across sessions and agent handoffs.

## 4. Scope

### In scope

* One deterministic BFSI workflow: month-end accrual variance review
* MongoDB Agent Engine deployment and invocation
* LangChain Deep Agents VFS integration
* S3-backed source artifacts
* Atlas-backed workspace metadata, state, chunks, embeddings, and search
* Hybrid retrieval using Atlas Vector Search and Full-Text Search; prefer `$rankFusion` when supported by the target environment
* One orchestrator agent and one specialist variance-analysis agent
* Session interruption and resume
* Evidence-gap detection
* Reviewer-pack generation
* Human approval boundary
* Thin demo UI plus a CLI smoke-test path
* Seed data, automated tests, health checks, and a pre-recorded fallback path

### Out of scope

* Autonomous journal posting or accounting policy decisions
* Production-grade ERP, GL, or regulatory-system integration
* Real customer or confidential financial data
* Model fine-tuning
* Full enterprise authorization design
* Autonomous approval, closure, legal interpretation, or regulator communication
* Building a generalized document-management product

## 5. Primary user journey

The presenter should be able to complete this flow in 5–7 minutes:

1. Select an accrual-review workspace for a reporting period.
2. Ask the agent to review an open variance.
3. Show that the agent discovers the relevant contract, current-period extract, reconciliation workpaper, and prior-period evidence.
4. Show one intentionally missing artifact and an explicit evidence-gap result.
5. Save the intermediate state and simulate a session break.
6. Resume using only the workspace and run state, not the previous conversation transcript.
7. Hand off a scoped variance-analysis task to a specialist agent.
8. Retrieve the specialist’s findings from the shared workspace.
9. Generate a reviewer pack with evidence references, unresolved questions, and a proposed next step.
10. Stop at “human decision required”; do not approve, post, or close the accounting item automatically.

## 6. Reference architecture

```text
+-----------------------------+
| Thin UI / CLI               |
| workspace, task, evidence   |
+--------------+--------------+
               |
               v
+-----------------------------+
| MongoDB Agent Engine        |
| orchestrator + tools        |
| session/run entrypoint      |
+--------------+--------------+
               |
               v
+-----------------------------+
| LangChain Deep Agents VFS   |
| durable workspace interface |
+-----------+-----------------+
            |
     +------+------+
     |             |
     v             v
+---------+   +----------------+
| AWS S3  |   | MongoDB Atlas  |
| source  |   | state, memory, |
| files   |   | metadata,      |
|         |   | chunks, search |
+---------+   +----------------+
```

### Architecture rules

* Agent Engine is the runtime of record for the deployed agent; do not run the demo only as a local script.
* Keep the Agent Engine-specific bootstrap and deployment code isolated in one adapter module so SDK changes are localized.
* S3 is the source-file/object layer. Atlas is the operational workspace, state, metadata, and retrieval layer.
* The retrieval path must return source identifiers and evidence references with every material finding.
* Persist intermediate work and next actions in Atlas rather than relying on conversation history.
* Do not place credentials, connection strings, or raw secrets in prompts, source files, logs, or committed configuration.

## 7. Functional requirements

### FR-1: Workspace creation and discovery

The system must create and list a workspace with:

* `workspace_id`
* Business process, such as `accrual_review`
* Reporting period
* Entity or business unit
* Owner
* Status
* Created and updated timestamps
* Artifact count
* Open evidence gaps
* Current workflow step

### FR-2: Artifact registration

The system must register source artifacts from S3 and expose metadata sufficient for targeted retrieval:

* `artifact_id`
* Workspace ID
* S3 URI or object key
* Human-readable filename
* Artifact type
* Reporting period
* Entity or vendor identifier
* Version
* Content hash
* Ingestion status
* Created timestamp
* Access or classification tags

At minimum, seed these artifacts:

* Current-period accrual extract
* Prior-period accrual extract
* Vendor contract
* Rate schedule
* Reconciliation workpaper
* Exception log
* Approval record

Also seed one missing artifact condition, such as a missing invoice support file or stale approval record.

### FR-3: Ingestion and indexing

The ingestion pipeline must:

1. Read source files from the configured S3 prefix.
2. Extract text while retaining page, section, or row provenance where available.
3. Chunk content with a stable `chunk_id` and `artifact_id`.
4. Generate embeddings using the configured embedding provider.
5. Write chunks and metadata to Atlas.
6. Create or validate the Atlas Vector Search and Full-Text Search indexes.
7. Be idempotent using a content hash or source version.
8. Report partial failures without silently marking ingestion complete.

The code must make clear which data is stored in S3 and which derived content is stored in Atlas.

### FR-3a: Realistic mock-data seeding into Atlas

Provide a deterministic seed pipeline that creates a believable BFSI accrual-review workspace without using customer or production data. No human will provide the source files. The implementation agent owns generation of every source artifact, upload to S3, registration in Atlas, ingestion, indexing, and validation. The primary path must preserve the intended architecture:

1. Generate synthetic source artifacts locally from a versioned manifest.
2. Upload the artifacts to the configured S3 prefix.
3. Register the artifacts in Atlas.
4. Ingest, chunk, embed, and index the content in Atlas.
5. Create the initial workflow state, evidence gap, and pending human decision.
6. Validate expected document counts, relationships, and retrieval results.

The seed pipeline must be idempotent and support a complete reset of only the demo namespace. It must never delete unrelated databases, collections, S3 prefixes, or Atlas data.

#### Seeded business scenario

Use a fictional Indian finance entity and a fictional vendor. Keep all names and identifiers clearly synthetic:

* Workspace: `accrual_review_demo_2026_06`
* Entity: `demo_finance_india`
* Vendor: `VEN-2048`, `Asterion Cloud Services India Pvt Ltd`
* Contract: `CON-7781`
* Cost center: `CC-410`
* Current period: `2026-06`
* Prior period: `2026-05`
* Currency: INR
* Booked accrual: INR 1,240,000
* Expected accrual: INR 1,275,000
* Variance: INR 35,000

The values must agree across the seeded artifacts so the agent can reconcile them. The scenario should demonstrate a meaningful variance without requiring complex accounting logic.

#### Source artifact generation and S3 ownership

The implementation must generate the actual source files; it must not assume that PDFs, CSVs, JSON files, workpapers, or approval records will be supplied separately. Generate them from a versioned manifest and templates, write them to an ephemeral local staging directory, and upload them to S3 before Atlas ingestion.

Use these deterministic S3 object keys under the configured demo prefix:

| S3 object key | Format | Purpose |
| --- | --- | --- |
| `source/2026-06/accrual_extract_current.csv` | CSV | Current-period booked and expected accrual values |
| `source/2026-05/accrual_extract_prior.csv` | CSV | Prior-period comparison values |
| `source/2026-06/vendor_contract_CON-7781.md` | Markdown | Contract terms and rate evidence |
| `source/2026-06/rate_schedule_CON-7781.csv` | CSV | Monthly service rates and effective dates |
| `source/2026-06/reconciliation_workpaper_CON-7781.md` | Markdown | Reconciliation calculation and review status |
| `source/2026-06/exception_log.json` | JSON | Missing-support and stale-approval exceptions |
| `source/2026-06/approval_record.json` | JSON | Pending human approval record |
| `manifests/v1/evidence_index.json` | JSON | Artifact manifest, hashes, provenance, and expected validation results |

Generation requirements:

* Create the files from `data/manifests/mock_accrual_v1.json` and versioned templates or generator code.
* Use synthetic names, IDs, amounts, and dates only; do not call an external business system or copy real company data.
* Ensure every file contains the workspace ID, period, entity, vendor or contract ID where relevant, and enough provenance for the agent to link the file to Atlas records.
* Include one exact-match target (`CON-7781` or `VEN-2048`) and one semantic target (“support for the June cloud-services accrual variance”).
* Generate internally consistent values across all files, including the INR 35,000 variance and the `pending_human_review` status.
* Calculate and record SHA-256 hashes before upload; Atlas metadata and the manifest must contain the same hashes.
* Upload and verify every expected S3 object before beginning ingestion.
* Fail the seed command if an expected object is missing, has a mismatched hash, or is uploaded outside the configured demo prefix.
* Do not silently use local files as the conference-demo source after upload; local staging is only an intermediate generation step.
* Make generated files safe to delete and recreate using the reset command.

The README must state clearly that a clean checkout plus credentials is sufficient to generate the complete S3 dataset; no manually prepared source artifacts are required.

#### Required mock artifacts

Generate at least these artifacts with cross-referenced IDs and provenance:

| Artifact | Format | Required content |
| --- | --- | --- |
| Current-period accrual extract | CSV or JSON | Vendor, contract, GL account, cost center, period, booked amount, expected amount, currency, invoice status |
| Prior-period accrual extract | CSV or JSON | Prior-period amount, vendor, contract, cost center, and comparable variance fields |
| Vendor contract | Markdown or PDF-compatible text | Contract term, rate, effective date, renewal clause, vendor and contract identifiers |
| Rate schedule | CSV or Markdown | Monthly rate, effective date, service category, currency, and contract ID |
| Reconciliation workpaper | Markdown or XLSX-compatible data | Expected versus booked calculation, variance, preparer, reviewer, and status |
| Exception log | JSON or Markdown | Missing invoice support or stale approval, severity, owner, due date, and linked artifact IDs |
| Approval record | JSON or Markdown | Approval status set to `pending_human_review`, approver role, timestamps, and decision fields left empty |
| Evidence index manifest | JSON | Artifact IDs, source URIs, hashes, versions, and expected chunk counts |

Include at least one exact-match retrieval target, such as `CON-7781` or `VEN-2048`, and one semantic retrieval target, such as “support for the June cloud-services accrual variance.”

#### Atlas seed behavior

The seed command must:

* Accept `--dataset-version`, `--workspace-id`, `--reset`, and `--embedding-mode` arguments.
* Use deterministic IDs derived from dataset version and logical identifiers.
* Upsert the workspace, artifacts, chunks, workflow state, handoff seed, and reviewer-pack seed records.
* Preserve source-to-chunk provenance, including filename, page/section/row, and source URI.
* Use the real configured embedding provider for the conference path.
* Support deterministic local embeddings only for unit tests or offline development, clearly labeled as non-production.
* Create or validate Vector Search and Full-Text Search indexes before reporting success.
* Run validation queries and fail if expected artifact IDs, variance values, or evidence gaps are missing.
* Print a concise manifest summary: workspace ID, artifact count, chunk count, index status, and validation status.

Recommended commands:

```text
python scripts/seed_mock_data.py --dataset-version v1 --reset
python scripts/validate_seed.py --workspace-id accrual_review_demo_2026_06
python scripts/reset_demo.py --workspace-id accrual_review_demo_2026_06 --confirm
```

The implementation may use different command names, but the README must document equivalent commands and the exact reset boundary.

### FR-4: Hybrid evidence retrieval

Implement a retrieval tool with this logical contract:

```text
search_workspace(
  workspace_id,
  query,
  filters,
  top_k,
  retrieval_mode="hybrid"
) -> ranked evidence items
```

Each result must include:

* Artifact ID and filename
* Chunk ID
* Source URI or document reference
* Matching score or ranking signal when available
* Extracted passage
* Page, section, or row provenance when available
* Metadata filters that matched
* Retrieval mode used

Retrieval behavior:

* Use lexical search for exact identifiers, vendor names, account codes, policy phrases, and control language.
* Use vector search for paraphrased concepts and semantically related evidence.
* Prefer Atlas hybrid search with `$rankFusion` when available in the target cluster and SDK.
* If `$rankFusion` is unavailable, provide a documented fallback that combines the two result sets deterministically; do not silently claim that native hybrid search was used.
* Apply workspace and metadata filters before returning results.
* Never return an answer without retaining the evidence references used to produce it.

### FR-5: Durable workflow state

Persist at least:

* Current workflow step
* User request
* Open questions
* Retrieved evidence IDs
* Agent findings
* Specialist handoffs
* Pending human decisions
* Last successful action
* Next recommended action
* Run ID and timestamps

The workflow must resume correctly after:

* Clearing the UI conversation state
* Restarting the local client
* Starting a new Agent Engine request with the same workspace/run identifiers

### FR-6: Multi-agent handoff

Implement two logical roles:

#### Orchestrator agent

Responsibilities:

* Inspect workspace state
* Plan the evidence-gathering task
* Call retrieval and workspace tools
* Detect missing or stale evidence
* Create a specialist handoff
* Read the specialist result
* Prepare the reviewer pack

#### Variance-analysis specialist

Responsibilities:

* Receive a scoped task and workspace reference
* Retrieve only the evidence needed for the variance question
* Compare current and prior period evidence
* Produce findings, assumptions, evidence references, and unresolved questions
* Write its result back to the workspace

Handoff contract:

```json
{
  "handoff_id": "string",
  "workspace_id": "string",
  "parent_run_id": "string",
  "task": "string",
  "scope": {
    "artifact_ids": ["string"],
    "period": "string",
    "entity": "string"
  },
  "expected_output": [
    "finding",
    "evidence_references",
    "unresolved_questions",
    "recommended_next_step"
  ],
  "status": "created|running|completed|blocked",
  "created_at": "timestamp"
}
```

The specialist must not make approval or posting decisions.

### FR-7: Reviewer-pack generation

Generate a structured reviewer pack containing:

* Review objective
* Workspace and reporting period
* Executive summary
* Variance or exception under review
* Findings
* Evidence table with artifact and passage references
* Missing or stale evidence
* Assumptions and uncertainty
* Specialist-agent output
* Proposed next step
* Explicit human decision required
* Run ID and generation timestamp

The output must distinguish:

* Evidence observed
* Agent inference
* Evidence still required
* Human decision required

### FR-8: Human-in-the-loop boundary

The UI and agent output must visibly label these actions as human-controlled:

* Accounting policy judgment
* Materiality determination
* Journal approval or posting
* Valuation or provision decision
* Final reporting
* Regulatory closure or communication

The demo must never expose a tool that posts a journal, closes a finding, or approves a control as an agent action.

## 8. Suggested Atlas data model

Use separate collections or a clearly documented equivalent. Collection names are suggestions; keep the logical separation.

### `agent_workspaces`

```json
{
  "_id": "workspace_id",
  "process": "accrual_review",
  "period": "2026-06",
  "entity": "demo_finance_india",
  "owner": "finance-reviewer",
  "status": "in_progress",
  "current_step": "evidence_review",
  "open_evidence_gaps": ["invoice_support"],
  "created_at": "date",
  "updated_at": "date"
}
```

### `workspace_artifacts`

```json
{
  "_id": "artifact_id",
  "workspace_id": "workspace_id",
  "filename": "vendor_contract.pdf",
  "artifact_type": "contract",
  "source_uri": "s3://bucket/key",
  "period": "2026-06",
  "entity": "demo_finance_india",
  "version": 1,
  "content_hash": "sha256",
  "ingestion_status": "indexed",
  "created_at": "date"
}
```

### `workspace_chunks`

```json
{
  "_id": "chunk_id",
  "workspace_id": "workspace_id",
  "artifact_id": "artifact_id",
  "content": "retrievable text",
  "embedding": [0.0],
  "page": 3,
  "section": "rate schedule",
  "metadata": {
    "period": "2026-06",
    "entity": "demo_finance_india",
    "artifact_type": "contract"
  },
  "created_at": "date"
}
```

### `agent_runs`

```json
{
  "_id": "run_id",
  "workspace_id": "workspace_id",
  "session_id": "session_id",
  "parent_run_id": null,
  "goal": "review accrual variance",
  "state": "evidence_review",
  "findings": [],
  "evidence_references": [],
  "open_questions": [],
  "next_action": "run specialist variance analysis",
  "created_at": "date",
  "updated_at": "date"
}
```

### `agent_handoffs`

Store the handoff contract, status transitions, scoped artifact IDs, result references, and timestamps.

### `reviewer_packs`

Store the generated pack, its source run ID, evidence references, version, and human-review status. Do not store an approval decision unless a human explicitly supplies it through the UI.

## 9. Agent tools

Expose narrowly scoped tools rather than a generic database tool:

* `get_workspace(workspace_id)`
* `list_workspace_artifacts(workspace_id, filters)`
* `read_artifact(artifact_id, locator)`
* `search_workspace(workspace_id, query, filters, top_k, retrieval_mode)`
* `save_working_note(workspace_id, run_id, note)`
* `update_workflow_state(workspace_id, run_id, state_patch)`
* `create_specialist_handoff(workspace_id, run_id, task, scope)`
* `get_handoff(handoff_id)`
* `save_specialist_result(handoff_id, result)`
* `generate_reviewer_pack(workspace_id, run_id)`

Tool requirements:

* Validate all IDs and workspace scope.
* Log tool name, run ID, workspace ID, latency, and outcome.
* Return structured errors with a user-safe message.
* Make writes idempotent where possible.
* Never expose unrestricted collection access to the model.

## 10. MongoDB Agent Engine requirements

The implementation agent must validate the current Agent Engine SDK, deployment manifest, authentication model, and runtime contract before coding against them.

Build requirements:

* Provide a single Agent Engine entrypoint for the orchestrator.
* Use a stable request contract containing `workspace_id`, `session_id`, `run_id` if supplied, and `user_message`.
* Keep durable state in Atlas; treat the Agent Engine process as restartable.
* Expose health/readiness behavior suitable for a live demo.
* Capture run IDs and correlation IDs in every log line.
* Provide a local development mode that invokes the same agent entrypoint without bypassing the production adapter.
* Keep provider-specific model configuration in environment variables.
* Document the exact deployment command and required project/cluster identifiers in the README.
* Pin package versions and record the tested Agent Engine SDK version.

Create an adapter with a small surface such as:

```python
class AgentEngineRuntime:
    def invoke(self, request: AgentRequest) -> AgentResponse:
        """Run one durable workspace interaction."""

    def health(self) -> HealthResponse:
        """Return dependency and runtime readiness."""
```

Do not invent an Agent Engine API. If the current SDK uses a different entrypoint or deployment model, adapt this interface to the supported model and document the mapping.

## 11. Demo interface

Build a thin Streamlit or equivalent UI with these views:

### Workspace view

* Workspace selector
* Period, entity, status, current step
* Artifact list and ingestion status
* Open evidence gaps

### Agent interaction view

* User request input
* Agent response
* Run ID
* Tool/event timeline
* Evidence references
* Resume-session control

### Handoff view

* Specialist task
* Scope
* Status
* Findings
* Evidence references
* Unresolved questions

### Reviewer-pack view

* Rendered reviewer pack
* Human decision required banner
* Download or copy action
* No approve/post/close button for the agent

The CLI must support the same core flow for automated smoke tests:

```text
seed -> ingest -> create-workspace -> invoke -> interrupt -> resume -> handoff -> reviewer-pack
```

## 12. Repository structure

Use a structure similar to:

```text
mongodb-agent-engine-demo/
├── README.md
├── pyproject.toml
├── .env.example
├── Makefile
├── src/
│   ├── agent_engine_adapter.py
│   ├── agent_entrypoint.py
│   ├── config.py
│   ├── models.py
│   ├── agents/
│   │   ├── orchestrator.py
│   │   └── variance_specialist.py
│   ├── tools/
│   │   ├── workspace_tools.py
│   │   ├── retrieval_tools.py
│   │   └── handoff_tools.py
│   ├── storage/
│   │   ├── atlas_repository.py
│   │   ├── s3_repository.py
│   │   └── indexes.py
│   └── ui/
│       └── app.py
├── data/
│   ├── generated/                 # gitignored; created during seeding
│   ├── manifests/
│   │   └── mock_accrual_v1.json
│   └── templates/
├── scripts/
│   ├── generate_source_artifacts.py
│   ├── seed_mock_data.py
│   ├── seed_s3.py
│   ├── ingest_workspace.py
│   ├── create_indexes.py
│   ├── validate_seed.py
│   ├── reset_demo.py
│   └── smoke_demo.py
├── tests/
│   ├── test_retrieval.py
│   ├── test_resume.py
│   ├── test_handoff.py
│   └── test_reviewer_pack.py
└── deploy/
    ├── agent-engine.*
    └── README.md
```

The implementation agent may change names to match the current Agent Engine SDK, but must preserve the separation between runtime, agent logic, tools, storage, UI, and deployment.

## 13. Configuration and secrets

Provide `.env.example` with placeholders only. At minimum document:

```text
MONGODB_URI=
MONGODB_DATABASE=
MONGODB_WORKSPACE_COLLECTION=
MONGODB_CHUNKS_COLLECTION=
AWS_REGION=
S3_BUCKET=
S3_PREFIX=
DEMO_DATASET_VERSION=v1
DEMO_WORKSPACE_ID=accrual_review_demo_2026_06
EMBEDDING_PROVIDER=
EMBEDDING_MODEL=
LLM_PROVIDER=
LLM_MODEL=
AGENT_ENGINE_PROJECT=
AGENT_ENGINE_ENVIRONMENT=
LOG_LEVEL=INFO
```

Requirements:

* Use secret-manager or Agent Engine secret configuration for deployed credentials.
* Never commit `.env`, private keys, real URIs, or customer data.
* Fail fast with a clear message when required variables are missing.
* Provide a mock/local mode only for unit tests; the conference demo path must use the real Atlas and S3 integrations.

## 14. Observability and demo diagnostics

Log structured events for:

* Agent invocation start and completion
* Workspace load and state resume
* Retrieval mode, filters, result count, and latency
* Artifact reads and writes
* Handoff creation and completion
* Reviewer-pack generation
* Errors and retries

Never log full document contents or credentials. The UI should expose a concise event timeline so the presenter can explain what happened without opening raw logs.

Add a diagnostic command that verifies:

* Agent Engine runtime is reachable
* Atlas connection works
* Required collections exist
* Required search indexes are ready
* S3 access works
* Seed workspace exists
* A known hybrid retrieval query returns expected artifacts

## 15. Acceptance criteria

The demo is complete when all criteria pass:

### AC-1: Real Agent Engine path

A fresh environment can invoke the deployed MongoDB Agent Engine entrypoint using documented commands and credentials.

### AC-2: Durable resume

After clearing the client conversation and starting a new request with the same workspace, the agent recovers the persisted workflow state, open questions, and next action.

### AC-3: Evidence retrieval

A known query returns both an exact-match artifact and a semantically related artifact, with source references and provenance.

### AC-4: Hybrid-search transparency

The UI or logs identify whether native Atlas hybrid search with `$rankFusion` or the documented fallback was used.

### AC-5: Evidence gap

The seeded missing artifact is detected and appears in the reviewer pack as “evidence required,” not as an invented conclusion.

### AC-6: Multi-agent handoff

The orchestrator creates a scoped specialist task, the specialist writes a result, and the orchestrator reads the result from durable storage.

### AC-7: Human control

The system clearly separates agent-generated findings from human decisions and exposes no autonomous posting, approval, or closure action.

### AC-8: Reproducible seed

A single documented command resets only the demo namespace in Atlas and the configured S3 prefix, reseeds the versioned mock dataset, validates indexes, and reports the expected artifact, chunk, and evidence-gap counts.

### AC-9: Seed-data realism and consistency

The seeded artifacts contain consistent fictional business identifiers and amounts across current-period, prior-period, contract, rate, reconciliation, exception, and approval records. Validation fails when cross-document relationships or expected retrieval targets are missing.

### AC-10: Test coverage

Automated tests cover retrieval filtering, resume behavior, handoff persistence, missing evidence, reviewer-pack source references, artifact generation, S3 manifest validation, and reset isolation.

### AC-11: S3 source artifact generation

From a clean checkout, the documented seed command generates every required source file, uploads and verifies every expected S3 object, and completes without human-supplied input files. A failed upload or hash mismatch stops the pipeline before Atlas ingestion.

### AC-12: Failure recovery

The README includes a backup demo path and troubleshooting steps for unavailable Agent Engine, S3, Atlas indexes, model provider, or network access.

## 16. Presenter runbook

### Before the session

* Run the diagnostic command.
* Reset and seed the workspace; confirm that the command generated and uploaded all expected S3 objects.
* Verify the expected retrieval results and S3/Atlas hash alignment.
* Warm the Agent Engine deployment and model provider.
* Confirm the backup recording or local fallback works.
* Open the UI at the workspace view.

### Live sequence

1. Show the workspace and its artifacts.
2. Ask the orchestrator to investigate the variance.
3. Point out the evidence returned from hybrid retrieval.
4. Highlight the missing support artifact.
5. Save state and simulate a session break.
6. Resume and show that the workflow continues.
7. Trigger the specialist handoff.
8. Show the specialist result in the shared workspace.
9. Generate the reviewer pack.
10. End on “human decision required.”

### Recovery shortcuts

* If Agent Engine is unavailable: run the local adapter against the same Atlas and S3 data, while clearly labeling it as local fallback.
* If search indexes are not ready: use the precomputed seeded results only as a backup, never as the primary demo path.
* If model latency is high: use a cached transcript for the narrative and show the live retrieval/state transitions.
* If the UI fails: run the CLI smoke-demo and show the structured reviewer pack.

## 17. Implementation order

1. Validate the current MongoDB Agent Engine runtime and deployment contract.
2. Create the repository skeleton and configuration validation.
3. Define the versioned mock-data manifest and synthetic BFSI artifacts.
4. Implement the Atlas collections, indexes, and seed/reset/validation commands.
5. Implement S3 upload and ingestion with provenance-preserving chunking.
6. Implement workspace and state repositories.
7. Implement retrieval with native hybrid search first and a clearly labeled fallback.
8. Implement the orchestrator and specialist workflow.
9. Implement resume and handoff persistence.
10. Implement reviewer-pack generation and human-control labels.
11. Add UI and CLI smoke path.
12. Add tests, diagnostics, deployment documentation, and backup flow.
13. Run the complete presenter runbook from a clean environment after a full reset and reseed.

## 18. Definition of done

The implementation is ready for handoff and rehearsal when:

* The real Agent Engine deployment executes the end-to-end flow.
* The demo uses real Atlas and S3 integrations.
* A session break does not lose the workflow state.
* Retrieval results are targeted, source-linked, and reproducible.
* The specialist handoff is durable and scoped.
* The reviewer pack exposes evidence gaps and human decision points.
* No regulated decision is made autonomously.
* A clean-environment setup, test, deploy, seed, reset, and demo command are documented.
* The mock dataset is versioned, deterministic, synthetic, cross-document consistent, and seeded through the S3-to-Atlas path.
* No human-provided source artifacts are required; the implementation generates and verifies the complete S3 source dataset.
* Seed validation confirms expected workspaces, artifacts, chunks, indexes, retrieval targets, and evidence gaps.
* The presenter can complete the flow within seven minutes and recover using the fallback path.
