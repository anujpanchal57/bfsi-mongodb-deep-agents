# Change spec: align with latest public Atlas Agent Engine docs

Status: **implemented 2026-09-29** (with two evidence-based deviations noted
inline: §1, §4). Diffed 2026-09-29 against the public docs
(`mongodb.com/docs/agentengine/`: get-started, agent-contract, create-project,
run-local, build-deep-agent, invoke-agent, network-egress). Supersedes the
private-docs assumptions in `agent_engine_alignment_spec.md` where they
conflict. Items are ordered by severity; P0 = blocks build/deploy.

## P0 — Breaks against the documented contract

### 1. Custom `backend=` in `app.deep_agent()` is now rejected

`src/demo_agent/main.py` passes `backend=create_backend()`
(`MongoFilesystemBackend`). Per Build a Deep Agent → Security Validations,
`App.deep_agent()` now **rejects a manually supplied backend at
initialization** — the platform enforces its own
`AgentEngineToolSandboxBackend` (filesystem/shell via the tool sandbox,
exposed as `filesystem_*` / `shell_execute` tools). The old spec's "RESOLVED:
pass backend=" note is no longer valid.

Required change — pick one:

- **(a) Recommended: keep `deep_agent`, move VFS behind tools.** Drop the
  `backend=` kwarg. Instantiate `MongoFilesystemBackend` in module scope and
  expose its operations as `@app.tool()`s (e.g. `vfs_grep`, `vfs_read`,
  `vfs_ls`) that the orchestrator prompt prefers over the built-in
  `filesystem_*` tools. Keeps `features.deep_agent: true`, subagents,
  checkpointer, and the audited LLM path. Cost: VFS I/O is no longer the
  agent's filesystem; it is tool calls (which the demo narrative already
  treats it as).
- **(b) Drop `deep_agent`.** Build the graph manually
  (`create_deep_agent(backend=MongoFilesystemBackend(...))` from the
  `deepagents` library directly, compiled with `app.checkpointer()`), remove
  `features.deep_agent`. Keeps the VFS-as-filesystem UX but loses the
  platform's sandboxed filesystem/shell handlers and the documented
  deep-agent path.

Either way: delete the `backend=` argument from `app.deep_agent()` before the
next build, or the agent fails to start.

