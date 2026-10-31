"""Страж перед оплатой в коде агента: обёртка и крючки библиотек агентов.

Модели не вызываются: факты задаёт тест, а модель агента — заготовленный
сценарий «позвать checkout, потом ответить текстом». Сами библиотеки —
настоящие: проверяется, что оплата действительно не вызывается.
"""

import asyncio
import json

import pytest

from asasked import Guard
from asasked.coherence import IntentFacts

SHOES = {"name": "Nike Pegasus 41", "brand": "Nike", "color": "Triple Black",
         "size": "43", "price": 129.99, "returnable": True, "delivery_days": 3}


def size_guard() -> tuple[Guard, list[str]]:
    """Человек просил 42, пока не ответил, что 43 тоже подойдёт."""
    heard = []

    def extract(request):
        heard.append(request)
        return IntentFacts(color="black", size_label="43" if "43 is fine" in request else "42")

    return Guard("black running shoes, size 42", extract=extract), heard


# --- обёртка вокруг своей функции оплаты ---

def test_protect_does_not_pay_until_the_person_agrees():
    guard, heard = size_guard()
    paid = []
    pay = guard.protect(lambda items: paid.append(items) or "order 1",
                        cart=lambda items: items)

    blocked = pay([SHOES])
    assert paid == [] and blocked.startswith("NOT PAID") and "size 43" in blocked

    # агент «соглашается» сам и платит ещё раз — всё равно нет
    assert pay([SHOES]).startswith("NOT PAID") and paid == []

    guard.answer("43 is fine")
    assert pay([SHOES]) == "order 1" and paid == [[SHOES]]
    assert "The agent asked: " in heard[-1] and "The person answered: 43 is fine" in heard[-1]


def test_protect_async_checkout():
    guard, _ = size_guard()

    async def checkout(items):
        return "order 1"

    pay = guard.protect(checkout, cart=lambda items: items)
    assert asyncio.run(pay([{**SHOES, "size": "42"}])) == "order 1"
    assert asyncio.run(pay([SHOES])).startswith("NOT PAID")


def test_answer_without_a_question_is_added_to_the_request():
    guard, heard = size_guard()
    guard.answer("43 is fine")
    assert guard.gate([SHOES]) is None
    assert "(The person added: 43 is fine)" in heard[-1]


# --- Claude Agent SDK ---

def test_claude_agent_hook_denies_checkout():
    pytest.importorskip("claude_agent_sdk")
    from asasked.integrations.claude_agent import checkout_hook

    guard, _ = size_guard()
    matcher = checkout_hook(guard, cart=lambda args: args["items"], tool="mcp__shop__checkout")
    assert matcher.matcher == "mcp__shop__checkout"
    hook = matcher.hooks[0]

    def run(items):
        return asyncio.run(hook({"tool_name": "mcp__shop__checkout",
                                 "tool_input": {"items": items}}, "t1", None))

    out = run([SHOES])["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "size 43" in out["permissionDecisionReason"]
    assert run([{**SHOES, "size": "42"}]) == {}


# --- OpenAI Agents SDK: настоящий Runner, модель — сценарий ---

def test_openai_agents_guardrail_keeps_checkout_from_running():
    pytest.importorskip("agents")
    from agents import Agent, RunConfig, Runner, function_tool
    from agents.items import ModelResponse
    from agents.models.interface import Model
    from agents.usage import Usage
    from openai.types.responses import (ResponseFunctionToolCall, ResponseOutputMessage,
                                        ResponseOutputText)

    from pydantic import BaseModel

    from asasked.integrations.openai_agents import checkout_guardrail

    class Item(BaseModel):  # строгая схема OpenAI не принимает list[dict]
        name: str
        brand: str
        color: str
        size: str
        price: float
        returnable: bool
        delivery_days: int

    class Scripted(Model):
        def __init__(self, items):
            self.items, self.seen = items, []

        async def get_response(self, system_instructions, input, *args, **kwargs):
            self.seen.append(input)
            if len(self.seen) == 1:
                out = ResponseFunctionToolCall(type="function_call", call_id="c1", name="checkout",
                                               arguments=json.dumps({"items": self.items}))
            else:
                out = ResponseOutputMessage(
                    id="m1", type="message", role="assistant", status="completed",
                    content=[ResponseOutputText(type="output_text", text="done", annotations=[])])
            return ModelResponse(output=[out], usage=Usage(), response_id=None)

        def stream_response(self, *args, **kwargs):
            raise NotImplementedError

    def shop(items, guard):
        paid = []

        @function_tool(tool_input_guardrails=[checkout_guardrail(guard, cart=lambda a: a["items"])])
        def checkout(items: list[Item]) -> str:
            """Pay for the items."""
            paid.append(items)
            return "order 1"

        model = Scripted(items)
        Runner.run_sync(Agent(name="shopper", model=model, tools=[checkout]), "buy shoes",
                        run_config=RunConfig(tracing_disabled=True))
        return paid, json.dumps(model.seen[-1], default=str)

    guard, _ = size_guard()
    paid, told = shop([SHOES], guard)
    assert paid == [] and "NOT PAID" in told and "size 43" in told
    paid, _ = shop([{**SHOES, "size": "42"}], guard)
    assert len(paid) == 1


# --- LangChain: настоящий create_agent, модель — сценарий ---

def test_langchain_middleware_keeps_checkout_from_running():
    pytest.importorskip("langchain")
    from langchain.agents import create_agent
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool

    from asasked.integrations.langchain import CheckoutGuard

    class Scripted(BaseChatModel):
        items: list

        @property
        def _llm_type(self):
            return "scripted"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if any(isinstance(m, ToolMessage) for m in messages):
                msg = AIMessage(content="done")
            else:
                msg = AIMessage(content="", tool_calls=[
                    {"name": "checkout", "args": {"items": self.items}, "id": "c1"}])
            return ChatResult(generations=[ChatGeneration(message=msg)])

    def shop(items, guard, run=lambda agent, x: agent.invoke(x)):
        paid = []

        @tool
        def checkout(items: list[dict]) -> str:
            """Pay for the items."""
            paid.append(items)
            return "order 1"

        agent = create_agent(Scripted(items=items), tools=[checkout],
                             middleware=[CheckoutGuard(guard, cart=lambda a: a["items"])])
        result = run(agent, {"messages": [{"role": "user", "content": "buy shoes"}]})
        told = [m.content for m in result["messages"] if isinstance(m, ToolMessage)]
        return paid, told

    guard, _ = size_guard()
    paid, told = shop([SHOES], guard)
    assert paid == [] and told[0].startswith("NOT PAID") and "size 43" in told[0]
    paid, told = shop([{**SHOES, "size": "42"}], guard)
    assert len(paid) == 1 and told == ["order 1"]
    # асинхронный агент идёт через awrap_tool_call
    paid, told = shop([SHOES], guard, run=lambda agent, x: asyncio.run(agent.ainvoke(x)))
    assert paid == [] and told[0].startswith("NOT PAID")
