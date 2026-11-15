"""The guard as an MCP server: the real protocol, a client in the same process, no models."""

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
    """Extraction with no model: size 42, until the person agreed to 43."""
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


def test_asasked_payees_pins_the_shops_address(heard, monkeypatch):
    shop, thief = ("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
                   "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")
    cart = [{**SHOES, "size": "42"}]
    forged = {"token": "USDC", "network": "solana", "amount": 129.99, "to": thief,
              "merchant": thief, "rate": 1.0}
    monkeypatch.setenv("ASASKED_PAYEES", f" {shop} , ")
    refused, paid = call(
        {"request": "black shoes, size 42", "cart": cart, "payment": forged},
        {"request": "black shoes, size 42", "cart": cart,
         "payment": {**forged, "to": shop, "merchant": shop}},
    )
    assert refused.structured_content["decision"] == "refuse"
    assert paid.structured_content["decision"] == "proceed"
    monkeypatch.delenv("ASASKED_PAYEES")
    (unpinned,) = call({"request": "black shoes, size 42", "cart": cart, "payment": forged})
    assert unpinned.structured_content["decision"] == "proceed"
    assert any("forged" in n for n in unpinned.structured_content["notes"])


def test_agent_cannot_claim_the_address_is_bound(heard):
    # A binding is the caller's own check of the site; an agent that says so
    # proves nothing, so the tool drops it.
    shop = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    payment = {"token": "USDC", "network": "solana", "amount": 129.99, "to": shop,
               "merchant": shop, "rate": 1.0,
               "binding": {"outcome": "bound", "reason": "payee-bound"}}
    (result,) = call({"request": "black shoes, size 42", "cart": [{**SHOES, "size": "42"}],
                      "payment": payment})
    assert any("forged" in n for n in result.structured_content["notes"])


def test_server_asks_the_site_itself(heard, monkeypatch):
    from asasked.payee_binding import BOUND, EXCLUDED, INCONCLUSIVE, Binding
    shop = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    chain = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
    asked = []

    def site_says(outcome, reason):
        def check(origin, network, pay_to, name=None):
            asked.append((origin, network, pay_to) + ((name,) if name else ()))
            return Binding(outcome, reason, origin, network, pay_to, detail="from the site")
        return check

    payment = {"token": "USDC", "network": "solana", "amount": 129.99, "to": shop,
               "rate": 1.0, "origin": "https://shop.example", "chain": chain}
    order = {"request": "black shoes, size 42", "cart": [{**SHOES, "size": "42"}],
             "payment": payment}

    monkeypatch.setattr(mcp_server, "CHECK_PAYEE", site_says(BOUND, "payee-bound"))
    (bound,) = call(order)
    assert asked == [("https://shop.example", chain, shop)]
    assert bound.structured_content["decision"] == "proceed"
    assert not any("unchecked" in n or "forged" in n for n in bound.structured_content["notes"])

    monkeypatch.setattr(mcp_server, "CHECK_PAYEE", site_says(EXCLUDED, "payto-not-authorized"))
    (excluded,) = call(order)
    assert excluded.structured_content["decision"] == "refuse"

    monkeypatch.setattr(mcp_server, "CHECK_PAYEE", site_says(INCONCLUSIVE, "unsigned"))
    (unknown,) = call(order)
    assert unknown.structured_content["decision"] == "proceed"
    assert any("unsigned" in n for n in unknown.structured_content["notes"])

    asked.clear()
    call({**order, "payment": {**payment, "payee_name": "pay.shop.eth"}})
    assert asked == [("https://shop.example", chain, shop, "pay.shop.eth")]

    monkeypatch.setenv("ASASKED_PAYEE_CHECK", "off")
    asked.clear()
    call(order)
    assert asked == []


def test_origin_without_chain_or_https_is_inconclusive(heard, monkeypatch):
    shop = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    monkeypatch.setattr(mcp_server, "CHECK_PAYEE", None)
    base = {"token": "USDC", "network": "solana", "amount": 129.99, "to": shop, "rate": 1.0}
    for extra, reason in (({"origin": "https://shop.example"}, "no-chain"),
                          ({"origin": "http://shop.example", "chain": "solana:x"}, "bad-origin")):
        (result,) = call({"request": "black shoes, size 42", "cart": [{**SHOES, "size": "42"}],
                          "payment": {**base, **extra}})
        assert result.structured_content["decision"] == "proceed"
        assert any(reason in n for n in result.structured_content["notes"]), reason
