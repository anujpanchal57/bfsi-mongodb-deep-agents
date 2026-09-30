# Spec: Human review step via Agent Engine `require_review` guardrail

Status: **proposal 2026-09-30.** Based on the public docs (Use Content
Guardrails), fetched 2026-09-30:
https://www.mongodb.com/docs/agentengine/manage/governance/guardrails/

## 0. Why

The demo's narrative is "the agent proposes, the human disposes." Today that
boundary is **structural** — no approve/post/close tool exists, so the agent
literally cannot complete those actions. That stays. This spec adds a second,
**platform-enforced** layer: when the agent emits decision-shaped output (the
reviewer pack / recommendation), the Orchestration Engine (OE) suspends the
execution and holds it until a human reviewer approves. The demo story
upgrades from "we chose not to give the agent the tool" to "the platform
itself gates the output."

Two layers, complementary:

| Layer | Mechanism | Gates |
| --- | --- | --- |
| Structural (existing) | No approval tool in `tools.py`; `remember_fact` refuses approval-shaped content | Agent *actions* |
| Guardrail (this spec) | OE `require_review` on `llm_output` | Agent *content* |

## 1. What the docs support

Guardrails are project-level content controls enforced by the OE on every
execution. Relevant facts from the docs:

- **Type:** only `output_validation` exists today — evaluates content against
  regex patterns in `config.match_patterns`.
- **Action `require_review`:** "Suspends the execution for human review. The
  execution proceeds only after a reviewer approves it." This *is* the
  human-in-the-loop step.
- **Stages:** `llm_input` (before the model call) and `llm_output` (before
  the model's response returns to the user). We want `llm_output`.
- **Scoping:** `workspace_ids` limits a guardrail to specific workspaces;
  empty = every workspace in the project.
- **Precedence:** when multiple guardrails match, most restrictive wins:
  `block` > `require_review` > `modify` > `log_only`.
- **Propagation:** changes take effect on the next execution; in-flight
  executions are unaffected.
- **Management:** Platform UI (Manage → Policies → Guardrails tab) or REST
  API (`create`/`update` with a JSON body).
- **Limitation:** guardrails control *content* only. Tool/action gating is
  the Policy Engine's job — out of scope here.

## 2. Proposed guardrail

One guardrail on the accrual-variance-review workspace:

```json
{
  "name": "reviewer-pack-human-review",
  "description": "Suspend execution when the agent emits a reviewer pack or "
                 "recommendation; a human reviewer must approve before the "
                 "output is released.",
  "type": "output_validation",
  "action": "require_review",
  "status": "active",
  "stage_filter": ["llm_output"],
  "workspace_ids": ["<accrual-variance-review workspace id>"],
  "config": {
    "match_patterns": [
      { "type": "regex", "value": "(?i)reviewer pack" },
      { "type": "regex", "value": "(?i)recommendation\\s*:" }
    ]
  }
}
```

Pattern rationale: the agent's terminal artefact is the reviewer pack
(`generate_reviewer_pack` tool, step 5 "PACK" in the orchestrator prompt).
Matching on "reviewer pack" / "recommendation:" catches exactly the
decision-shaped output and little else. Interim tool chatter (grep results,
evidence rows) does not contain these phrases, so review triggers once per
run, at the moment that matters.

Start with `status: "inactive"` or `action: "log_only"` for one dry run to
confirm the patterns match the pack and nothing else, then flip to
`require_review` for the demo.

## 3. What changes in this repo

Deliberately little — the guardrail is platform config, not agent code.

1. **Nothing in `src/`.** No code change. The structural boundary
   (no approval tool) is untouched; `main.py`, `tools.py`, `memory_tools.py`
   stay as-is.
2. **`docs/demo_prompts.md`:** add a beat — after the PACK step, the run
   suspends; presenter shows the pending review in the platform UI and
   approves it live; the execution then resumes and returns the pack.
3. **`docs/slides.md`:** one bullet in the governance/architecture section —
   "Platform-enforced human review: OE `require_review` guardrail suspends
   decision-shaped output until a reviewer approves" (complementing the
   existing "no approval tool" structural boundary).
4. **`docs/usecase.md`:** one line noting the two enforcement layers.

## 4. Demo flow after implementation

1. Presenter runs the review prompt (existing beats unchanged through PACK).
2. Agent emits the reviewer pack → guardrail matches → OE **suspends** the
   execution instead of returning the output.
3. Presenter opens Manage → Policies / the review surface, shows the held
   output and the matched guardrail.
4. Presenter approves → execution resumes → pack is delivered.
5. Narrative line: "The agent proposed. The platform held it. The human
   disposed."

## 5. Open items (verify before implementing)

- **Review/approve surface:** the docs page describes the suspension
  semantics but not where the reviewer approves (a review queue in the UI, or
  an API endpoint). Confirm against the platform UI or the Agent Engine API
  reference before writing the demo beat. *Pending.*
- **Reviewer identity/RBAC:** who in the project may approve (project admin
  vs. a reviewer role). *Pending.*
- **Rejection path:** docs state "proceeds only after a reviewer approves"
  but don't specify reject semantics (error to caller? resume with
  feedback?). Verify behaviour before promising it on stage. *Pending.*
- **Workspace ID:** fetch via `agentengine` CLI / Atlas UI at apply time
  (Atlas API is behind the org IP access list — allowlist first).

## 6. Out of scope

- Policy Engine (tool/action gating) — separate feature, separate spec if
  ever needed.
- `block`/`modify` guardrails (PII redaction etc.) — not needed for the
  demo narrative.
- Any agent-code "interrupt" mechanism (e.g. LangGraph `interrupt()`) —
  superseded by the platform guardrail; don't build both.
