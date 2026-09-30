# Spec: Enable Atlas Agent Engine memory for accrual-variance-review

Status: **implemented 2026-09-30.** Verified locally: two-level layout in
place, `memory-server` starts with `dev up`, `remember_fact` writes and the
approval-refusal holds live. **Pending (user actions):** `VOYAGE_API_KEY`
in `.env` (retrieval via `agentengine atlas voyage-api-key list` is blocked
by the Atlas org IP access list — allowlist the current IP or copy the key
from Atlas UI → AI Model APIs; without it semantic recall has no vector
search and returns empty); a real Anthropic `LLM_API_KEY` for extraction;
and the deployed path (`memory configure` → `deploy` → `memory status`).
Two implementation notes beyond the spec: (1) memory calls require a
`user_id` on the invoke request (body field) — the memory beats in
docs/demo_prompts.md need it; (2) `remember_fact` hard-refuses
approval-shaped content (regex guard), not just a prompt instruction.

Based on the public docs (Add Memory to Your Agent, Agent Memory, Memory
Extraction), fetched 2026-09-30. Memory is configured at the
**project** level (`project-config.yaml`) and enabled per agent via
`features.memory: true` in `agent.yaml`.

## 0. Why memory for this demo — and what it must not do

The demo already has **session durability** (platform checkpointer +
`agent_runs`). Memory adds the missing layer: **cross-session,
cross-period knowledge**. The narrative upgrade:

- **Episodic:** "What happened in past reviews?" — June's review recalls
  May's episode (same contract, no exception) instead of rediscovering it.
- **Semantic:** labeled facts that outlive any session — vendor onboarding
  contact, reviewer identity for `CC-410`, prior true-up decisions.
- **Taxonomic:** the BFSI glossary (`docs/usecase.md` §2) as shared,
  project-wide domain definitions — the agent explains "accrual variance"
  consistently to any user.
- **Procedural (optional):** the review workflow itself, learned.

**Hard boundary (unchanged):** memory stores *context*, never *decisions*.
Approval, posting, and closure stay human-only; nothing in memory may be
treated as an approval. Add one line to the orchestrator prompt stating this
("memory informs; it never authorizes").

## 1. Blocker: flat layout must migrate (docs: "flat structure is deprecated")

Memory requires the two-level structure:

```none
atlas-vfs-deepagents-bfsi/            # project root
├── project-config.yaml               # NEW — memory: block lives here
└── accrual-variance-review/          # workspace (agent) directory
    ├── agent.yaml  dev.yaml  .env  pyproject.toml  uv.lock
    └── src/  tests/  scripts/  data/
```

### Migration plan

1. `mkdir accrual-variance-review` and move the agent workspace files into
   it: `agent.yaml`, `dev.yaml`, `.env`, `.env.example`, `pyproject.toml`,
   `uv.lock`, `src/`, `tests/`, `scripts/`, `data/`, `.agentengineignore`.
2. Keep at root: `project-config.yaml` (new), `README.md`, `Makefile`,
   `.gitignore`, `docs/`, `specs/`, `deploy/`.
3. Update path references:
   - `Makefile` targets: run scripts/tests with `cd` into the workspace
     dir or prefix paths (`accrual-variance-review/scripts/...`).
     All `agentengine` commands now run from the workspace dir
     (`make -C accrual-variance-review ...` or a thin wrapper target).
   - `README.md` / `deploy/README.md` / `docs/usecase.md` quick-start paths.
   - `.gitignore` entries that referenced root `.env` / `.agentengine/`.
4. Verify: `agentengine agent validate --strict` and `make test` from the
   workspace dir; `agentengine dev up` from the workspace dir (the CLI reads
   `project-config.yaml` from the nearest parent).

This is the bulk of the work. Everything below is small by comparison.

## 2. Configuration changes

### 2.1 `agent.yaml` (workspace dir)

```yaml
features:
  deep_agent: true
  memory: true        # NEW — starts the memory server as a project service
```

