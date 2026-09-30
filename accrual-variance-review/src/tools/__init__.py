import json
import logging
import time
from dataclasses import dataclass
from functools import wraps

logger = logging.getLogger("agent_tools")


@dataclass
class ToolContext:
    """Dependencies injected into every tool. Narrow scope: no raw collection
    access is ever handed to the model."""
    repo: object
    s3: object
    settings: object


def tool(fn):
    """Structured logging + user-safe errors. Never logs document contents."""
    @wraps(fn)
    def wrapper(ctx: ToolContext, *args, **kwargs):
        start = time.time()
        workspace_id = kwargs.get("workspace_id") or (args[0] if args else None)
        run_id = kwargs.get("run_id")
        try:
            result = fn(ctx, *args, **kwargs)
            logger.info(json.dumps({
                "event": "tool_call", "tool": fn.__name__,
                "workspace_id": workspace_id, "run_id": run_id,
                "latency_ms": int((time.time() - start) * 1000),
                "outcome": "ok",
            }))
            return result
        except ToolError as exc:
            logger.warning(json.dumps({
                "event": "tool_call", "tool": fn.__name__,
                "workspace_id": workspace_id, "run_id": run_id,
                "latency_ms": int((time.time() - start) * 1000),
                "outcome": "error", "code": exc.code,
            }))
            return {"error": {"code": exc.code, "message": exc.message}}
        except Exception:
            logger.exception(json.dumps({
                "event": "tool_call", "tool": fn.__name__,
                "workspace_id": workspace_id, "run_id": run_id,
                "outcome": "error",
            }))
            return {"error": {"code": "internal",
                              "message": "Tool failed; see logs for details."}}
    return wrapper


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def require_workspace(ctx: ToolContext, workspace_id: str) -> dict:
    ws = ctx.repo.get("workspaces", workspace_id)
    if not ws:
        raise ToolError("workspace_not_found",
                        f"Workspace '{workspace_id}' does not exist.")
    return ws
