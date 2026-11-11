"""Hidden subscriptions: an item that renews is asked about unless the person
asked for a subscription or agreed to one. No model is called here."""

import pytest

from asasked import coherence
from asasked.coherence import IntentFacts, merge_facts, retelling_differences
from asasked.guard import ASK, PROCEED, Guard
from asasked.stress_subscription import CARTS, CASES

BALLS = IntentFacts(raw="x", brand="Wilson", model="US Open", quantity=4)


def check(facts, cart):
    return Guard("x", today="Wednesday, 11 November 2026", extract=lambda _t: facts).check(cart)


def test_a_subscription_nobody_asked_for_is_asked_about():
    got = check(BALLS, CARTS["balls_sub"])
    assert got["decision"] == ASK
    assert got["reasons"] == ["Not a one-time purchase: a subscription that charges $5.39 every "
                              "month: Wilson US Open Extra Duty tennis balls, can of 3 "
                              "(Subscribe & Save)."]


def test_a_subscription_the_person_wants_passes():
    from dataclasses import replace
    assert check(replace(BALLS, wants_recurring=True), CARTS["balls_sub"])["decision"] == PROCEED


@pytest.mark.parametrize("recurring", [None, False])
def test_a_one_time_item_passes_and_says_nothing(recurring):
    cart = [{**CARTS["balls"][0], "recurring": recurring}]
    got = check(BALLS, cart)
    assert got["decision"] == PROCEED and got["notes"] == []


def test_a_subscription_never_softens():
    facts = IntentFacts(raw="x", brand="Wilson", soft=frozenset({"brand"}),
                        disputed=frozenset({"quantity"}))
    assert check(facts, CARTS["balls_sub"])["decision"] == ASK


def test_a_free_trial_counts_at_its_monthly_price_against_a_limit():
    asked = IntentFacts(raw="x", explicit_max_cents=1000, wants_recurring=True)
    got = check(asked, CARTS["tv"])
    assert got["decision"] == ASK
    assert got["reasons"] == ["Set a limit of $10.00, the order costs $10.99 at the "
                              "subscription price."]
    roomy = IntentFacts(raw="x", explicit_max_cents=1500, wants_recurring=True)
    assert check(roomy, CARTS["tv"])["decision"] == PROCEED


def test_a_trial_added_next_to_the_item_is_asked_about():
    facts = IntentFacts(raw="x", brand="Garmin", model="Forerunner 265", quantity=1)
    got = check(facts, CARTS["watch_trial"])
    assert got["decision"] == ASK
    assert any("every month" in r and "Connect+" in r for r in got["reasons"])


def test_when_facts_fail_the_question_names_the_renewal():
    def broken(_text):
        raise coherence.ExtractionError("no model")
    got = Guard("x", today="Wednesday, 11 November 2026", extract=broken).check(CARTS["tv"])
    assert "$0.00 each, then $10.99 every month" in got["question"]


@pytest.mark.parametrize("recurring", [{"every": ""}, "monthly", {"price": 3},
                                       {"every": "month", "price": -1},
                                       {"every": "month", "price": True}])
def test_a_malformed_recurring_is_refused(recurring):
    with pytest.raises(ValueError, match="recurring"):
        check(BALLS, [{**CARTS["balls"][0], "recurring": recurring}])


def test_models_must_agree_that_a_subscription_is_fine():
    yes, no = IntentFacts(raw="x", wants_recurring=True), IntentFacts(raw="x")
    split = merge_facts([yes, no])
    assert split.wants_recurring is False and "wants_recurring" not in split.disputed
    assert merge_facts([yes, yes]).wants_recurring is True


def test_extraction_reads_the_subscription_fact(monkeypatch):
    monkeypatch.setattr(coherence, "call_model",
                        lambda request, provider=None, today=None: {"wants_recurring": True})
    assert coherence.extract_intent("every month, please").wants_recurring is True


def test_retelling_names_a_subscription_the_person_did_not_sign():
    found = retelling_differences(IntentFacts(raw="x"), IntentFacts(raw="y", wants_recurring=True))
    assert "subscription: the person signed not said, the agent says a subscription is fine" \
        in found[0].text


def test_the_case_set_is_well_formed():
    assert len(CASES) == 16
    for case in CASES:
        assert case.cart in CARTS and case.expect in (ASK, PROCEED)
        assert (case.reply is None) == (case.after is None)
        if case.reply is not None:
            assert case.expect == ASK   # a reply only follows a question

