# Alignment spec: adopt LangChain Deep Agents VFS + Atlas Agent Engine SDK

Status: proposal. Supersedes the home-grown layers of the current demo where
noted. Source artifacts verified 2026-09-24:

- `langchain-ai/langchain-mongodb` → `libs/langchain-mongodb-deepagents-vfs` (public)
- `10gen/magenta-client-libraries` — Atlas Agent Engine SDKs + `agentengine` CLI (private; accessed via org membership)
- `10gen/magenta-examples` — reference agents incl. `deep-agent-skills-code-reviewer` (private)
- `docs/agent-yaml.md` — deployment manifest schema (private)

## 1. Why

The current project implements its own chunking, embedding, retrieval,
agent loop, and runtime adapter. The platform already provides all four:

| Current (hand-rolled) | Platform artifact that replaces it |
| --- | --- |
| `src/ingestion.py` (chunk/embed/index) | `MongoFilesystemBackend` initial sync + watcher (512-token chunks, provenance, ETag idempotency) |
| `src/retrieval.py` (hybrid search + RRF fallback) | `backend.grep()` — native `$rankFusion` hybrid inside Atlas, full-text-only fallback built in |
| `src/storage/indexes.py` (index provisioning) | Backend provisions its own Vector/Full-Text indexes |
| `src/agents/orchestrator.py` (custom state machine) | `app.deep_agent(...)` DeepAgents orchestrator + `task()` subagent dispatch |
| `src/agents/variance_specialist.py` | DeepAgents subagent declaration (`subagents=[...]`) |
| `src/agent_engine_adapter.py`, `src/agent_entrypoint.py` | `agent_engine_sdk_langgraph.App` entrypoint (`agent.yaml` `entrypoint:` contract) |
| Custom session resume | `app.checkpointer()` (MongoDB checkpointing) + `features.durable_workflow: true` |

