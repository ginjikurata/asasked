"""Claude Agent SDK: a PreToolUse hook in front of the payment tool.

    options = ClaudeAgentOptions(..., hooks={"PreToolUse": [
        checkout_hook(guard, cart=lambda args: args["items"],
                      tool="mcp__shop__checkout")]})
"""

from __future__ import annotations

from collections.abc import Callable

from claude_agent_sdk import HookMatcher

from ..guard import Guard


def checkout_hook(guard: Guard, cart: Callable[[dict], list[dict]],
                  tool: str = "checkout") -> HookMatcher:
    """tool is the payment tool's name as the agent sees it."""

    async def asasked_guard(input_data, tool_use_id, context):
        blocked = await guard.agate(cart(input_data["tool_input"]))
        if blocked is None:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": blocked}}

    return HookMatcher(matcher=tool, hooks=[asasked_guard])