> **Implementation outcome (deviation, evidence-based):** the shipped SDK
> (`agent-engine-sdk-langgraph` 0.11.6, latest on PyPI) does **not** reject a
> custom backend — `App.deep_agent()` accepts `backend=` with a
> bypass-the-audit warning in its docstring, and no rejection check exists in
> the source. The docs page describes stricter behavior than the shipped
> artifact. Decision: **keep `backend=MongoFilesystemBackend(...)`** (the
> demo's core architecture) with the mismatch documented in
> `src/demo_agent/main.py`. If a future SDK version enforces the documented
> rejection, apply option (a) above.

### 2. `agent.yaml` fields not in the current schema

Per the Agent Contract Reference, the `features` block accepts only
`guardrails`, `memory`, `deep_agent`, `playground`, `use_custom_parser`, and
there is **no top-level `required_secrets`** field.

- Remove `features.durable_workflow: true` — durability is now implicit via
  `app.checkpointer()` (MongoDBSaver), no flag exists.
- Remove the whole `required_secrets:` block. Secrets are declared only via
  `sandboxes.agent.secrets` / `sandboxes.tool.secrets`. `MONGODB_URI` is
  automatically available to every sandbox and must not be declared. The
  `aer:` terminology is gone (now Agent Sandbox / Tool Sandbox / OE).
- Keep `sandboxes.tool` but note: to call an LLM from a tool body, the docs
  require listing the built-in `invoke_llm` tool in `sandboxes.tool.tools`
  plus the provider key in `sandboxes.tool.secrets`. We don't call LLMs from
  tool bodies, so `tools: []` stays.
- Add `ports: [443]` to each `network.egress` entry (`s3.us-east-1...`,
  `api.openai.com`, `bedrock-runtime...`). Port-less entries are accepted but
  allow **all** ports and raise warnings; the deploy expects an explicit
  egress policy since every workspace starts in `deny_all`.
- Optional: add `agent_card.summary`/`capabilities` (UI display) and a
  `scaling` block (`replicas` default 4; pool-full errors when exhausted —
  relevant for a booth demo with parallel sessions).

Gate: `agentengine agent validate --strict` must pass (exit 0).

### 3. `app.run()` never runs when imported

The contract: "Call the `app.run()` function at the bottom of the module."
`src/demo_agent/main.py` only calls it under `if __name__ == "__main__"`.
The sandbox imports the module — the guard never fires. Move to an
unconditional `app.run()` at module bottom (per the migrate-guide example),
keeping `main()` only if something else calls it.

### 4. Missing required dependency + unpinned deepagents

Per Create a Project / Migrate, the platform requires **two** packages:
`agent-engine-runner-shared` and `agent-engine-sdk-langgraph`. Build a Deep
Agent pins `deepagents==0.5.3`.

- Add `agent-engine-runner-shared` to dependencies.
- Pin `deepagents==0.5.3` (docs' tested version). **Deviation:** the VFS
  backend package (`langchain-mongodb-deepagents-vfs` 0.1.0) requires
  `deepagents>=0.6.0`, and the SDK constrains deepagents only in its dev
  extra (runtime import is lazy) — so we follow the VFS constraint
  (`deepagents>=0.6.0,<1`); `==0.5.3` is unsatisfiable here.
- Move the `[project.optional-dependencies].platform` set into main
  `dependencies` (or confirm the managed build installs extras — the docs
  show them as plain deps). The build runs `uv sync`; extras are not synced
  by default.
- Commit `uv.lock` — with a lockfile present, dev/deploy sync with
  `--frozen`; dependency changes need `uv lock` + `agentengine dev restart`.
- SDK distribution: the public docs install both packages with plain
  `uv add` — verify they are now on public PyPI; if so, delete the
  private-index / `wheels/` machinery from `deploy/README.md` and the
  `artifact_repositories` plan.

## P1 — Flow and tooling drift

### 5. CLI install & auth instructions are outdated

`deploy/README.md` says "CLI from `mongodb/atlasap` GitHub releases."
Current: download from `https://agentengine.mongodb.com/download-cli`
(verify SHA-256), install to `~/.local/bin`, then `agentengine auth login`
(browser flow) and later `agentengine self-update`. Update deploy/README.md
and README.md prereqs.

### 6. Missing `agentengine atlas setup` step

The deploy flow now requires `agentengine atlas setup` before secrets/build:

- Atlas **service account** (client ID/secret) with **Project Owner** —
  legacy Atlas API keys and user logins are explicitly unsupported.
- Provisions/selects the cluster (new = paid Atlas Flex), configures the IP
  access list, creates the DB user, and stores `MONGODB_URI` as a platform
  secret.
- Also creates a Voyage AI key (only needed if memory is later enabled; ours
  stays `memory: false`).

Add to Makefile/deploy steps between `init` and `secret set`. For sandbox
network access to Atlas, use `agentengine atlas link` (or the
`network.atlas_clusters` block), not egress FQDNs.

### 7. Deploy command

`agentengine deploy --auto` (build + deploy in one step) is the documented
single-agent path. Keep `agentengine build && agentengine deploy` as the
two-step alternative already in the Makefile; add `make deploy-auto`.

### 8. Invoke contract changed — `src/platform_client.py`

Deployed invoke is now:

```
POST /api/v1/projects/{project_id}/workspaces/{workspace_id}/invoke
Authorization: Bearer <api key>
X-Session-ID: <session id>
{"message": "...", "payload": {...}}     # payload = JSON metadata, optional
→ {"success": true, "response": "...", "execution_id": "...", "status": "completed"}
```

Current client posts `{"input": {"message": ..., "payload": {session_id...}}}`
to `{AGENT_ENGINE_URL}/invoke`. Changes:

- Flatten the body: top-level `message` and `payload`.
- Move `session_id` from the payload to the `X-Session-ID` header (1–128
  chars, `[A-Za-z0-9_-]`; response returns it in the same header). Reusing
  session IDs also avoids pool-full errors (§2 scaling note).
- Config: replace the single `AGENT_ENGINE_URL` with base URL + project ID +
  workspace ID for the deployed path (readable from `.agentengine/state.json`
  after `agentengine init`); the local `agentengine dev up` UI stays
  `http://localhost:<ui-port>/invoke` with the same `{"message": ...}` body.
- `/health` (used by `platform_health`) is not a documented endpoint —
  verify against the dev stack or drop in favor of `agentengine dev status`.
- Optional: `agentengine invoke [--session] [--payload]` now exists and
  handles HITL prompts — simplest replacement for `scripts/smoke_demo.py`'s
  HTTP plumbing.
- Optional: `/invokeStream` (SSE) for the Streamlit UI if live narration is
  wanted; suspend/resume endpoints exist if we later adopt platform HITL
  (`interrupt()`). Not required — our human boundary stays tool-enforced.

## P2 — Layout and housekeeping

### 9. Project layout — no change required, one decision

`agentengine create` scaffolds `project-config.yaml` + `agents/<slug>/`, but
the manual-setup path (root `agent.yaml` + `.env` + `pyproject.toml`) remains
fully supported — our root layout is valid. `project-config.yaml` is only
needed for `create`-scaffolded projects and memory config. **Keep the root
layout**; run all `agentengine` commands from the repo root.

### 10. Generated files to expect / ignore

`agentengine init` generates `docker-compose.yml`, `.agentengine/`
(Dockerfile, entrypoint.py, **state.json** with workspace/org/project IDs),
`.dockerignore`, `.gitignore`. `agentengine dev up` generates
`.agentengine/docker-compose.dev.yml`, `Dockerfile.dev`, `dev-entrypoint.py`,
`.devcontainer/`. Add `.agentengine/state.json`-adjacent generated artifacts
to `.gitignore`/`.agentengineignore` policy as desired (state.json is the
local link to the workspace — do not delete; commit decision per team).

### 11. `.env` is the only runtime secret source locally

The dev container mounts **only** `.env` — host env vars are ignored.
`dev.yaml` (`services.mongodb.local: false`) is correct per the current
schema; with it, `MONGODB_URI` in `.env` is mandatory. `.env.example` already
covers this; make sure every var the agent reads (`LLM_API_KEY`, S3 creds if
not via IAM chain, `S3_BUCKET`, `S3_PREFIX`) lands in the real `.env`.

### 12. Docs/comments cleanup

- `deploy/README.md`: rewrite prereqs (§5, §6), drop private-index/`wheels/`
  notes if SDK is public (§4), record tested CLI/SDK versions.
- `agent_engine_alignment_spec.md`: mark superseded items — the `backend=`
  "RESOLVED" note (now rejected, §1) and `features.durable_workflow` (§2).
- README "Quick start" platform block: add `agentengine auth login` and
  `agentengine atlas setup`; note `make deploy` vs `deploy --auto`.
- `src/demo_agent/main.py` docstring: update the backend bullet per §1.

## Verified unchanged (no action)

- `agentengine agent validate` still exists (experimental; exit 0/1/2) — Makefile target stays.
- `dev.yaml` schema (`services.mongodb.local`) — current file conforms.
- `features.deep_agent: true` — still required for `app.deep_agent()`.
- Do **not** wrap the LLM with `app.llm()` before `deep_agent()` — it wraps
  internally (`SecureWrappedLLM`); double-wrapping fails startup. Current
  `llm=build_llm()` is correct.
- Subagent `SubAgent.model` must be an LLM instance, not a string — check
  `src/demo_agent/subagents.py` conforms (it builds a real model).
- `.agentengineignore`, `.env.example`, tests, seeding pipeline: unaffected
  by the docs diff (seeding changes only if §1 option (b) alters backend
  wiring).

## Suggested order

1. §4 deps + `uv lock`; confirm SDK on public PyPI.
2. §1 backend decision (recommend (a)); adjust `main.py`, tools, prompts.
3. §2 `agent.yaml` cleanup → `agentengine agent validate --strict`.
4. §3 `app.run()`.
5. §8 `platform_client.py` + smoke/UI re-point; test against `agentengine dev up`.
6. §5–§7 flow docs + Makefile targets; run `init → atlas setup → secret set → deploy --auto`.
7. §10–§12 housekeeping; re-run `make test` and the demo runbook.
