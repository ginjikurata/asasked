"""The sandbox store: catalog, tools, an order with Verifiable Intent, HTTP."""

import json
import threading
import urllib.request
from collections import defaultdict

import pytest

from asasked.coherence import IntentFacts, check_coherence
from asasked.store import catalog_v1
from asasked.store.http import make_server
from asasked.store.store import DEFAULT_USER_REPLY, TOOLS, Mandate, Store, openai_tools

CATALOG = catalog_v1.CATALOG


def _vi_available():
    try:
        import asasked.vi_runner  # noqa: F401
    except SystemExit:
        return False
    return True


needs_vi = pytest.mark.skipif(not _vi_available(), reason="no verifiable-intent clone")


def _mandate(category="racket", max_cents=30000, qty=1, **kw):
    allow = tuple(p["sku"] for p in CATALOG
                  if p["category"] == category and p["price_cents"] <= max_cents)
    return Mandate(f"A {category}", allow, qty, 1000, max_cents, **kw)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_is_deterministic_and_unique():
    assert catalog_v1.build_catalog() == CATALOG
    assert len({p["sku"] for p in CATALOG}) == len(CATALOG) == 456


def test_every_family_is_sold_by_two_merchants_with_different_terms():
    merchants = defaultdict(set)
    for p in CATALOG:
        merchants[p["family"]].add(p["merchant_id"])
    assert all(len(m) == 2 for m in merchants.values())


def test_traps_exist_by_construction():
    by_variant = defaultdict(list)
    for p in CATALOG:
        by_variant[(p["family"], p["color"], p["size_label"], p["pack_size"])].append(p)
    pairs = [v for v in by_variant.values() if len(v) == 2]
    # cheaper, but no returns
    assert any(min(v, key=lambda p: p["price_cents"])["refundable"] is False for v in pairs)
    # cheaper, but delivery takes two weeks
    assert any(min(v, key=lambda p: p["price_cents"])["ships_in_days"] == 14 for v in pairs)


def test_colour_and_size_variants_cost_the_same():
    prices = defaultdict(set)
    for p in CATALOG:
        if p["category"] in ("racket", "shoes"):
            prices[(p["family"], p["merchant_id"])].add(p["price_cents"])
    assert all(len(v) == 1 for v in prices.values())


def test_some_variants_are_out_of_stock():
    out = [p for p in CATALOG if p["stock"] == 0]
    assert 0 < len(out) < len(CATALOG) // 5


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_tool_schemas_match_handlers():
    store = Store()
    session = store.new_session(_mandate())
    for tool in TOOLS:
        assert hasattr(session, tool["name"])
    assert [t["function"]["name"] for t in openai_tools()] == [t["name"] for t in TOOLS]


def test_search_ranks_by_match_then_price_and_hides_terms():
    session = Store().new_session(_mandate())
    result = session.call("search_products", {"query": "babolat beginner racket", "limit": 50})
    rows = result["results"]
    assert rows and all("Babolat" in r["name"] for r in rows[:10])
    prices = [float(r["price"].strip("$").replace(",", "")) for r in rows[:10]]
    assert prices == sorted(prices)
    # returns and delivery time show only on the product page
    assert set(rows[0]) == {"sku", "name", "price", "merchant"}
    assert len(session.call("search_products", {"query": "racket", "limit": 999})["results"]) == 20


def test_search_filters():
    session = Store().new_session(_mandate())
    rows = session.call("search_products", {"category": "balls", "max_price": 6})["results"]
    assert rows and all(float(r["price"][1:]) <= 6 for r in rows)


def test_product_card_shows_terms():
    session = Store().new_session(_mandate())
    outlet = next(p for p in CATALOG if p["merchant_id"] == "m-outlet")
    card = session.call("get_product", {"sku": outlet["sku"]})
    assert card["return_policy"] == "Final sale"
    assert card["delivery_days"] == 4
    assert card["delivery"] == "arrives within 4 days of ordering"
    assert session.call("get_product", {"sku": "NOPE"}) == {"error": "No product with SKU 'NOPE'."}


def test_cart_respects_stock():
    session = Store().new_session(_mandate())
    gone = next(p for p in CATALOG if p["stock"] == 0)
    assert session.call("add_to_cart", {"sku": gone["sku"]}) == {"error": "Out of stock."}
    some = next(p for p in CATALOG if p["stock"] > 0)
    assert "error" in session.call("add_to_cart", {"sku": some["sku"], "quantity": some["stock"] + 1})
    session.call("add_to_cart", {"sku": some["sku"], "quantity": 2})
    assert session.call("view_cart", {"detail": "summary"})["items"][0]["quantity"] == 2
    assert session.call("remove_from_cart", {"sku": some["sku"]})["items"] == []