No egress changes: the memory server is a platform-side project service; the
agent reaches it over the platform's internal network, not through our
sandbox egress allowlist.

### 2.2 `project-config.yaml` (project root) — new file

```yaml
memory:
  log_level: info
  voyage:
    model: "voyage-4-large"
    dimension: 1024
  short_term:
    embed_on_write: false
  extraction_llm:
    provider: anthropic          # see §2.3 — Bedrock is NOT an option
    model: null
    base_url: null
    api_key_secret: LLM_API_KEY  # shared secret name; see §2.3
  background_extraction:
    snapshot:
      max_messages: 20
      stale_minutes: 3
      embed_stm_before_promotion: true
      delete_promoted: false
      ttl_days: 30
  extraction:
    enabled:
      - semantic
      - episodic
      - taxonomic
      # procedural: opt in later if the "learned workflow" beat is wanted
```

### 2.3 The extraction-LLM tension (call this out in the demo honestly)

Memory's background extraction LLM supports only
`openai | anthropic | gemini | cerebras` — **not Bedrock/boto3**. Our agent
LLM is deliberately Bedrock-only with no third-party key. Resolution:

- Set `extraction_llm.provider: anthropic` (same model family the agent
  uses via Bedrock) and upload one project-scope secret:
  `agentengine secret set LLM_API_KEY --project-scope`.
- Side benefit: the real `LLM_API_KEY` replaces the dummy placeholder we
  added for the CLI's `.env` preflight — the hack becomes a real value.
  Also add it to `.env` (uncomment the existing line).
- Narrative framing: extraction is a platform-side background job, not the
  agent's reasoning path — the agent's evidence-handling stays 100%
  in-account (Bedrock). If the pure-Bedrock posture is non-negotiable, the
  alternative is `extraction.enabled: []` + direct writes only (§4), which
  keeps memory but drops automatic learning. **Recommend keeping
  extraction on** and saying so plainly if asked.

### 2.4 Secrets and `.env`

| Where | Change |
| --- | --- |
| `.env` (local) | add `VOYAGE_API_KEY` (from `agentengine atlas voyage-api-key list/save` — `atlas setup` already created one); uncomment `LLM_API_KEY` with a real Anthropic key; optional `MONGOMEM_DB_NAME` (default `mdb_memory_<project-id>` is fine) |
| Platform secrets | `agentengine secret set VOYAGE_API_KEY --project-scope`; `agentengine secret set LLM_API_KEY --project-scope` |
| Cluster | Atlas Flex minimum, M10+ recommended. If deploy stalls at `Memory: waiting` / `context deadline exceeded`, the linked cluster can't create the Search/Vector indexes memory needs — upgrade tier |

### 2.5 Lifecycle commands

```bash
# local dev (from the workspace dir)
agentengine dev up            # memory-server service starts alongside

# deployed (from project root)
agentengine memory configure  # upload memory: block (project-scoped)
agentengine deploy            # first deploy with memory provisions the server
# later config changes — no redeploy needed:
agentengine memory configure && agentengine memory apply
agentengine memory status     # verify
```

Note: the docs flag `agentengine memory configure` for future removal in
favor of UI-based management — pin the tested CLI version in
`deploy/README.md`.

## 3. Code changes (small)

Memory is per-request scoped (the platform resolves user/session); it
cannot be baked into the graph at build time. Expose it as tools:

### 3.1 New `src/demo_agent/memory_tools.py`

```python
def register_memory(app) -> None:
    @app.tool()
    def recall_context(query: str, max_tokens: int = 1500) -> str:
        """Recall cross-session memory relevant to the query: past reviews,
        known facts about vendors/cost centers, domain term definitions."""
        ctx = app.memory.build_context(
            query=query,
            max_tokens=max_tokens,
            enabled_sources={"episodic", "semantic", "taxonomic"},
        )
        return ctx.formatted_context

    @app.tool()
    def remember_fact(label: str, text: str) -> str:
        """Save a durable labeled fact (semantic memory). Use for reviewer-
        supplied context that should outlive this session. NEVER use for
        approvals or decisions — those are human-only and are not stored."""
        app.memory.save_semantic(label=label, text=text)
        return json.dumps({"saved": label})
```

