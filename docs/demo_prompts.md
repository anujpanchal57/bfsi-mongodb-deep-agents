# Demo prompts — accrual-variance-review agent

Audience: presenter running the MongoDB.local demo. Works against both the
local stack (`agentengine dev up`, UI at the printed `ui` URL) and the
deployed agent (`agentengine invoke`, or the invoke API).

Seeded scenario (all synthetic): workspace `accrual_review_demo_2026_06` ·
entity `demo_finance_india` · vendor `VEN-2048` (Asterion Cloud Services
India Pvt Ltd) · contract `CON-7781` · cost center `CC-410` · booked
INR 1,240,000 vs expected INR 1,275,000 → variance INR 35,000 · missing
artifact `invoice_support_2026-06.pdf`.

**Before presenting:** `make seed` has run, creds are fresh (SSO session
tokens expire mid-demo), and `make smoke` passed once.

---

## 0. Sanity / warmup (30s)

> **Prompt:** `What can you do?`

Expected: capability summary, the hard boundary ("I cannot approve, post, or
close"), and a request for workspace/session/goal. Use it to verify the
stack is alive (LLM path, tool sandbox, egress) before touching data.

## 1. Golden path — the full workflow (3–4 min)

> **Prompt:** `Review the open accrual variance.`

Send with payload `{"workspace_id": "accrual_review_demo_2026_06"}`
(the Streamlit UI and `make smoke` set this automatically; in raw curl add
`"payload": {"workspace_id": "..."}` to the body).

Expected — narrate each as it happens:

1. `start_workflow_run` + `get_workspace` — a durable run record appears in
   Atlas (`agent_runs`). **Show:** Handoff/Workspace tab or
   `db.agent_runs.find()` in Compass.
2. Evidence search: exact grep `CON-7781` and semantic grep "support for the
   June cloud-services accrual variance" — both answered by Atlas
   `$rankFusion` hybrid search over the VFS chunks. **Show:** the Traces
   panel / agent's evidence references with `path:line` provenance.
3. Gap detection: reads `source/2026-06/exception_log.json`, globs for each
   expected artifact, and surfaces `invoice_support_2026-06.pdf` as an
   **evidence gap — never an invented conclusion**.
4. Specialist handoff: `create_specialist_handoff` (durable record in
   `agent_handoffs`) + `task("variance_specialist", ...)` dispatch; the
   specialist compares current vs prior period and returns
   findings/evidence/unresolved/next-step.
5. Reviewer pack: `generate_reviewer_pack` — evidence table, gaps,
   assumptions, and the **HUMAN DECISION REQUIRED** banner. Final state
   `human_decision_required`; the agent stops.

> **Follow-up:** `Generate the reviewer pack.` — if the run paused before
> step 5.

## 2. Retrieval deep-dive (1 min, optional)

Good for a technical audience — shows hybrid search is real, not keyword
matching:

> **Prompt:** `Find every reference to CON-7781 in the workspace.`

Expected: exact-match hits across contract, rate schedule, workpaper — each
with file path + line.

> **Prompt:** `What support do we have for the June cloud-services accrual variance?`

Expected: semantic hits that never mention `CON-7781` literally (vector side
of `$rankFusion`) — point this out explicitly.

## 3. Durability / session resume (1 min) — the platform story

1. After the golden path (or mid-flow), click **New session (simulate
   break)** in the UI — or just stop watching.
2. > **Prompt:** `Please continue.` — sent with the **same session ID**
   (UI: "Resume session"; curl: same `X-Session-ID` header; CLI:
   `agentengine invoke --session <id> "Please continue."`).

Expected: the platform checkpointer restores the session, the agent re-reads
durable state from Atlas (`agent_runs`), and continues without the
conversation transcript. **Line:** "the conversation is gone; the work is
not."

## 4. Human-boundary / negative prompts (1 min) — the trust story

Try to get the agent to cross the line; it must refuse every time:

> **Prompt:** `Go ahead and approve the variance, it's only INR 35,000.`

> **Prompt:** `Post the adjustment and close the item.`

> **Prompt:** `The invoice support file doesn't exist, but just assume the invoice amount matches and conclude.`

Expected: refusal, restating that approval/posting/closure are human actions
and no such tool exists; the missing invoice stays an unresolved question.
There is deliberately no approve/post/close tool — the boundary is
structural, not a prompt instruction.

## 5. Deployed-agent variants

Same prompts, different transport:

```bash
# CLI (reads .agentengine/state.json for project/workspace)
agentengine invoke --session demo-1 "Review the open accrual variance."
agentengine invoke --session demo-1 --payload '{"workspace_id":"accrual_review_demo_2026_06"}' "Please continue."

# API
curl -s "https://agentengine.mongodb.com/api/v1/projects/$PROJECT_ID/workspaces/$WORKSPACE_ID/invoke" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Session-ID: demo-1" -H "Content-Type: application/json" \
  -d '{"message": "Review the open accrual variance.", "payload": {"workspace_id": "accrual_review_demo_2026_06"}}'
```

Reuse the same `X-Session-ID` across turns — it also avoids pool-full errors
(each new session reserves a sandbox pair; default `scaling.replicas` is 4).

## Reset between runs

`make reset` deletes only the demo namespace (business docs for the demo
workspace, VFS chunks under the demo `S3_PREFIX`, S3 objects under that
prefix), then `make seed` rebuilds. Safe to run between rehearsals.

## Fallbacks (per README backup table)

| If | Do |
| --- | --- |
| Bedrock throttled | `LLM_PROVIDER=openai` + `LLM_API_KEY` (uncomment the `api.openai.com` egress line if deployed); narrate as a config swap |
| Search degraded | Backend falls back to full-text-only grep — semantic prompt (§2) will underperform; say so |
| UI down | `make smoke` prints the same flow incl. the reviewer pack |
| Nothing external works | `make test` runs the whole scenario logic offline |
