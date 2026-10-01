# Spec: Remove the `require_review` guardrail; human approval as a walkthrough beat

Status: **implemented 2026-10-01** (local guardrail deleted, docs
reverted, original spec marked superseded; cloud guardrail unverifiable —
REST route still 503s — check Manage → Policies → Guardrails in the cloud
UI and delete `reviewer-pack-human-review` if present).
Supersedes the rollout plan in
specs/human_review_guardrail_spec.md (which stays on disk as the verified
re-creation recipe).

## 0. Why

The guardrail works mechanically — verified end-to-end on the local OE
2026-10-01 (suspend → approve → resume → complete). But as a *live session
beat* it fights the presenter:

1. **Held content is invisible.** The local OE strips
   `suspend_context.pending_llm_content` from every HTTP response; the
   reviewer can only see what they're approving by querying Atlas
   directly (Compass). "Review what you approve" is the whole point of the
   beat, and the API doesn't support it.
2. **No completion signal.** `/resume` returns `{"status":"resuming"}`
   and pushes nothing; the final answer must be polled out of
   `GET /execution/:id`. On stage this reads as "it hung".
3. **Phantom second suspend.** Right after approve, the OE re-evaluates
   the next model output and logs a second "stored pending content"
   before auto-releasing — confuses the presenter into approving twice.
4. **Narrative redundancy.** The solution already carries the trust story
   structurally (no approve/post/close tool; `remember_fact` refuses
   approval-shaped content). The guardrail adds a second layer that costs
   setup fragility (regex validator quirks, 503-ing cloud route, Compass
   fallback) without adding on-stage clarity.

Decision: remove the guardrail; keep the structural boundary; make the
human's *approval* an explicit, out-of-band walkthrough beat instead.

## 1. What to remove

1. **Local OE guardrail** (id `6abdf5cbce2f3eee3ca673f7`):
   ```bash
   OE=$(docker port accrual-variance-review-oe-1 8000/tcp | cut -d' ' -f3)
   curl -X DELETE "http://$OE/guardrails/6abdf5cbce2f3eee3ca673f7?org_id=000000000000000000000001&project_id=1a0820f62c66229319b13a37"
   ```
2. **Cloud guardrail** `reviewer-pack-human-review`, if it was created in
   the Platform UI (Manage → Policies → Guardrails → Delete).
3. **Docs added for the guardrail** — revert:
   - `docs/presenter_runbook.md`: the guardrail setup note and step 6 of §1.
   - `docs/slides.md`: the "Platform-enforced human review" bullet.
   - `docs/usecase.md`: the "second, complementary layer" paragraph.
4. **Specs:** mark `human_review_guardrail_spec.md` status
   **superseded 2026-10-01 — guardrail removed, see guardrail_removal_spec.md**.
   Do not delete it: §2's verified JSON + §5's behavior notes are the
   re-enable recipe if the platform's review surface matures.

## 2. What replaces it (the approval beat)

The human decision was always out-of-band by design (`usecase.md` §5:
"the reviewer pack in the UI"). Make it a first-class walkthrough beat instead
of an implicit one — see `docs/presenter_runbook.md` §4c:

- Presenter, as the human reviewer, tells the agent the findings are
  approved.
- The agent must **refuse to record it** (no approval tool; memory never
  stores approvals) and restate that approval is a human action.
- Presenter records the decision themselves in Compass:
  `db.reviewer_packs.updateOne({_id:"pack-run-…"},
  {$set:{human_review_status:"approved"}})` — "the agent proposed, the
  human disposed, and only the human could dispose."

## 3. What stays untouched

- No `src/` changes (same as the original spec — the structural boundary
  is the product, not a gap).
- `agent_runs` → `human_decision_required` terminal state; pack's
  `human_review_status: "pending"` until the human updates it — that
  pending-until-human-acts behavior *is* the solution.

## 4. Re-enabling later

If the cloud review queue ships with visible held content + push/stream
on resume, re-apply `human_review_guardrail_spec.md` §2 verbatim
(patterns already UI-safe). The open items in its §5 (cloud review
surface, RBAC, deny semantics) still gate that.