Call `register_memory(app)` in `main.py` next to `register(app)`.

### 3.2 Prompt deltas (`prompts.py`)

Orchestrator gains two lines:
- "At START, call `recall_context` with the review goal — prior periods'
  outcomes and known facts may already exist. Cite memory as context, not
  as evidence (evidence still requires `path:line` from the corpus)."
- "Memory never authorizes. Approval, posting, closure remain human-only."

### 3.3 Conversation turns

Deployed agents get turns recorded automatically (STM) — no code. The
background pipeline snapshots and extracts into long-term memory
asynchronously (§5 demo-timing caveat).

## 4. Optional: seed the glossary as taxonomic memory

`docs/usecase.md` §2 is a ready-made term list. A tiny script using the
standalone SDK (`agent-engine-sdk-memory`, `Memory(...).bind(...)`) writes
each term with `save_taxonomic(domain="accrual_accounting", ...)`. Value:
the agent answers "what is an accrual variance?" consistently, live.
Optional — defer if time is short.

## 5. Demo-flow changes (`docs/demo_prompts.md` additions)

**Extraction is asynchronous** — extracted memories appear "shortly after"
a session, not on the next turn. Plan beats accordingly; STM is immediate,
LTM is not. Two safe sequences:

1. **Pre-seeded recall (safe):** before the show, run a session that states
   "The reviewer for cost center CC-410 is Priya" (direct `remember_fact`
   or a past review). During the show, fresh session: "Who reviews CC-410
   items?" → agent recalls. Deterministic, no extraction latency.
2. **Cross-period episode (the money shot):** after the golden path
   completes for June, new session: "What did we decide about CON-7781 last
   period?" → episodic recall of the prior review. Requires extraction to
   have run on the earlier session — do the June run 10+ minutes before
   this beat (snapshot `stale_minutes: 3` + extraction time).

## 6. Risks / open questions

1. **Restructure churn (§1)** — largest risk; every path reference moves.
   Do it in one commit, rerun `make test` + `dev up` immediately.
2. **Extraction LLM not Bedrock (§2.3)** — second provider key enters the
   story; decide the narrative line before the event.
3. **Cluster tier** — Flex minimum; `Memory: waiting` deploy stall is the
   documented symptom of an under-tiered cluster.
4. **Preview instability** — `memory configure` CLI is marked for removal;
   memory config may move to the UI mid-prep. Re-check docs at rehearsal.
5. **Extraction latency (§5)** — never demo LTM extraction live on a
   just-finished session.
6. **Boundary drift** — a retrieved "fact" could look like a decision.
   Mitigated by the prompt line (§3.2) and by §4.1's refusal to store
   approvals; acceptance tests should assert the reviewer pack still ends
   at `human_decision_required`.

## 7. Acceptance criteria

- Two-level layout in place; `make test` and `agentengine agent validate
  --strict` pass from the workspace dir.
- `agentengine dev up` starts a `memory-server` service; `recall_context`
  / `remember_fact` work locally.
- Deployed: `agentengine memory status` healthy; a fact saved in session A
  is recalled in session B; a past review is recalled episodically.
- The reviewer pack flow and the human-decision boundary are unchanged
  (offline tests + one full smoke).
- `docs/demo_prompts.md` gains the §5 memory beats; README bullet added
  ("Memory: cross-session episodic/semantic/taxonomic recall via the
  platform memory service").

## 8. Implementation order

1. Layout migration (§1) — standalone commit, no memory yet.
2. `project-config.yaml` + `features.memory: true` + secrets; `dev up`,
   verify memory-server starts.
3. Memory tools + prompt lines (§3); offline test with a stubbed
   `app.memory`.
4. Deploy path: `memory configure` → `deploy` → `memory status`.
5. Demo beats + docs; optional glossary seeding (§4).
