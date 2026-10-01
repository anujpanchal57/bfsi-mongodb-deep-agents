# Spec: Bedrock-provided LLMs for the solution agent

Status: **implemented 2026-09-29; live-verified 2026-09-30** — agent answers
end-to-end via Bedrock Converse under `agentengine dev up` with egress
enforced (§5 risk 3 cleared). Full walkthrough smoke (`make smoke`) still
pending seed. Scope: swap the agent's chat LLM from OpenAI/Anthropic
direct APIs to AWS Bedrock, in the target region (`us-east-1`). Verified
2026-09-29: `langchain-aws` 1.7.9 is already installed/locked (pulled by
`langchain-mongodb-deepagents-vfs[bedrock]`); `ChatBedrockConverse` exposes
`model_id`, `region_name`, `temperature`, `max_tokens`, and explicit
credential fields.

## 1. Why

- **One credential chain for everything AWS:** embeddings already use Bedrock
  Titan v2 via the boto3 chain. Moving the chat LLM to Bedrock means the solution
  needs no third-party LLM API key at all — one IAM principal, one audit
  trail, one egress endpoint.
- **BFSI narrative:** data stays in-region (`us-east-1`) inside the solution's
  own AWS account; no prompt content leaves for a third-party SaaS endpoint.
  Stronger story for the room than "we put an OpenAI key in a secret store".
- **Fewer secrets:** `LLM_API_KEY` disappears from the required set.

## 2. Current state

| Piece | Today |
| --- | --- |
| `src/demo_agent/llm.py` | `LLM_PROVIDER=openai|anthropic` → `ChatOpenAI`/`ChatAnthropic`; hard-fails without `LLM_API_KEY` |
| Egress (`agent.yaml`) | `bedrock-runtime.us-east-1.amazonaws.com:443` already allowed (for embeddings); `api.openai.com:443` for the LLM |
| Secrets | `LLM_API_KEY` in `.env` / `agentengine secret set LLM_API_KEY` |
| Embeddings | Bedrock `amazon.titan-embed-text-v2:0` via boto3 chain (unchanged) |
| Platform contract | `app.deep_agent(llm=build_llm(), ...)` — any LangChain `BaseChatModel`; the SDK wraps it in `SecureWrappedLLM` internally. **Do not** wrap with `app.llm()` (double-registration fails startup) |

## 3. Changes

### 3.1 `src/demo_agent/llm.py` — add a `bedrock` provider branch

```python
if provider == "bedrock":
    from langchain_aws import ChatBedrockConverse
    return ChatBedrockConverse(
        model=os.environ.get(
            "LLM_MODEL",
            "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        temperature=temperature,
        # credentials: boto3 default chain (AWS_ACCESS_KEY_ID /
        # AWS_SECRET_ACCESS_KEY [/ AWS_SESSION_TOKEN], or profile/role)
    )
```

- Use `ChatBedrockConverse` (Converse API), not legacy `ChatBedrock` —
  streaming + tool-use are first-class there, which deepagents'
  tool-calling loop needs.
- Only require `LLM_API_KEY` when `LLM_PROVIDER` is `openai`/`anthropic`;
  for `bedrock` fail fast instead on missing AWS credentials
  (`boto3.Session().get_credentials() is None` → clear error naming the
  three env vars).
- Keep `openai`/`anthropic` branches as documented fallbacks (conference
  contingency if Bedrock is throttled — README's backup table already
  narrates this).

### 3.2 Defaults

- `LLM_PROVIDER` default flips to `bedrock` in `src/config.py`,
  `.env.example`, and anywhere else it is named (`pyproject` untouched).
- Default model: Claude Sonnet 4.5 via the **cross-region inference
  profile** (`us.` prefix — required for Claude Sonnet 4.5; on-demand direct
  model IDs for Anthropic models are not invocable there). Confirm the exact
  profile ID in the arget account and pin it in `.env.example`.
  Fallback choice if Anthropic access isn't granted in the account:
  `us.amazon.nova-pro-v1:0`.

### 3.3 `agent.yaml` egress

- Keep `bedrock-runtime.us-east-1.amazonaws.com:443` (now serves both
  embeddings and the LLM).
- **Remove `api.openai.com`** — with Bedrock as the provider it is dead
  surface in a `deny_all`-default posture. (If the OpenAI fallback must stay
  deployable, comment the line out with a one-line note instead of
  deleting.)