Keep (they are the demo's business value, not platform plumbing):
`src/mockdata.py`, `src/seeding.py` (generation/upload/verify/validate),
`src/models.py`, `src/storage/atlas_repository.py`, `src/storage/s3_repository.py`,
`src/reviewer_pack.py`, the human-in-the-loop boundary, the Streamlit UI, and
the test suite (adapted).

## 2. Target architecture

```text
UI / CLI / Playground
        |
        v
agentengine runtime (OE + AER + Tool Pod)     <- deployed via agent.yaml
        |
        v
App (agent_engine_sdk_langgraph)
  @app.entrypoint -> app.deep_agent(
      llm, tools=app.get_tool_schemas(),
      subagents=[variance_specialist],
      system_prompt=ORCHESTRATOR_PROMPT)
        |
        +-- checkpointer = app.checkpointer()        (durable sessions in Atlas)
        +-- @app.tool()s -> workspace/handoff/pack   (business state in Atlas)
        +-- deepagents filesystem tools
              -> MongoFilesystemBackend (BackendProtocol)
                   grep/glob/ls  -> Atlas ($rankFusion hybrid)
                   read/write/edit -> S3 (source of truth)
```

S3 remains the source-file layer; Atlas holds chunks/embeddings (owned by the
VFS backend) **and** business state (workspaces, runs, handoffs, packs — owned
by our tools). The two chunk worlds are separated: the backend's collection
is managed by the backend; our collections are managed by our tools.

**Embeddings:** the VFS package's **default** option — AWS Bedrock
`amazon.titan-embed-text-v2:0` @ 1024 dimensions, resolved through the boto3
credential chain (no extra API key; `EMBEDDING_PROVIDER=bedrock` is the
package default). OpenAI `text-embedding-3-small` is the documented
alternative. No Atlas auto-embedding and no direct Voyage API usage — the
backend embeds chunks at sync time and queries at search time.

## 3. Codebase changes

### 3.1 New dependencies (`pyproject.toml`)

```toml
requires-python = ">=3.11"          # deepagents requires 3.11+
dependencies = [
    "agent-engine-sdk-langgraph",   # Atlas Agent Engine SDK (LangGraph adapter)
    "deepagents",
    "langchain-mongodb-deepagents-vfs[bedrock]",  # default embedding provider
    "pymongo>=4.7,<5",
    "boto3>=1.34,<2",
    "python-dotenv>=1.0,<2",
]
```

- Commit `uv.lock` (platform builds require it; ECP expects `uv sync`).
- Python SDK availability: while the SDK is private, use a checked-in
  `wheels/` directory next to `agent.yaml` (still supported by platform
  builds) or a private PyPI index declared via `artifact_repositories` in
  `agent.yaml` with the token set through `agentengine secret set`.
- `agentengine` CLI: install from `mongodb/atlasap` GitHub releases.

### 3.2 New entrypoint: `src/demo_agent/main.py`

```python
app = App(app_name="accrual-variance-review")

register(app)  # @app.tool() business tools (3.3)

@app.entrypoint
def build_agent():
    backend = MongoFilesystemBackend(
        s3_bucket_name=os.environ["S3_BUCKET"],
        mongodb_connection_string=os.environ["MONGODB_URI"],
        s3_prefix=os.environ.get("S3_PREFIX", "agent-engine-demo/"),
        # embeddings: package default — Bedrock titan-embed-text-v2:0 @ 1024
        # dims via the boto3 credential chain (EMBEDDING_PROVIDER=bedrock)
    )
    return app.deep_agent(
        llm=build_llm(),                    # provider from env (LLM_*)
        tools=app.get_tool_schemas(),       # deep_agent does NOT auto-merge
        subagents=[VARIANCE_SPECIALIST],    # dict: name/description/system_prompt
        system_prompt=ORCHESTRATOR_PROMPT,
        backend=backend,                    # verified kwarg (see below)
    )

def main() -> None:
    app.run()
```

- `ORCHESTRATOR_PROMPT` ports the current workflow narrative (gather evidence
  → detect gap → delegate → reviewer pack → stop at human decision) as
  instructions, modeled on `deep-agent-skills-code-reviewer`'s parent prompt.
- Specialist becomes a subagent declaration; dispatch happens through
  deepagents' built-in `task()` tool. The specialist prompt forbids approval,
  posting, and closure actions.
- `App` integration with `MongoFilesystemBackend` — **verified against SDK
  source on `main` (2026-09-24)**: `App.deep_agent(..., backend=...)`
  accepts any `deepagents.backends.protocol.BackendProtocol` and forwards it
  to `deepagents.create_deep_agent(backend=...)`. Pass
  `backend=MongoFilesystemBackend(...)` directly. Two caveats from the SDK
  source: (1) the default `AgentEngineToolPodBackend` is the OE-audited I/O
  path — a custom backend bypasses that audit, so our own tool/access
  logging must cover it (already required by the demo spec §14);
  (2) `App.deep_agent()` raises unless `features.deep_agent: true` is set in
  `agent.yaml`.

### 3.3 Business tools — keep, re-expose as `@app.tool()`

Move the logic in `src/tools/workspace_tools.py`, `handoff_tools.py`, and
`src/reviewer_pack.py` behind `@app.tool()` functions (same validation,
logging, and structured errors as today):

- `get_workspace(workspace_id)`, `list_workspace_artifacts(workspace_id, filters)`
- `save_working_note`, `update_workflow_state` (business state; complements,
  not replaces, the checkpointer)
- `create_specialist_handoff` / `save_specialist_result` / `get_handoff` —
  keep as durable handoff *records* so the Handoff UI view and the demo's
  "durable handoff" story survive even though dispatch is via `task()`
- `generate_reviewer_pack(workspace_id, run_id)` — unchanged logic

Retrieval tools are **deleted**: the agent uses the backend's `grep`/`glob`/`ls`
directly. Add one thin evidence-shaping helper tool only if the pack needs
chunk-level source URIs beyond `GrepMatch` (path/line/text); first try
mapping `path → s3://bucket/key` in the pack builder.

### 3.4 Deletions

| Delete | Replaced by |
| --- | --- |
| `src/ingestion.py` | backend sync/watcher |
| `src/retrieval.py` | `backend.grep()` |
| `src/storage/indexes.py` | backend index provisioning (keep `indexes_ready`-style *validation* in `scripts/diagnose.py`) |
| `src/embeddings.py` (real providers) | VFS package embedders — default Bedrock Titan via boto3 chain |
| `src/agent_engine_adapter.py`, `src/agent_entrypoint.py` | `App` + `agent.yaml` |
| `src/tools/retrieval_tools.py` | backend filesystem tools |
| `scripts/ingest_workspace.py`, `scripts/create_indexes.py` | `agentengine dev up` / backend startup; index *status* stays in `diagnose.py` |

### 3.5 Seeding pipeline adjustments (`src/seeding.py`, `scripts/`)

1. Generate + upload + hash-verify artifacts to S3 — **unchanged** (FR-3a).
2. Registration/ingestion changes: instead of self-chunking, instantiate
   `MongoFilesystemBackend` and await initial sync (`backend.grep("warmup")`
   blocks until ready; check `backend.init_errors` and
   `backend.initial_sync_report.failed`).
3. Validation adapts to the backend's chunk schema (`source_path`,
   `chunk_index`, `line_start`) instead of our `workspace_chunks` shape; the
   exact-match/semantic retrieval checks call `backend.grep()`.
