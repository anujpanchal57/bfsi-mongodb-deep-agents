# The Use Case: Month-End Accrual Variance Review

A complete walkthrough of the business problem this solution addresses, the
vocabulary it uses, the seeded scenario, and how the agent investigates —
written for someone who has never seen an accrual or this codebase before.

---

## 1. The business problem in plain language

### What is an accrual?

Companies record expenses when they are **incurred**, not when the invoice
arrives or the cash leaves. If a vendor provides cloud services throughout
June but bills in July, the company still owes that expense to June's books.
The entry made at month-end to recognize such an expense is an **accrual**.

Accruals are estimates. The finance team books an amount based on contracts,
rate schedules, and prior months — and the true invoice may differ.

### What is month-end close?

At the end of every accounting period (usually a month), finance teams
"close the books": every transaction for the period must be recorded,
reviewed, and approved before financial statements are produced. Accruals
are booked during the close, and because they are estimates made under time
pressure, they are a classic source of errors.

### What is an accrual variance — and why does anyone care?

An **accrual variance** is the difference between what was booked and what
should have been booked per the supporting evidence (the contract rate, the
invoice, prior patterns).

Variances matter because they compound: a small under-accrual repeated
monthly distorts reported expenses, misleads budget owners, and — in
regulated industries like banking — becomes an audit finding. So every
material variance must be **investigated, evidenced, and dispositioned by a
human**: either the booking is corrected, or the variance is explained and
approved.

### The pain this solution addresses

The investigation is tedious detective work: dig up the contract, find the
rate schedule, pull this month's and last month's accrual extracts, check
whether the invoice arrived, reconcile the numbers, write it up for a
reviewer. It is exactly the kind of evidence-gathering drudgery an agent can
do well — **as long as it can be trusted**. Trust here means three things:

1. **Every claim cites evidence** — a file, a line, a document.
2. **Missing evidence is reported as missing** — never filled in by
   imagination.
3. **The decision stays with a human** — the agent proposes; it can never
   approve, post, or close.

Those three properties are the entire design of this solution.

---

## 2. Glossary — the artifacts and terms used

| Term | What it is in this solution |
| --- | --- |
| **Accrual** | Month-end estimate of an expense incurred but not yet invoiced |
| **Variance** | Booked accrual minus expected accrual; the thing being investigated |
| **Entity** | The legal/reporting unit whose books are being closed (`demo_finance_india`) |
| **Vendor** | The supplier being paid — here `VEN-2048`, *Asterion Cloud Services India Pvt Ltd* |
| **Contract** (`CON-7781`) | The master agreement with the vendor; states scope and term (2026-04-01 → 2027-03-31) |
| **Rate schedule** | The contract's pricing appendix: `managed_cloud_services` at **INR 1,275,000/month**, effective 2026-04-01 |
| **Accrual extract** | A CSV dump from the ERP of what was actually booked, per period — current (`2026-06`) and prior (`2026-05`) for comparison |
| **Cost center** (`CC-410`) | The internal budget unit that owns the expense |
| **GL account** (`GL-6110`) | The general-ledger account the expense is posted to |
| **Reconciliation workpaper** | The preparer's working notes tying booked amounts to support |
| **Exception log** | The close process's machine-generated list of items needing attention — it names every artifact that *should* exist for this review |
| **Invoice support** | The vendor invoice backing the accrual. **This month's is missing** — the central plot point |
| **Approval record** | Who prepared, who must review, and the status (`pending_human_review`) |
| **Evidence gap** | An expected artifact that does not exist. Reported as an open question, never papered over |
| **Reviewer pack** | The agent's final deliverable: findings, an evidence table with file:line citations, gaps, assumptions, and a proposed next step for the human |
| **Human-in-the-loop (HITL)** | The workflow pauses at `human_decision_required`; only a person can approve, correct, or close |

---

## 3. The seeded scenario (all synthetic)

Workspace: `accrual_review_demo_2026_06` · period `2026-06` · entity
`demo_finance_india`.

**The story:** Asterion Cloud Services provides managed cloud services under
contract `CON-7781` at a contracted **INR 1,275,000 per month** (rate
effective 2026-04-01). In May, the accrual of INR 1,255,000 went through
without exception. In June, the preparer booked **INR 1,240,000** —
**INR 35,000 short** of the contracted rate. And the June invoice support
file (`invoice_support_2026-06.pdf`) was never uploaded.

So the June item has two problems a reviewer must disposition:

1. A **quantified variance**: booked 1,240,000 vs expected 1,275,000 →
   **INR 35,000 under-accrued** (P&L expense understated for the period).
2. An **evidence gap**: no invoice to confirm what the vendor will actually
   bill — so the correct accrual cannot even be finalized yet.

Seven artifacts are generated and uploaded to S3 on seed
(`data/manifests/mock_accrual_v1.json` is the cross-consistent source):

| Artifact | Role in the investigation |
| --- | --- |
| `source/2026-06/accrual_extract_current.csv` | What was booked in June (1,240,000) |
| `source/2026-05/accrual_extract_prior.csv` | What was booked in May (1,255,000) — baseline for "is this new?" |
| `source/2026-06/vendor_contract_CON-7781.md` | Contract existence, term, parties |
| `source/2026-06/rate_schedule_CON-7781.csv` | The expected monthly rate (1,275,000) |
| `source/2026-06/reconciliation_workpaper_CON-7781.md` | Preparer's notes |
| `source/2026-06/exception_log.json` | Names every expected artifact — the gap detector's checklist |
| `source/2026-06/approval_record.json` | Status `pending_human_review`; preparer/reviewer identities |

