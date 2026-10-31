"""LangChain 1.x: middleware around the payment tool.

    agent = create_agent(model, tools=[checkout], middleware=[
        CheckoutGuard(guard, cart=lambda args: args["items"])])
"""

from __future__ import annotations

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..guard import Guard


class CheckoutGuard(AgentMiddleware):
    def __init__(self, guard: Guard, cart: Callable[[dict], list[dict]], tool: str = "checkout"):
        super().__init__()
        self.guard, self.cart, self.tool = guard, cart, tool

    def _not_paid(self, request, blocked: str) -> ToolMessage:
        return ToolMessage(content=blocked, tool_call_id=request.tool_call["id"],
                           name=self.tool, status="error")

    def wrap_tool_call(self, request, handler):
        if request.tool_call["name"] != self.tool:
            return handler(request)
        blocked = self.guard.gate(self.cart(request.tool_call["args"]))
        return self._not_paid(request, blocked) if blocked else handler(request)

    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] != self.tool:
            return await handler(request)
        blocked = await self.guard.agate(self.cart(request.tool_call["args"]))
        return self._not_paid(request, blocked) if blocked else await handler(request)
