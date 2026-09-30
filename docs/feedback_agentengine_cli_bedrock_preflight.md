# Feedback: `agentengine dev up` `.env` preflight rejects Bedrock-based agents

**Date:** 2026-09-30
**CLI:** `agentengine` 0.1.115 (git `b8302e3`), macOS arm64
**Severity:** Medium — blocking error, workaround exists
**Area:** CLI / local development (`agentengine dev up` hot-reload artifact generation)

## Summary

`agentengine dev up` refuses to start the local stack unless the agent's
`.env` file contains one of a hardcoded list of LLM API-key variables:

```none
Error: generating hot-reload artifacts: .env is missing required variables:
one of OPENAI_API_KEY, ANTHROPIC_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY, LLM_API_KEY
```

This check assumes every agent authenticates to its LLM provider with a
static API key. Agents that use **AWS Bedrock** — where authentication rides
the boto3 credential chain (IAM roles, SSO, `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`) and no LLM API key exists at
all — cannot pass the preflight without adding a dummy variable.

## Reproduction

1. Configure an agent to use Bedrock via `langchain-aws`
   `ChatBedrockConverse` (no `*_API_KEY` variable anywhere):

   ```python
   # src/demo_agent/llm.py
   from langchain_aws import ChatBedrockConverse

   def build_llm():
       return ChatBedrockConverse(
           model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
           region_name="us-east-1",
       )
   ```

   ```none
   # .env
   MONGODB_URI=mongodb+srv://...
   LLM_PROVIDER=bedrock
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   ```

2. Run `agentengine dev up`.

3. The command fails before building anything, with the error above.

## Why this matters

- **The docs promise provider freedom.** The Agent Contract Reference states
  "You can use any LLM provider with your agent... construct a LangChain
  `BaseChatModel` for the provider and pass it to the `app.llm()` method."
  Bedrock is a standard LangChain provider and a common enterprise choice —
  the preflight contradicts the documented contract.
- **Bedrock is the natural fit for your own demo shape.** Our reference
  architecture (S3 + Atlas + Bedrock embeddings via
  `langchain-mongodb-deepagents-vfs`) already authenticates to Bedrock for
  embeddings through the boto3 chain. Forcing a foreign API key into `.env`
  for the chat model breaks the "one credential chain" story.
- **Static-key-only thinking is at odds with the target audience.** BFSI and
  other regulated users often *cannot* put third-party LLM API keys in env
  files; IAM-mediated Bedrock access is precisely how they get approved.
- **The workaround is a loaded footgun.** A placeholder
  `LLM_API_KEY=unused-...` is mounted into the container like any real
  secret, can mask genuine misconfiguration (a real Bedrock failure now
  competes with "wait, which key is it using?"), and will confuse every
  future reader of the repo.

## Expected behavior

Any of:

1. Add Bedrock to the CLI's recognized provider set and validate AWS
   credentials instead of an API key (e.g. accept `AWS_ACCESS_KEY_ID`, or
   `AWS_PROFILE`, or skip the check when `AWS_REGION`/Bedrock config is
   present).
2. Only enforce the API-key check for providers that need one — the CLI
   already scaffolds a `custom` ("configure in code") option in
   `agentengine create`; honor that signal, or an `agent.yaml` field, at
   preflight time.
3. Provide an explicit opt-out flag (e.g. `agentengine dev up
   --no-llm-preflight`) with a warning instead of a hard error.
4. At minimum, downgrade the error to a warning: "no LLM API key found —
   ensure your agent configures its provider in code."

## Workaround in use

A commented placeholder in `.env` satisfies the presence check; the agent
code never reads it when the provider is Bedrock:

```none
# Placeholder ONLY to satisfy the agentengine CLI .env preflight...
LLM_API_KEY=unused-bedrock-uses-boto3-chain
```

The stack then starts normally and Bedrock calls work through the boto3
credential chain.

## Additional notes

- The same assumption likely surfaces in the deploy path
  (`agentengine deploy`) and in `agentengine create`'s provider catalog
  (OpenAI / Anthropic / Gemini / OpenRouter / *-compatible / custom) —
  Bedrock appears only indirectly via "Anthropic-compatible" base-URL
  gateways, not as a native boto3-backed option.
- Happy to share the full CLI session log referenced in the error output if
  useful.

## Related gotcha found while debugging (worth documenting prominently)

The documented lifecycle says the **tool sandbox lazily executes the agent
entrypoint once** to discover `app.llm()` registrations. What is easy to
miss: any network I/O performed during graph construction (e.g. our
workspace backend verifying its S3 bucket with `head_bucket`) runs under the
**tool sandbox's egress policy** (`deny_all` by default), not the agent
sandbox's. The failure surfaces several layers away as:

```none
LLM invocation error: llm_id '__default__' is not registered because the
agent entrypoint failed when the LLM registry was loaded.
```

which reads like an LLM configuration problem but is actually an egress 403
in the tool sandbox. Our fix was to skip backend construction when
`RUNNER_MODE=tool` (the graph built there is discarded anyway). Suggestions:
(a) call this out in the "Execution Lifecycle" docs with exactly this
failure mode; (b) consider having the tool sandbox inherit the agent
sandbox's egress destinations, or (c) make the error name the offending
host — the CONNECT target is known to the proxy and would have saved an hour
of tracing.

One more egress-model surprise in the same debugging session: with
`features.deep_agent`, LLM calls execute **from the tool sandbox**
(`invoke_llm`), so the LLM provider's FQDN must be allowlisted under
`sandboxes.tool.network.egress` — listing it only on the agent sandbox
yields `LLM invocation error: Failed to connect to proxy URL ...` even
though the model is declared in agent-side code. The network-egress docs
cover per-sandbox egress for tools but do not call out that the LLM itself
egresses from the tool sandbox.

Similarly, the local egress proxy's 403 responses do not name the denied
FQDN anywhere in the agent logs; a `agentengine egress`-style "denied:
host" log line (or a `dev logs egress` view) would make allowlist iteration
much faster. Three additions to our allowlist were discovered one 403 at a
time (S3 virtual-hosted `*.s3.<region>.amazonaws.com`, the legacy global
`s3.amazonaws.com` endpoint botocore still uses for us-east-1, and
tiktoken's `openaipublic.blob.core.windows.net` encoding blob).
