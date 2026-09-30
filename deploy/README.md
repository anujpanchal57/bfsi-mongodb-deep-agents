# Deployment: Atlas Agent Engine

## Contract mapping

| Platform concept | This repo |
| --- | --- |
| Project config | `project-config.yaml` (repo root) — `memory:` block for the project-scoped memory server |
| Agent workspace | `accrual-variance-review/` — all `agentengine` agent commands run from here |
| Agent manifest | `accrual-variance-review/agent.yaml` — `entrypoint: src.demo_agent.main:app`, `features.deep_agent: true`, `features.memory: true` |
| Local dev settings | `dev.yaml` (external Atlas: `services.mongodb.local: false`, so `MONGODB_URI` in `.env` is required) |
| Entrypoint object | `src/demo_agent/main.py` → `app = App(app_name="accrual-variance-review")`; `app.run()` at module bottom |
| Graph factory | `@app.entrypoint build_agent()` → `app.deep_agent(llm, tools, subagents, system_prompt, backend=MongoFilesystemBackend(...))` |
| Business tools | `src/demo_agent/tools.py` → `register(app)` (@app.tool() wrappers) |
| Subagent | `src/demo_agent/subagents.py` → `VARIANCE_SPECIALIST` (dispatched via deepagents `task()`) |
| Workspace backend | `src/demo_agent/backend.py` → `MongoFilesystemBackend` (grep/glob/ls → Atlas `$rankFusion`; read/write → S3; Bedrock Titan embeddings by default) |
| Durable sessions | `app.checkpointer()` (MongoDB) + durable business state in `agent_runs` |
| Secrets | `agentengine secret set AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (Bedrock LLM + embeddings; least-privilege IAM user) + `MONGODB_URI` (stored by `agentengine atlas setup`); `LLM_API_KEY` only for the openai/anthropic fallback. Sandbox access via `sandboxes.*.secrets` in `agent.yaml` |
| Archive filtering | `.agentengineignore` |

## Prereqs

1. `agentengine` CLI: download from https://agentengine.mongodb.com/download-cli
   (verify the SHA-256 shown on the page), install to `~/.local/bin`, then
   `agentengine auth login` (browser flow). Update later with
   `agentengine self-update`.
2. Python 3.11+ and [uv](https://docs.astral.sh/uv/) — `agentengine init`
   requires the `[build-system]` block in `pyproject.toml` (present).
3. Docker Desktop running (local dev + image builds).
4. An Atlas **service account** (client ID/secret) with **Project Owner** on
   the target project. Legacy Atlas API keys and user logins are not
   supported by `agentengine atlas setup`.
5. Atlas cluster M10+ (Vector Search + Full-Text Search) — or let
   `agentengine atlas setup` provision one (new clusters are paid Atlas Flex).
6. AWS: S3 bucket + IAM with `s3:GetObject/PutObject/DeleteObject/ListBucket`,
   and `bedrock:InvokeModel` / `bedrock:InvokeModelWithResponseStream` on the
   Titan embed model (`amazon.titan-embed-text-v2:0`) **and** the chat model
   inference profile (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) plus the
   underlying model ARNs it routes to. **Pre-session checklist:** enable model
   access for Claude Sonnet 4.5 in the demo account/region (manual console
   step) and confirm the exact `us.*` profile ID.
7. Python SDK packages are on public PyPI (`agent-engine-sdk-langgraph`,
   `agent-engine-runner-shared`, `langchain-mongodb-deepagents-vfs`) —
   `uv sync` resolves them; no private index or vendored wheels.

## Steps

```bash
make install                              # uv sync --extra ui --extra test
agentengine init                          # register workspace; writes .agentengine/state.json
                                          # (run from accrual-variance-review/; make targets cd there)
make atlas-setup                          # service account -> cluster, IP access,
                                          # DB user, MONGODB_URI platform secret
agentengine secret set AWS_ACCESS_KEY_ID      # Bedrock LLM + embeddings
agentengine secret set AWS_SECRET_ACCESS_KEY
# memory (features.memory: true): project-scope secrets — Voyage key from
# `agentengine atlas voyage-api-key list`; LLM_API_KEY must be a REAL
# Anthropic key (memory extraction; Bedrock is not a supported extraction
# provider — see specs/memory_enablement_spec.md §2.3)
agentengine secret set VOYAGE_API_KEY --project-scope
agentengine secret set LLM_API_KEY --project-scope
make memory-configure                     # upload memory: block from project-config.yaml
agentengine atlas link                    # grant sandboxes network access to Atlas
make validate-agent                       # agentengine agent validate --strict
make seed                                 # S3 upload/verify -> backend sync
make dev                                  # agentengine dev up; note the printed ui URL
make smoke                                # end-to-end against the local stack
make deploy-auto                          # build + deploy in one step (provisions
                                          # the memory server on first memory deploy)
                                          # (or: make deploy for the two-step path)
```

Memory config changes after deploy need no redeploy: `make memory-configure
&& make memory-apply`; check with `make memory-status`. Note: the docs flag
`agentengine memory configure` for future removal in favor of UI-based
management — re-check at rehearsal. Cluster tier: Atlas Flex minimum, M10+
recommended; a deploy stalled at `Memory: waiting` means the cluster can't
create the required Search/Vector indexes.

Record after first successful deploy:
`AGENTENGINE CLI VERSION TESTED: <fill in>` ·
`AGENT-ENGINE-SDK VERSION TESTED: <fill in>`

## Invoke

Deployed:

```
POST https://agentengine.mongodb.com/api/v1/projects/{project_id}/workspaces/{workspace_id}/invoke
Authorization: Bearer <api key>
X-Session-ID: <session id>
{"message": "...", "payload": {"workspace_id": ...}}
```

Local dev: same body against the `ui` URL printed by `agentengine dev up`
(`http://localhost:<port>/invoke`). Session continuity is the `X-Session-ID`
header — the same ID resumes the session via the platform checkpointer; the
agent also re-reads durable business state from Atlas.

`src/platform_client.py` is the single place that knows this contract; it
reads project/workspace IDs from env (`AGENT_ENGINE_PROJECT_ID` /
`AGENT_ENGINE_WORKSPACE_ID`) or `.agentengine/state.json`. The CLI equivalent
is `agentengine invoke --session <id> [--payload <json>] "message"`.

## Fallback (label clearly as LOCAL, not the deployed path)

```bash
agentengine dev up        # same agent, local stack
make ui / make smoke      # same invoke path via AGENT_ENGINE_URL
```

## Troubleshooting

- `agentengine deploy logs` — deployment event log
- `agentengine logs` — deployed workspace logs
- `agentengine dev status` / `agentengine dev logs` — local stack
- Most common deploy failures: misconfigured secrets; Atlas IP access list
  not allowing Agent Engine traffic (`agentengine atlas setup` handles both).
