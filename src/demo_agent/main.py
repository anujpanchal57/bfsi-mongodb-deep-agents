"""Atlas Agent Engine entrypoint: accrual-variance-review.

The deployed runtime imports this module (agent.yaml: entrypoint
src.demo_agent.main:app) and builds the graph via the @app.entrypoint
factory:

- deepagents orchestrator with the variance specialist as a subagent
  (dispatch via the built-in task() tool)
- MongoFilesystemBackend: grep/glob/ls -> Atlas $rankFusion hybrid search,
  read/write -> S3 (source of truth); embeddings via the package default
  (Bedrock titan-embed-text-v2:0, boto3 credential chain)
- durable sessions via the platform MongoDB checkpointer
- business state (runs, handoffs, packs) via @app.tool() tools

Note: the public docs (Build a Deep Agent) state that App.deep_agent()
rejects a custom `backend`; the SDK as shipped (agent-engine-sdk-langgraph
0.11.6) accepts it with a bypass-the-audit warning, which this demo accepts
deliberately (VFS I/O is covered by our own tool logging). If a future SDK
enforces rejection, fall back to exposing the VFS via @app.tool() wrappers
and drop the backend kwarg.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from agent_engine_sdk_langgraph import App

from src.demo_agent.backend import create_backend
from src.demo_agent.llm import build_llm
from src.demo_agent.prompts import ORCHESTRATOR_PROMPT
from src.demo_agent.subagents import VARIANCE_SPECIALIST
from src.demo_agent.tools import register

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

app = App(app_name="accrual-variance-review")

register(app)


@app.entrypoint
def build_agent():
    """Build the deep agent graph.

    NOTE: the TOOL sandbox also executes this entrypoint once (lazily, on the
    first invoke_llm call) just to discover app.llm()/deep_agent LLM
    registrations — and its egress policy is deny_all. Constructing
    MongoFilesystemBackend there fails on S3/Atlas network I/O and takes down
    LLM routing ("llm_id '__default__' is not registered"). The graph built in
    the tool sandbox is discarded, so skip the real backend there.
    """
    in_tool_sandbox = os.environ.get("RUNNER_MODE") == "tool"
    logger.info("Building accrual-variance-review deep agent (tool_sandbox=%s)",
                in_tool_sandbox)
    return app.deep_agent(
        # Do NOT wrap with app.llm() — deep_agent wraps internally
        # (SecureWrappedLLM); double-wrapping fails startup.
        llm=build_llm(),
        tools=app.get_tools(),  # OE-audited wrappers; deep_agent does NOT auto-merge
        subagents=[VARIANCE_SPECIALIST],
        system_prompt=ORCHESTRATOR_PROMPT,
        backend=None if in_tool_sandbox else create_backend(),
        # checkpointer: _UNSET default -> app.checkpointer() (MongoDB)
    )


# Contract: app.run() is called at module bottom, unconditionally — the
# sandbox imports this module and run() is mode-aware (no-op outside AER).
app.run()
