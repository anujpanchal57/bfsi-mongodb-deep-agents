"""Atlas Agent Engine entrypoint: accrual-variance-review.

The deployed runtime loads `app` (agent.yaml: entrypoint src.demo_agent.main:app)
and builds the graph via the @app.entrypoint factory:

- deepagents orchestrator with the variance specialist as a subagent
  (dispatch via the built-in task() tool)
- MongoFilesystemBackend: grep/glob/ls -> Atlas $rankFusion hybrid search,
  read/write -> S3 (source of truth); embeddings via the package default
  (Bedrock titan-embed-text-v2:0, boto3 credential chain)
- durable sessions via the platform MongoDB checkpointer
- business state (runs, handoffs, packs) via @app.tool() tools
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from src.demo_agent.backend import SDK_HINT, create_backend
from src.demo_agent.llm import build_llm
from src.demo_agent.prompts import ORCHESTRATOR_PROMPT
from src.demo_agent.subagents import VARIANCE_SPECIALIST
from src.demo_agent.tools import register

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

try:
    from agent_engine_sdk_langgraph import App
except ImportError as exc:  # placeholder wheel / SDK not installed
    raise RuntimeError(SDK_HINT) from exc

app = App(app_name="accrual-variance-review")

register(app)


@app.entrypoint
def build_agent():
    """Build the deep agent graph for the AER."""
    logger.info("Building accrual-variance-review deep agent")
    return app.deep_agent(
        llm=build_llm(),
        tools=app.get_tool_schemas(),  # deep_agent does NOT auto-merge
        subagents=[VARIANCE_SPECIALIST],
        system_prompt=ORCHESTRATOR_PROMPT,
        backend=create_backend(),
        # checkpointer: _UNSET default -> app.checkpointer() (MongoDB)
    )


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
