"""On-chain payment checks: token, network, recipient, amount, limit, slippage."""

import asyncio
from dataclasses import replace

import pytest

from asasked import coherence
from asasked.coherence import BLOCK, WARN, IntentFacts, merge_facts, retelling_differences
from asasked.guard import REFUSE, Guard, plain_yes
from asasked.payment import check_payment, parse_payment, refused

SHOP = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
THIEF = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
SHOES = {"name": "Nike Pegasus 41", "brand": "Nike", "color": "Triple Black",
         "size": "42", "price": 129.99, "returnable": True, "delivery_days": 3}
USDC = {"token": "USDC", "network": "solana", "amount": 129.99, "to": SHOP,
        "merchant": SHOP, "rate": 1.0}
# 250 000 ASASKED at $0.00053 = $132.50 in, quoted 132.1 USDC out, at least 130.8
SWAP = {**USDC, "swap": {"from_token": "ASASKED", "amount_in": 250000, "rate": 0.00053,
                         "quote_out": 132.1, "min_out": 130.8}}
FACTS = IntentFacts(raw="x", color="black", size_label="42")


def guard(facts=FACTS):
    return Guard("x", today="Thursday, 12 November 2026", extract=lambda request: facts)


def codes(facts, payment, total=12999, over_limit=False):
    return {(f.code, f.severity)
            for f in check_payment(facts, parse_payment(payment), total, over_limit)}


# ---------------------------------------------------------------------------
# Each check alone
# ---------------------------------------------------------------------------


def test_a_right_payment_passes():
    assert codes(replace(FACTS, pay_with="USDC", pay_network="solana"), USDC) == set()
    assert guard(replace(FACTS, pay_with="USDC")).check([SHOES], payment=USDC)["decision"] == "proceed"


def test_a_payment_to_another_address_is_always_refused():
    # soft or disputed facts cannot make paying a stranger right, and there is
    # nothing to ask the person: the payment itself must change
    facts = replace(FACTS, soft=frozenset({"pay_with"}), disputed=frozenset({"pay_network"}))
    result = guard(facts).check([SHOES], payment={**USDC, "to": THIEF})
    assert result["decision"] == REFUSE and result["question"] is None
    assert THIEF in result["refused"][0] and SHOP in result["refused"][0]
    assert result["reasons"] == result["refused"]


def test_evm_addresses_compare_without_case_base58_with_it():
    evm = "0xAbC0000000000000000000000000000000000001"
    assert codes(FACTS, {**USDC, "to": evm.lower(), "merchant": evm}) == set()
    assert ("pay-recipient", BLOCK) in codes(FACTS, {**USDC, "to": SHOP.lower()})


def test_no_merchant_address_is_a_note():
    assert codes(FACTS, {**USDC, "merchant": None}) == {("unchecked", WARN)}


def test_the_wrong_token_asks():
    assert codes(replace(FACTS, pay_with="ASASKED"), USDC) == {("pay-token", BLOCK)}
    # with a swap, the token the person gives is what counts
    assert codes(replace(FACTS, pay_with="ASASKED"), SWAP) == set()
    assert codes(replace(FACTS, pay_with="USDC"), SWAP) == {("pay-token", BLOCK)}
    # "not a big deal" and a dispute between models only warn
    assert codes(replace(FACTS, pay_with="SOL", soft=frozenset({"pay_with"})), USDC) \
        == {("pay-token", WARN)}


def test_the_wrong_network_asks():
    facts = replace(FACTS, pay_network="solana")
    assert codes(facts, {**USDC, "network": "base"}) == {("pay-network", BLOCK)}
    assert codes(facts, {**USDC, "network": None}) == {("unchecked", WARN)}
    assert codes(replace(facts, disputed=frozenset({"pay_network"})),
                 {**USDC, "network": "Base"}) == {("pay-network", WARN)}


def test_paying_more_than_the_cart_asks_less_only_warns():
    assert codes(FACTS, {**USDC, "amount": 139.99}) == {("pay-amount", BLOCK)}
    assert codes(FACTS, {**USDC, "amount": 119.99}) == {("pay-amount", WARN)}
    # rounding within half a percent is not a finding
    assert codes(FACTS, {**USDC, "amount": 130.5}) == set()
    # only paying more is refused; paying less the person loses nothing
    over, under = (check_payment(FACTS, parse_payment({**USDC, "amount": a}), 12999)
                   for a in (139.99, 119.99))
    assert refused(over[0]) and not refused(under[0])
    # no rate: the amount cannot be compared, the person is told
    assert codes(FACTS, {**USDC, "rate": None}) == {("unchecked", WARN)}


