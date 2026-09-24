# Deployment: Atlas Agent Engine

## Contract mapping

| Platform concept | This repo |
| --- | --- |
| Agent manifest | `agent.yaml` (repo root) — `entrypoint: src.demo_agent.main:app`, `features.deep_agent: true`, `features.durable_workflow: true` |
| Local dev settings | `dev.yaml` (external Atlas: `services.mongodb.local: false`) |
| Entrypoint object | `src/demo_agent/main.py` → `app = App(app_name="accrual-variance-review")` |
| Graph factory | `@app.entrypoint build_agent()` → `app.deep_agent(llm, tools, subagents, system_prompt, backend=MongoFilesystemBackend(...))` |
| Business tools | `src/demo_agent/tools.py` → `register(app)` (@app.tool() wrappers) |
| Subagent | `src/demo_agent/subagents.py` → `VARIANCE_SPECIALIST` (dispatched via deepagents `task()`) |
| Workspace backend | `src/demo_agent/backend.py` → `MongoFilesystemBackend` (grep/glob/ls → Atlas `$rankFusion`; read/write → S3; Bedrock Titan embeddings by default) |
| Durable sessions | `app.checkpointer()` (MongoDB) + durable business state in `agent_runs` |
| Secrets | `agentengine secret set MONGODB_URI` / `LLM_API_KEY` (declared in `required_secrets`) |
| Archive filtering | `.agentengineignore` |

## Prereqs

1. `agentengine` CLI from `mongodb/atlasap` GitHub releases.
2. Python 3.11 locally for parity with the runner-base image.
3. Atlas cluster M10+ (Vector Search + Full-Text Search).
4. AWS: S3 bucket + IAM with `s3:GetObject/PutObject/DeleteObject/ListBucket`
   and `bedrock:InvokeModel` for `amazon.titan-embed-text-v2:0` in the demo
   region.
5. The Python SDK until its first public release: private index or a
   vendored `wheels/` directory next to `agent.yaml` (platform builds pick up
   `wheels/` via `uv sync --find-links`). Private-index mechanism: mint a 1h
   token from the service account (`POST /api/v1/oauth/token`,
   `client_credentials`), then
   `uv pip install agent-engine-sdk-langgraph --extra-index-url "https://ignore:${ACCESS_TOKEN}@agentic-platform.mongodb.com/api/v1/packages/python/simple/"`.
   SA creds live in AWS Secrets Manager; never in git.

## Steps

```bash
pip install -e ".[platform]"
agentengine init                          # registers the agent from agent.yaml
agentengine secret set MONGODB_URI
agentengine secret set LLM_API_KEY
agentengine agent validate
make seed                                 # S3 upload/verify -> backend sync
agentengine dev up                        # local stack; AGENT_ENGINE_URL printed
make smoke                                # end-to-end against the local stack
agentengine build
agentengine deploy
```

Record after first successful deploy:
`AGENTENGINE CLI VERSION TESTED: <fill in>` ·
`AGENT-ENGINE-SDK VERSION TESTED: <fill in>`

## Invoke

The UI and `scripts/smoke_demo.py` call
`POST {AGENT_ENGINE_URL}/invoke` with `{"input": {"message": ...,
"payload": {"session_id": ..., "workspace_id": ...}}}` — see
`src/platform_client.py` (the single place to adjust if the platform route
differs).

Resume after a session break: same `session_id` in the payload; the platform
checkpointer restores the session and the agent re-reads durable business
state from Atlas.

## Fallback (label clearly as LOCAL, not the deployed path)

```bash
agentengine dev up        # same agent, local stack
make ui / make smoke      # same invoke path via AGENT_ENGINE_URL
```