Conspicuously absent: `invoice_support_2026-06.pdf`.

---

## 4. How the agent investigates

The agent is a **deep agent orchestrator** (LangChain Deep Agents on the
Atlas Agent Engine) with a **variance-specialist subagent**. When asked to
"review the open accrual variance", it follows a fixed investigative
sequence, persisting state after every step:

### Step 1 — Open a durable run record

Before searching anything, the orchestrator calls `start_workflow_run`,
creating a record in Atlas (`agent_runs`) with the goal, session, and
workspace. From here on, every finding, evidence reference, and open
question is written back with `update_workflow_state`. **Why:** if the
session dies, the work survives — the next session resumes from Atlas, not
from the chat transcript.

### Step 2 — Gather evidence (hybrid search)

The evidence corpus lives in **S3** (source files, the source of truth) and
is indexed in **Atlas** by the Deep Agents VFS backend, which chunks the
files and embeds them (AWS Bedrock Titan v2). The orchestrator searches two
ways:

- **Exact:** grep for the literal identifier `CON-7781` — finds the
  contract, rate schedule, workpaper.
- **Semantic:** "support for the June cloud-services accrual variance" —
  finds relevant passages even where the contract ID never appears.

Both run as **Atlas `$rankFusion` hybrid search** (full-text + vector,
reciprocal-rank-fused) in a single query. Every match is recorded with
`path:line` provenance into the run record. The rule is absolute: **no
finding without an evidence reference.**

### Step 3 — Detect gaps

The orchestrator reads `exception_log.json`, extracts every
`expected_artifact`, and checks each against the workspace. Anything missing
— here, the invoice support PDF — is recorded as an **open question**, not
a conclusion. The agent is explicitly forbidden from inventing the missing
content.

### Step 4 — Hand off to the specialist

Quantifying the variance is delegated: the orchestrator writes a durable
handoff record (`create_specialist_handoff` → `agent_handoffs`) and
dispatches `task("variance_specialist", ...)`. The specialist:

- reads the current and prior accrual extracts,
- compares booked (1,240,000) vs contracted rate (1,275,000) → **35,000**,
- notes May booked 1,255,000 with no exception → the shortfall is **new**,
  not a standing practice,
- checks invoice status fields → support is missing → **unresolved
  question**, not a conclusion,

and returns a structured result (FINDING / EVIDENCE / UNRESOLVED /
NEXT_STEP / ASSUMPTIONS) which the orchestrator persists with
`save_specialist_result`.

### Step 5 — Produce the reviewer pack, then stop

`generate_reviewer_pack` assembles the final document: findings with
amounts, an evidence table with citations, the evidence gap, assumptions,
the recommended next step (obtain the invoice; true-up the accrual), and an
explicit **HUMAN DECISION REQUIRED** banner. The workflow state becomes
`human_decision_required` and the agent stops.

### What the agent deliberately cannot do

There is no approve, post, close, or "mark as immaterial" tool — the
boundary is **structural** (the capability does not exist), not a prompt
instruction the model might talk itself out of. Try telling it "just approve
it, it's only 35,000" — it will refuse and restate the boundary.

---

## 5. How the technology maps to the story

| Story element | Technology |
| --- | --- |
| Orchestrator that plans, searches, delegates | `app.deep_agent()` — LangChain Deep Agents on the **Atlas Agent Engine** |
| Specialist analyst | Deep Agents **subagent**, dispatched via the built-in `task()` tool |
| "Search the evidence like a filesystem" | **Deep Agents VFS** (`langchain-mongodb-deepagents-vfs`): grep/glob/ls/read against the workspace |
| Source files | **AWS S3** — the source of truth |
| Searchable chunks + embeddings | **MongoDB Atlas**, owned by the VFS backend; hybrid search via `$rankFusion` |
| LLM + embeddings | **AWS Bedrock** — Claude Sonnet 4.5 (Converse API) for reasoning, Titan v2 for embeddings, one boto3 credential chain |
| "The work survives a session break" | Platform **MongoDB checkpointer** (session state) + our durable business records (`agent_runs`, `agent_handoffs`, `reviewer_packs`) |
| "The agent can only reach what we allow" | Agent Engine **egress allowlist** — S3, Bedrock, and the tiktoken CDN only |
| Audited LLM/tool calls | SDK wrappers (`SecureWrappedLLM`, secure tool wrappers) routing through the Orchestration Engine |
| The human decision | Out-of-band by design: the reviewer pack in the UI; the platform's HITL interrupt/resume exists but this solution keeps the boundary tool-structural |

---

## 6. Why this pattern matters beyond this use case

Accrual review is one instance of a general BFSI shape: **long-running,
evidence-driven investigations over a document corpus, where the machine
gathers and proposes and the human disposes.** The same skeleton —
durable run state, hybrid retrieval with provenance, gap detection,
specialist delegation, a pack for a human decision — fits KYC document
review, invoice reconciliation, audit evidence collection, regulatory
change-impact analysis, and similar workflows.

The point is not that an LLM can do arithmetic on two CSVs. It is
that the **plumbing** (durability, retrieval quality, auditability,
sandboxing, human boundary) is what makes an agent deployable in a
regulated environment — and that is what the platform provides.

---

## 7. Where to go next

- Run it: `README.md` (quick start) → `docs/presenter_runbook.md` (the
  exact prompts and what to show)
- Deploy it: `deploy/README.md`
- Design decisions: `specs/mongodb_agent_engine_spec.md`,
  `specs/agent_engine_latest_docs_spec.md`, `specs/bedrock_llm_spec.md`