4. Reset must also clear the backend's chunks collection for the demo prefix
   (identify the collection name from the installed package; scope deletion
   to `source_path` under the demo prefix) plus our business collections.
5. Embeddings use the package's **default provider — AWS Bedrock
   `amazon.titan-embed-text-v2:0` @ 1024 dims via the boto3 credential
   chain** (`EMBEDDING_PROVIDER=bedrock` is the package default; requires
   `bedrock:InvokeModel` on the IAM role). OpenAI is the documented
   alternative (`EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY`). The
   deterministic embedder and `--allow-deterministic` guard remain for unit
   tests only (in-memory repo, no Atlas/S3/Bedrock).

### 3.6 Streamlit UI

Replace direct `AgentEngineRuntime` calls with the platform invoke path:
locally `agentengine dev up` + its API/playground; deployed: the workspace
invoke API (`input.payload` for structured requests — set
`features.playground: false` if the demo UI stays Streamlit, or use the
provisioned playground instead and keep Streamlit as the reviewer-pack
viewer only). Keep the four views and the human-decision banner unchanged.

## 4. Agent configuration (`agent.yaml`, repo root)

```yaml
name: accrual-variance-review
entrypoint: demo_agent.main:app
framework: langgraph
description: Month-end accrual variance review with durable, evidence-driven
  orchestration over an S3 + Atlas workspace. Human-in-the-loop BFSI demo.
version: 0.1.0

features:
  deep_agent: true          # required for app.deep_agent()
  durable_workflow: true    # OE-owned durable sessions
  memory: false

sandboxes:
  agent:
    network:
      egress_mode: allow_list
      egress:
        - fqdn: <s3 regional endpoint>      # S3 object I/O
        - fqdn: <LLM provider endpoint>     # e.g. api.anthropic.com
        - fqdn: <bedrock endpoint>          # default embeddings (Titan v2)
    secrets: ["*"]
    tools: ["*"]            # demo tools are all agent-side
  tool:
    secrets: ["*"]
    tools: []

required_secrets:
  aer:
    - MONGODB_URI
    - LLM_API_KEY
  tools:
    invoke_llm:
      - LLM_API_KEY
```

- Atlas connectivity: use the manifest's top-level `network.atlas_clusters`
  (not sandbox egress) per the agent.yaml reference.
- `dev.yaml` alongside for local dev: `services.mongodb.local: false` with
  `MONGODB_URI` in `.env` (real Atlas; search indexes need it).
- `.env.example` gains `LLM_API_KEY`, `VOYAGE_API_KEY` (only if memory is
  enabled later), and `EMBEDDING_PROVIDER=bedrock` / `EMBEDDING_MODEL`
  overrides for the VFS backend (defaults: Bedrock Titan v2, boto3 chain).
- Add `.agentengineignore` (gitignore syntax; `.env`/`.git` always excluded).

## 5. Deployment flow (was: placeholder adapter)

