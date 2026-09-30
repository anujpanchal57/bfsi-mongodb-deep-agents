# AGENTS.md — atlas-vfs-deepagents-bfsi

BFSI conference demo: durable, evidence-driven month-end accrual variance
review on MongoDB Atlas Agent Engine. Human-in-the-loop by design: the agent
proposes, never approves/posts/closes — no such tool exists (structural
boundary, keep it that way).

## Layout (two-level, required by the platform memory service)

- `project-config.yaml` (root) — project-scoped `memory:` config.
- `accrual-variance-review/` — the agent workspace; ALL `agentengine`
  commands and `uv`/pytest run from here (Makefile targets `cd` in).
  - `agent.yaml` (manifest), `dev.yaml` (local dev: external Atlas),
    `pyproject.toml` + `uv.lock` (commit the lock; `uv lock` after dep
    changes, then `agentengine dev restart`), `.env` (gitignored, real
    secrets), `src/`, `tests/`, `scripts/`, `data/`.
- `docs/` — usecase.md (explainer), demo_prompts.md (presenter runbook),
  slides.md (slide content + mermaid architecture).
- `specs/` — design specs incl. memory_enablement_spec.md (memory design +
  pending items) and feedback_agentengine_cli_bedrock_preflight.md.
- `deploy/README.md` — deployment runbook.

## Key code facts

- Entrypoint `accrual-variance-review/src/demo_agent/main.py`:
  `app = App(...)`; `app.run()` is called UNCONDITIONALLY at module bottom
  (platform imports the module). Do NOT wrap the LLM with `app.llm()` before
  `app.deep_agent()` — it double-registers and fails startup.
- `RUNNER_MODE=tool`: the tool sandbox re-executes the entrypoint just to
  discover LLM registrations, with deny_all egress — `build_agent()` skips
  `create_backend()` there. Any network I/O at graph-build time breaks LLM
  routing ("llm_id '__default__' is not registered").
- LLM (`src/demo_agent/llm.py`): providers bedrock (default, Converse API,
  boto3 chain) | anthropic | openai; `LLM_BASE_URL` + `LLM_AUTH_HEADER`
  support corporate gateways (e.g. APIM needs `LLM_AUTH_HEADER=api-key`).
- VFS paths are rooted at `/agent-engine-demo/` (the S3 prefix); prompts
  must use paths exactly as grep/glob/ls return them — bare paths fail with
  E2009.
- LLM-persisted findings may be plain strings — reviewer_pack.py guards
  with isinstance; keep that tolerance when editing it.
- Memory tools (`memory_tools.py`): `recall_context` / `remember_fact`;
  remember_fact hard-refuses approval-shaped content. Memory invoke requires
  `user_id` in the request body. Memory extraction is async — LTM is not
  available on the next turn.

## Commands

- `make test` (offline; integration tests skip unless AGENT_ENGINE_URL set),
  `make seed` / `make reset` (reset deletes ONLY the demo namespace),
  `make dev` (`agentengine dev up`), `make validate-agent`,
  `make deploy-auto`, `make memory-configure|apply|status`, `make smoke`.
- `agentengine agent validate --strict` must pass after editing agent.yaml.

## Environment gotchas (learned the hard way)

- CLI `dev up` preflight requires an LLM key var in `.env`
  (OPENAI/ANTHROPIC/.../LLM_API_KEY) — for Bedrock, a commented placeholder
  `LLM_API_KEY=unused-...` satisfies it (see specs/feedback doc).
- Egress: allowlist needs BOTH `s3.<region>.amazonaws.com` AND legacy global
  `s3.amazonaws.com`, each plus wildcard (`*.<bucket>.s3...`
  virtual-hosted), plus `openaipublic.blob.core.windows.net` (tiktoken),
  plus the LLM host on BOTH sandboxes (LLM calls egress from the TOOL
  sandbox). Proxy 403s never name the denied host — trace via container logs.
- AWS creds in .env are SSO session tokens and EXPIRE mid-work — S3
  HeadBucket then returns 400 Bad Request (misleading). Refresh:
  `aws sso login --profile anuj-dev` (SSO session anuj-ps), export creds.
- Atlas API access (`agentengine atlas *`) is behind the org IP access list.
- `project-config.yaml` `extraction_llm.api_key_secret` takes the NAME of an
  env var (`LLM_API_KEY`), never the key value — a literal key fails
  ProjectConfig validation and crash-loops memory-server on `dev up`.
- `.env.example` is placeholders ONLY — real credentials were once committed
  there and pushed to GitHub; they were rotated and the file masked. Never
  put real values in it again.

## Conventions

- Ponytail mode: minimal diffs, stdlib first, no speculative abstractions.
- Specs live in specs/ and are status-marked (proposal/implemented + date).
- Tests: offline-first; one small test per non-trivial logic change, no
  framework fixtures beyond the existing conftest.
