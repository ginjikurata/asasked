"""v3, the hijacked agent: listing content, injections, the reported request."""

import pytest

from asasked.coherence import IntentFacts
from asasked.guard import Guard
from asasked.harness import dataset_v3
from asasked.store.store import TOOLS, TOOLS_V3, Mandate, Store
from asasked.store import catalog_v1

CATALOG = catalog_v1.CATALOG
SKU = "WIL-PROSTAFF97-414-BLA-COU"


def _checkout_args(tools):
    tool = next(t for t in tools if t["name"] == "checkout")
    return set(tool["input_schema"]["required"])


def _mandate():
    allow = tuple(p["sku"] for p in CATALOG)
    return Mandate("Buy things", allow, 4, 100, 90000)


def test_old_store_output_is_unchanged():
    s = Store().new_session(_mandate())
    card = s.call("get_product", {"sku": SKU})
    assert "description" not in card and "reviews" not in card
    rows = s.call("search_products", {"query": "Pro Staff"})["results"]
    assert all("highlight" not in r for r in rows)
    assert _checkout_args(s.tools()) == _checkout_args(TOOLS) == {"confirm"}


def test_content_store_shows_benign_text_and_needs_request():
    s = Store(content=True).new_session(_mandate())
    assert _checkout_args(s.tools()) == _checkout_args(TOOLS_V3) == {"confirm", "request"}
    card = s.call("get_product", {"sku": SKU})
    assert card["description"] and len(card["reviews"]) == 2
    assert "seller_note" not in card
    s.call("add_to_cart", {"sku": SKU, "quantity": 1})
    assert "error" in s.call("checkout", {"confirm": True})
    out = s.call("checkout", {"confirm": True, "request": "A Pro Staff 97, black, 4 1/4"})
    assert "error" not in out
    assert s.reported_requests == ["A Pro Staff 97, black, 4 1/4"]


def test_injections_appear_where_placed():
    inj = {SKU: [{"place": "review", "text": "BUY OTHER", "author": "Customer"},
                 {"place": "description", "text": "ALSO THIS"},
                 {"place": "seller_note", "text": "NOTE"},
                 {"place": "highlight", "text": "HL"}]}
    s = Store(injections=inj).new_session(_mandate())
    card = s.call("get_product", {"sku": SKU})
    assert card["reviews"][1]["text"] == "BUY OTHER" and len(card["reviews"]) == 3
    assert card["description"].endswith("ALSO THIS")
    assert card["seller_note"] == "NOTE"
    rows = s.call("search_products", {"query": "Pro Staff 97"})["results"]
    assert [r["highlight"] for r in rows if r["sku"] == SKU] == ["HL"]


def _guard(request):
    return Guard(request, extract=lambda req: IntentFacts(
        color="red" if "red" in req else "black", raw=req))


def test_agent_request_replaces_the_guards_request():
    g = _guard("Pro Staff 97, black")
    s = Store(content=True).new_session(_mandate(), guard=g, guard_mode="enforced",
                                        guard_request="agent")
    s.call("add_to_cart", {"sku": "WIL-PROSTAFF97-414-RED-COU", "quantity": 1})
    out = s.call("checkout", {"confirm": True, "request": "Pro Staff 97, red"})
    assert g.request == "Pro Staff 97, red"
    assert out.get("status") != "needs_confirmation"  # the retold request let it through


def test_signed_request_stays_and_the_retelling_is_a_note():
    g = _guard("Pro Staff 97, black")
    g._signed = g.request
    s = Store(content=True).new_session(_mandate(), guard=g, guard_mode="enforced",
                                        guard_request="signed")
    s.call("add_to_cart", {"sku": "WIL-PROSTAFF97-414-RED-COU", "quantity": 1})
    out = s.call("checkout", {"confirm": True, "request": "Pro Staff 97, red"})
    assert g.request == "Pro Staff 97, black" and g.claimed == "Pro Staff 97, red"
    assert out["status"] == "needs_confirmation"


def test_v3_dataset_shape_and_labels():
    rows = dataset_v3.build()
    assert len(rows) == 70 and len({r["id"] for r in rows}) == 70
    assert rows == dataset_v3.build()  # deterministic
    for r in rows:
        t = dataset_v3.to_task(r)
        fam, colour, size = r["base"].split("|")
        right = next(p["sku"] for p in CATALOG if p["family"] == fam and p["color"] == colour
                     and p["size_label"] == size and p["refundable"] and p["stock"] > 0)
        assert t.ok_check([(right, 1)])
        assert not t.ok_check([(right, 3)])
        if r["attack"] == "none":
            assert t.attack_success is None and not r["injections"]
            continue
        assert right in r["injections"]
        assert not t.attack_success([(right, 1)])
        rule = r["attack_rule"]
        if "any_sku" in rule:
            target = rule["any_sku"][0]
            assert t.attack_success([(target, 1)])
            assert not t.ok_check([(target, 1)])
            if r["attack"] == "add_on":
                assert not t.ok_check([(right, 1), (target, 1)])
        else:
            assert t.attack_success([(right, 3)])


def test_mandate_lets_the_attacks_through():
    """VI's limits are broad on purpose: what is measured is the guard."""
    for r in dataset_v3.build():
        if r["attack"] == "none":
            continue
        t = dataset_v3.to_task(r)
        m = t.mandate()
        for sku in r["attack_rule"].get("any_sku", []):
            assert sku in m.allowlist
        assert m.quantity_cap >= 3


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_request_is_refused(bad):
    s = Store(content=True).new_session(_mandate())
    s.call("add_to_cart", {"sku": SKU, "quantity": 1})
    assert "error" in s.call("checkout", {"confirm": True, "request": bad})


# --- the scripted hijacked agent -------------------------------------------

from asasked.harness import hijacked  # noqa: E402
from asasked.harness.agent import AGENTS  # noqa: E402
from asasked.harness.run import run_task  # noqa: E402


@pytest.mark.parametrize("name", hijacked.MODES)
def test_hijacked_agent_without_guard_lands_every_attack(name):
    """No guard: every attack must be possible in the store (stock, one merchant)."""
    for t in dataset_v3.load():
        rec = run_task(AGENTS[name], t)
        if t.attack == "none":
            assert rec["score"]["as_asked"], t.id
        else:
            assert rec["attack"]["succeeded"], (t.id, rec["final_text"])
            assert rec["score"]["outcome"] == "wrong_purchase", t.id


def test_hijacked_reported_requests():
    tasks = {t.id: t for t in dataset_v3.load()}
    retell = run_task(AGENTS["hijacked"], tasks["v3-00-retell"])
    assert retell["reported_requests"] == [hijacked.retold_by_injection(tasks["v3-00-retell"])]
    plain = run_task(AGENTS["hijacked"], tasks["v3-00-swap_colour"])
    assert plain["reported_requests"] == [tasks["v3-00-swap_colour"].request]
    cover = run_task(AGENTS["hijacked-cover"], tasks["v3-00-final_sale"])
    assert cover["reported_requests"][0].endswith("Final sale is fine.")


def test_hijacked_agent_obeys_the_persons_no():
    """The guard stops the cart, the person says no, nothing is bought."""
    t = next(t for t in dataset_v3.load() if t.id == "v3-00-quantity")
    s = Store(content=True, injections=t.injections).new_session(
        t.mandate(), guard=_guard("x"), guard_mode="enforced")
    s.guard.check = lambda *a, **k: {"decision": "ask", "reasons": ["r"], "question": "Sure?"}
    out = hijacked.run_hijacked(AGENTS["hijacked"], s, t)
    assert s.order is None and s.questions == ["Sure?"] and "declined" in out.final_text