def test_swap_costs_count_toward_the_limit():
    limited = replace(FACTS, explicit_max_cents=13000)
    # the cart is $129.99, under the limit; the swap takes $132.50 worth of ASASKED
    assert codes(limited, SWAP) == {("pay-max", BLOCK)}
    assert codes(replace(limited, soft=frozenset({"explicit_max_cents"})), SWAP) \
        == {("pay-max", WARN)}
    # the cart check already found the cart over the limit: not said twice
    assert codes(limited, SWAP, over_limit=True) == set()
    # an overpayment is refused as it is: no question about the limit on top
    assert codes(limited, {**USDC, "amount": 139.99}) == {("pay-amount", BLOCK)}
    result = guard(limited).check([{**SHOES, "price": 135}], payment={**SWAP, "amount": 135})
    assert [r for r in result["reasons"] if "limit" in r] == \
        ["Set a limit of $130.00, the order costs $135.00."]


def test_too_much_slippage_asks():
    loose = {**SWAP, "swap": {**SWAP["swap"], "quote_out": 140.0, "min_out": 130.0}}
    assert codes(FACTS, loose) == {("pay-slippage", BLOCK)}
    assert codes(FACTS, {**loose, "max_slippage_bps": 800}) == set()


def test_a_swap_that_may_not_cover_the_payment_asks():
    short = {**SWAP, "swap": {**SWAP["swap"], "quote_out": 130.5, "min_out": 129.9}}
    assert codes(FACTS, short) == {("pay-swap-short", BLOCK)}


def test_a_stated_payment_with_no_payment_shown_asks():
    assert codes(replace(FACTS, pay_with="USDC", pay_network="solana"), None) \
        == {("pay-unchecked", BLOCK)}
    assert codes(FACTS, None) == set()
    result = guard(replace(FACTS, pay_with="USDC")).check([SHOES])
    assert result["decision"] == "ask" and "pay with USDC" in result["question"]


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def test_spellings_are_one():
    payment = parse_payment({**USDC, "token": " $usdc", "network": "Solana"})
    assert (payment["token"], payment["network"]) == ("USDC", "solana")


@pytest.mark.parametrize("bad", [
    "USDC", {**USDC, "amount": 0}, {**USDC, "amount": True}, {**USDC, "to": " "},
    {k: v for k, v in USDC.items() if k != "token"}, {**USDC, "max_slippage_bps": -1},
    {**SWAP, "swap": {**SWAP["swap"], "min_out": 200}}, {**USDC, "swap": "ASASKED"},
])
def test_a_payment_that_cannot_be_read_is_an_error(bad):
    with pytest.raises(ValueError, match="payment"):
        guard().check([SHOES], payment=bad)


def test_extraction_spells_tokens_and_networks_one_way(monkeypatch):
    monkeypatch.setattr(coherence, "call_model", lambda request, provider=None, today=None:
                        {"pay_with": "$asasked ", "pay_network": "Solana"})
    facts = coherence.extract_intent("pay with my $asasked on Solana")
    assert (facts.pay_with, facts.pay_network) == ("ASASKED", "solana")


def test_models_disagreeing_on_the_token_only_warn():
    merged = merge_facts([IntentFacts(pay_with="USDC"), IntentFacts(pay_with="SOL")])
    assert merged.pay_with == "USDC" and "pay_with" in merged.disputed
    found = retelling_differences(IntentFacts(raw="x", pay_with="ASASKED"),
                                  IntentFacts(raw="y", pay_with="USDC"))
    assert "payment token: the person signed ASASKED, the agent says USDC" in found[0].text


# ---------------------------------------------------------------------------
# Through the guard
# ---------------------------------------------------------------------------


def test_payment_findings_join_the_cart_findings():
    result = guard(replace(FACTS, pay_with="ASASKED")).check(
        [{**SHOES, "size": "43"}], payment={**USDC, "to": THIEF})
    assert result["decision"] == REFUSE
    assert len(result["reasons"]) == 3     # size, token, recipient
    # the person is asked what their answer can settle, not the recipient
    assert result["question"].startswith("Before I buy this")
    assert "43" in result["question"] and "ASASKED" in result["question"]
    assert THIEF not in result["question"] and THIEF in result["refused"][0]


def test_the_token_and_the_network_are_asked_not_refused():
    # they are the person's choice: a "yes, USDC is fine" settles them
    result = guard(replace(FACTS, pay_with="SOL", pay_network="base")).check(
        [SHOES], payment=USDC)
    assert result["decision"] == "ask" and result["refused"] == []
    assert "SOL" in result["question"] and "Base" in result["question"]


def test_a_failed_extraction_still_names_the_payment_problem():
    def fail(request):
        raise coherence.ExtractionError("down")
    g = Guard("x", today="Thursday, 12 November 2026", extract=fail)
    result = g.check([SHOES], payment={**USDC, "to": THIEF})
    assert result["decision"] == REFUSE and THIEF in result["refused"][0]
    # the order is still put to the person; the recipient is not theirs to approve
    assert "couldn't automatically check" in result["question"]
    assert THIEF not in result["question"]


