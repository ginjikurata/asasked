"""Страж как MCP-сервер: настоящий протокол, клиент в том же процессе, без моделей."""

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp import Client

from asasked import mcp_server
from asasked.coherence import IntentFacts

SHOES = {"name": "Nike Pegasus 41", "brand": "Nike", "color": "Triple Black",
         "size": "43", "price": 129.99, "returnable": True, "delivery_days": 3}


@pytest.fixture
def heard(monkeypatch):
    """Извлечение без модели: размер 42, пока человек не согласился на 43."""
    calls = []

    def extract(request):
        calls.append(request)
        return IntentFacts(color="black", size_label="43" if "43 is fine" in request else "42")

    monkeypatch.setattr(mcp_server, "EXTRACT", extract)
    monkeypatch.setattr(mcp_server, "_guards", type(mcp_server._guards)())
    return calls


def call(*steps):
    async def run():
        async with Client(mcp_server.server) as client:
            return [await client.call_tool("check_order", args) for args in steps]
    return asyncio.run(run())


def test_lists_one_tool_with_instructions():
    async def run():
        async with Client(mcp_server.server) as client:
            return await client.list_tools()
    tools = asyncio.run(run()).tools
    assert [t.name for t in tools] == ["check_order"]
    assert "name" in tools[0].input_schema["$defs"]["CartItem"]["required"]
    assert "do NOT pay" in mcp_server.INSTRUCTIONS


def test_ask_then_the_answer_lets_it_through(heard):
    first, second = call(
        {"request": "black shoes, size 42", "cart": [SHOES]},
        {"request": "black shoes, size 42", "cart": [SHOES],
         "answers": [{"question": "The shoes are size 43. Go ahead?", "answer": "43 is fine"}]},
    )
    assert first.structured_content["decision"] == "ask"
    assert "size 43" in first.structured_content["question"]
    assert second.structured_content["decision"] == "proceed"
    assert "The person answered: 43 is fine" in heard[-1]


def test_same_request_is_extracted_once(heard):
    fixed = {**SHOES, "size": "42"}
    first, second = call({"request": "black shoes, size 42", "cart": [SHOES]},
                         {"request": "black shoes, size 42", "cart": [fixed]})
    assert [first.structured_content["decision"], second.structured_content["decision"]] == ["ask", "proceed"]
    assert len(heard) == 1


def test_item_without_name_is_an_error(heard):
    (result,) = call({"request": "black shoes", "cart": [{"brand": "Nike"}]})
    assert result.is_error