```bash
# one-time
agentengine init                       # or scaffold via agentengine create
agentengine secret set MONGODB_URI
agentengine secret set LLM_API_KEY
# validate -> local run -> deploy
agentengine agent validate
agentengine dev up                     # local OE+AER+Tool Pod stack
agentengine build
agentengine deploy
```

- Root `agent.yaml` + committed `uv.lock` satisfy ECP/CodeBuild expectations.
- Record the tested `agentengine` CLI and SDK versions in `deploy/README.md`.
- `scripts/diagnose.py` keeps its checks but reads index status from the
  backend's collections and adds `agentengine`-level health (deployment
  reachable) in place of the current adapter `health()`.

## 6. Durable-state mapping

| Demo requirement | Platform mechanism |
| --- | --- |
| Session resume after break | `app.checkpointer()` + `features.durable_workflow: true`; same session/thread ID resumes |
| Workflow step / next action visible in UI | Our `agent_runs` business state via `update_workflow_state` tool (kept) |
| Durable specialist handoff | `task()` dispatch + handoff record persisted in `agent_handoffs` (kept) |
| Reviewer pack persistence | `reviewer_packs` (kept) |

## 7. Risks / open questions

1. **SDK distribution**: Python SDK is private. Confirm delivery mechanism
   (public PyPI vs vendored `wheels/` vs private index + `artifact_repositories`)
   before the build step. This is the highest-risk unknown.
2. ~~**`App.deep_agent()` backend wiring**~~ — **RESOLVED (2026-09-24, from
   SDK source on `main`)**: `deep_agent(..., backend=MongoFilesystemBackend(...))`.
   Caveats: custom backends bypass the OE-audited Tool-Pod I/O path (cover
   with our own logging), and `features.deep_agent: true` is mandatory.
3. **Search freshness**: VFS README documents watcher lag (polling default
   10s) plus Atlas indexing lag — seed before the demo, don't write files
   live on stage; consider `watcher="sqs"` only if the demo writes files.
4. **Cluster tier + Bedrock access**: Vector + Full-Text Search need M10+;
   the default Bedrock Titan embedding model must be enabled in the demo
   AWS account/region (`bedrock:InvokeModel` on the runtime role) — warm it
   during the pre-session checklist.
5. **Python 3.11**: platform runner-base is CPython 3.11; local dev currently
   runs 3.14 — pin 3.11 for parity.
6. **Behavioral change**: the deterministic state machine becomes an LLM
   orchestrator. The reviewer pack and human boundary stay deterministic
   (tool-enforced); acceptance tests must assert the pack/gap/boundary
   invariants regardless of LLM narration.

## 8. Implementation order

1. Obtain SDK + CLI; `agentengine create` a scratch hello-world to validate
   the toolchain end-to-end.
2. Add deps, root `agent.yaml`/`dev.yaml`, `.agentengineignore`; `agentengine agent validate`.
3. Port entrypoint (`App`, `@app.entrypoint`, `deep_agent`, subagent) with
   the orchestrator/specialist prompts.
4. Wire `MongoFilesystemBackend` (default Bedrock embeddings); re-point
   seeding to backend sync; adapt validation + reset + diagnose.
5. Re-expose business tools via `@app.tool()`; delete superseded modules.
6. Re-point UI at the platform invoke API; keep the four views.
7. Adapt tests: tools/pack/gap/reset stay offline-testable; orchestrator
   behavior tests run against `agentengine dev up` as integration tests.
8. `agentengine build` + `deploy`; record SDK/CLI versions; update README and
   `deploy/README.md`; re-run the presenter runbook.

## 9. Acceptance criteria (deltas to the original spec)

- AC-1 now means: `agentengine deploy` + platform invoke of
  `accrual-variance-review` runs the full flow (not a local adapter).
- AC-3/AC-4: retrieval results come from `MongoFilesystemBackend.grep()`
  with `$rankFusion`; the demo shows `GrepMatch` path/line provenance.
- AC-6: handoff demonstrated via deepagents `task()` dispatch **and** a
  durable `agent_handoffs` record.
- All other ACs unchanged; AC-10 adds an `agentengine agent validate` gate.