- No other manifest changes: `sandboxes.agent.secrets: ["*"]` already covers
  the AWS credential env vars.

### 3.4 Secrets and `.env`

- `.env.example`: set `LLM_PROVIDER=bedrock`, `LLM_MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0`;
  add `AWS_ACCESS_KEY_ID=` / `AWS_SECRET_ACCESS_KEY=` / `# AWS_SESSION_TOKEN=`
  (local dev only if the default chain doesn't resolve); mark `LLM_API_KEY`
  "only for LLM_PROVIDER=openai|anthropic".
- Deployed: sandbox pods are Firecracker microVMs — there is no instance
  role to assume, so credentials arrive as env vars:
  `agentengine secret set AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`
  (dedicated least-privilege IAM user; see §3.5). Replace the
  `LLM_API_KEY` step in `deploy/README.md` accordingly.
  **Verify on first deploy:** if the platform injects an AWS identity into
  sandboxes, prefer that and drop the static keys.

### 3.5 IAM

One policy covers the whole solution runtime (LLM + embeddings):

- `bedrock:InvokeModel` / `bedrock:InvokeModelWithResponseStream` on the
  inference-profile ARN **and** the underlying model ARNs it routes to
  (cross-region profiles require both), plus the existing Titan embed ARN.
- Enable model access for Claude Sonnet 4.5 (or Nova Pro) in the solution
  account/region beforehand — this is a manual console step and the most
  likely day-of surprise. Add it to the pre-session checklist in
  `deploy/README.md`.

### 3.6 Docs

- README: LLM bullet → "AWS Bedrock (Claude via Converse API), same boto3
  credential chain as the Titan embeddings"; backup-table row "Bedrock
  throttled/unavailable" now covers the LLM too — fallback =
  `LLM_PROVIDER=openai` + `LLM_API_KEY`.
- `deploy/README.md`: prereq 6 gains "model access enabled for the chosen
  Bedrock model"; secrets step swaps `LLM_API_KEY` → AWS keys.

## 4. Platform-contract notes (unchanged behavior)

- LLM calls still route through the OE-audited path: `deep_agent()` wraps
  the model in `SecureWrappedLLM` itself. The Bedrock client must be passed
  **unwrapped**, exactly like today.
- The outbound HTTPS call to `bedrock-runtime` originates from the agent
  sandbox, so the egress entry (§3.3) is the only network change surface.
- Subagent (`VARIANCE_SPECIALIST`) inherits the wrapped main model — no
  per-subagent model config needed.

## 5. Test plan

- New offline unit test (`tests/test_llm.py`): `LLM_PROVIDER=bedrock` →
  `build_llm()` returns a `ChatBedrockConverse` with the expected
  `model_id`/`region_name` (construction is lazy — no AWS call, no creds
  needed); missing-creds error message names the AWS env vars; existing
  `openai`/`anthropic` branches still construct.
- `make test` stays fully offline.
- Live verification: `agentengine dev up` + `make smoke` with
  `LLM_PROVIDER=bedrock`; confirm tool-calling works end-to-end through
  `SecureWrappedLLM` (Converse API streaming is the one integration risk
  worth a pre-presentation run).

## 6. Risks / open questions

1. **Inference-profile ID drift** — exact `us.*` IDs must be confirmed in
   the arget account; treat `LLM_MODEL` as required config, not a constant.
2. **Model access not enabled** in the account/region → runtime
   `AccessDeniedException`; mitigate via the pre-session checklist (§3.5).
3. **SecureWrappedLLM × Converse streaming** — untested combination;
   §5 live check gates the solution on it.
4. **Static AWS keys in platform secrets** — acceptable here;
   least-privilege IAM user, rotate after the event.

## 7. Acceptance criteria

- `LLM_PROVIDER=bedrock` + AWS creds (no `LLM_API_KEY`) runs the full solution
  flow locally under `agentengine dev up` and deployed.
- `agent.yaml` egress allowlist contains exactly `s3.us-east-1.amazonaws.com`
  and `bedrock-runtime.us-east-1.amazonaws.com` (OpenAI entry removed or
  commented).
- `agentengine agent validate --strict` passes; `make test` passes offline.
- README/deploy docs match the new secret set (AWS keys, not LLM_API_KEY).