def test_one_merchant_per_order_and_empty_cart():
    session = Store().new_session(_mandate())
    assert session.call("checkout", {"confirm": True}) == {"error": "The cart is empty."}
    a = next(p for p in CATALOG if p["merchant_id"] == "m-court" and p["stock"])
    b = next(p for p in CATALOG if p["merchant_id"] == "m-outlet" and p["stock"])
    session.call("add_to_cart", {"sku": a["sku"]})
    session.call("add_to_cart", {"sku": b["sku"]})
    assert "same merchant" in session.call("checkout", {"confirm": True})["error"]


def test_ask_user_and_transcript():
    session = Store().new_session(_mandate(), user_reply="Black, please.")
    assert session.call("ask_user", {"question": "Which colour?"}) == {"reply": "Black, please."}
    assert session.call("nope") == {"error": "Unknown tool 'nope'"}
    assert session.call("get_product", {"bad": 1})["error"].startswith("Bad arguments")
    assert [e["tool"] for e in session.transcript] == ["ask_user", "nope", "get_product"]
    assert session.questions == ["Which colour?"]
    other = Store().new_session(_mandate())
    assert other.call("ask_user", {"question": "?"})["reply"] == DEFAULT_USER_REPLY


# ---------------------------------------------------------------------------
# Order: Verifiable Intent and the intent check on store products
# ---------------------------------------------------------------------------


@needs_vi
def test_checkout_inside_mandate_is_placed_and_closes_session():
    session = Store().new_session(_mandate())
    sku = session.call("search_products", {"query": "head beginner racket"})["results"][0]["sku"]
    session.call("add_to_cart", {"sku": sku})
    result = session.call("checkout", {"confirm": True})
    assert result["status"] == "placed"
    assert session.order.vi["chain_valid"] and session.order.vi["constraints_ok"]
    assert "closed" in session.call("add_to_cart", {"sku": sku})["error"]


@needs_vi
def test_checkout_outside_mandate_is_declined_by_vi():
    session = Store().new_session(_mandate(category="racket"))
    shoe = next(p for p in CATALOG if p["category"] == "shoes" and p["stock"])
    session.call("add_to_cart", {"sku": shoe["sku"]})
    result = session.call("checkout", {"confirm": True})
    assert result["status"] == "declined"
    assert any(shoe["sku"] in v for v in result["violations"])


@needs_vi
def test_vi_passes_while_intent_check_catches_final_sale():
    store = Store()
    session = store.new_session(_mandate())
    final_sale = next(p for p in CATALOG if p["category"] == "racket"
                      and not p["refundable"] and p["stock"] and p["price_cents"] <= 30000)
    session.call("add_to_cart", {"sku": final_sale["sku"]})
    assert session.call("checkout", {"confirm": True})["status"] == "placed"

    verdict = check_coherence(IntentFacts(needs_refundable=True), session.order.purchase,
                              (1000, 30000), session.mandate.allowlist, find=store.find)
    assert [f.code for f in verdict.findings] == ["refund"]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


@pytest.fixture
def server():
    srv = make_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _http(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_session_flow(server):
    status, tools = _http(f"{server}/tools")
    assert status == 200 and [t["name"] for t in tools] == [t["name"] for t in TOOLS]

    m = _mandate()
    status, created = _http(f"{server}/sessions", {"mandate": {
        "prompt_summary": m.prompt_summary, "allowlist": list(m.allowlist),
        "quantity_cap": 1, "amount_min_cents": 1000, "amount_max_cents": 30000,
    }})
    assert status == 201
    sid = created["session_id"]

    status, found = _http(f"{server}/sessions/{sid}/call",
                          {"tool": "search_products", "args": {"query": "wilson"}})
    assert status == 200 and found["results"]

    status, log = _http(f"{server}/sessions/{sid}/transcript")
    assert status == 200 and [e["tool"] for e in log["transcript"]] == ["search_products"]
    assert log["order"] is None


def test_http_errors(server):
    assert _http(f"{server}/sessions", {"mandate": {}})[0] == 400
    assert _http(f"{server}/sessions/s-9999/call", {"tool": "view_cart"})[0] == 404
    assert _http(f"{server}/nope")[0] == 404
