"""Claude Agent SDK: крючок PreToolUse перед инструментом оплаты.

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
    """tool — имя инструмента оплаты так, как его видит агент."""

    async def asasked_guard(input_data, tool_use_id, context):
        blocked = await guard.agate(cart(input_data["tool_input"]))
        if blocked is None:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": blocked}}

    return HookMatcher(matcher=tool, hooks=[asasked_guard])