def test_with_the_models_down_a_plain_yes_pays_the_order_shown_and_no_other():
    def fail(request):
        raise coherence.ExtractionError("down")
    g = Guard("x", today="Thursday, 12 November 2026", extract=fail)
    asked = g.gate([SHOES], payment=USDC)
    assert asked.startswith("NOT PAID") and "Nike Pegasus 41" in asked
    g.answer("Yes, go ahead.")
    # another order is not what the person saw: asked again
    other = {**SHOES, "name": "Nike Pegasus 41 GTX", "price": 159.99}
    assert g.gate([other], payment={**USDC, "amount": 159.99}).startswith("NOT PAID")
    g.answer("ok")          # a yes to that question, about that order
    assert g.gate([SHOES], payment=USDC).startswith("NOT PAID")
    assert g.gate([other], payment={**USDC, "amount": 159.99}) is None
    assert "approved this order" in g.checks[-1]["notes"][0]


@pytest.mark.parametrize("answer", ["yes, but in white", "no", "нет", "да нет",
                                    "not yes", "I'd rather not", ""])
def test_with_the_models_down_anything_but_a_plain_yes_is_asked_again(answer):
    def fail(request):
        raise coherence.ExtractionError("down")
    g = Guard("x", today="Thursday, 12 November 2026", extract=fail)
    g.gate([SHOES], payment=USDC)
    g.answer(answer)
    assert g.gate([SHOES], payment=USDC).startswith("NOT PAID")


def test_with_the_models_down_a_yes_still_does_not_approve_a_refused_payment():
    def fail(request):
        raise coherence.ExtractionError("down")
    g = Guard("x", today="Thursday, 12 November 2026", extract=fail)
    g.gate([SHOES], payment={**USDC, "to": THIEF})
    g.answer("yes")
    assert THIEF in g.gate([SHOES], payment={**USDC, "to": THIEF})
    assert g.gate([SHOES], payment=USDC) is None


@pytest.mark.parametrize("answer,yes", [
    ("Yes", True), ("yes please, go ahead", True), ("OK, buy it", True), ("Да, давай", True),
    ("конечно, оплачивай", True), ("yes but size 43", False), ("ok no", False),
    ("nope", False), ("don't", False), ("1", False)])
def test_plain_yes(answer, yes):
    assert plain_yes(answer) is yes


def test_a_yes_does_not_approve_a_refused_payment():
    g = guard()
    told = g.gate([SHOES], payment={**USDC, "to": THIEF})
    assert told.startswith("NOT PAID") and THIEF in told
    assert "Do not ask the person to approve this payment" in told
    assert "Show the person this question" not in told
    g.answer("yes, pay that address")
    # the same payment after a "yes" is refused again, with the same text
    assert g.gate([SHOES], payment={**USDC, "to": THIEF}) == told
    # the corrected payment goes through
    assert g.gate([SHOES], payment=USDC) is None


def test_a_refusal_and_a_cart_question_come_together():
    # the cart needs the person's answer and the payment needs changing:
    # the agent is told both at once
    def extract(request):
        return replace(FACTS, size_label="43") if "43 is fine" in request else FACTS
    g = Guard("x", today="Thursday, 12 November 2026", extract=extract)
    told = g.gate([{**SHOES, "size": "43"}], payment={**USDC, "to": THIEF})
    refusal, question = told.split("The order also doesn't match", 1)
    assert THIEF in refusal and "43" not in refusal
    assert "43" in question and THIEF not in question
    g.answer("43 is fine")
    assert g.gate([{**SHOES, "size": "43"}], payment=USDC) is None


def test_protect_checks_the_payment_too():
    paid = []
    pay = guard().protect(lambda order: paid.append(order) or "paid",
                          cart=lambda order: order["items"],
                          payment=lambda order: order["payment"])
    assert pay({"items": [SHOES], "payment": {**USDC, "to": THIEF}}).startswith("NOT PAID")
    assert pay({"items": [SHOES], "payment": USDC}) == "paid" and len(paid) == 1


def test_mcp_takes_a_payment(monkeypatch):
    mcp = pytest.importorskip("mcp")  # noqa: F841
    from mcp import Client

    from asasked import mcp_server
    monkeypatch.setattr(mcp_server, "EXTRACT", lambda request: replace(FACTS, pay_with="ASASKED"))
    monkeypatch.setattr(mcp_server, "_guards", type(mcp_server._guards)())

    async def run(payment):
        async with Client(mcp_server.server) as client:
            return await client.call_tool("check_order", {
                "request": "black shoes, size 42, pay with my ASASKED", "cart": [SHOES],
                "payment": payment})
    good = asyncio.run(run(SWAP)).structured_content
    bad = asyncio.run(run({**SWAP, "to": THIEF})).structured_content
    assert good["decision"] == "proceed"
    assert bad["decision"] == "refuse" and THIEF in bad["refused"][0]
    assert bad["question"] is None
