"""OpenAI Agents SDK: a check on the payment tool's input.

    @function_tool(tool_input_guardrails=[
        checkout_guardrail(guard, cart=lambda args: args["items"])])
    def checkout(items: list[Item]) -> str: ...
"""

from __future__ import annotations

import json
from collections.abc import Callable

from agents.tool_guardrails import ToolGuardrailFunctionOutput, tool_input_guardrail

from ..guard import Guard


def checkout_guardrail(guard: Guard, cart: Callable[[dict], list[dict]]):
    @tool_input_guardrail(name="asasked_guard")
    async def asasked_guard(data):
        blocked = await guard.agate(cart(json.loads(data.context.tool_arguments or "{}")))
        if blocked is None:
            return ToolGuardrailFunctionOutput.allow()
        return ToolGuardrailFunctionOutput.reject_content(blocked)

    return asasked_guard
