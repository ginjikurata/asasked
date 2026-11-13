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
    assert len(CASES) == 20
    for case in CASES:
        assert case.cart in CARTS and case.expect in (ASK, PROCEED)
        assert (case.reply is None) == (case.after is None)
        assert case.then is None or (case.reply is not None and case.then in CARTS)
        if case.reply is not None:
            assert case.expect == ASK   # a reply only follows a question



# ---------------------------------------------------------------------------
# An agreed subscription holds its interval and renewal price
# ---------------------------------------------------------------------------

def _agreeing_guard(after_answer: IntentFacts) -> Guard:
    """Before the answer: facts with no subscription; after it, after_answer."""
    def extract(text):
        return after_answer if "The person answered" in text else BALLS
    return Guard("x", today="Wednesday, 11 November 2026", extract=extract)


def test_monthly_agreed_then_weekly_at_the_same_first_charge_asks_again():
    from dataclasses import replace
    guard = _agreeing_guard(replace(BALLS, wants_recurring=True))
    first = guard.check(CARTS["balls_sub"])
    assert first["decision"] == ASK
    guard.hear(first["question"], "yes, a monthly subscription is fine")
    assert guard.check(CARTS["balls_sub"])["decision"] == PROCEED
    weekly = guard.check(CARTS["balls_sub_weekly"])
    assert weekly["decision"] == ASK
    assert weekly["reasons"] == ["You agreed to a subscription every month; this one charges "
                                 "$5.39 every week: Wilson US Open Extra Duty tennis balls, "
                                 "can of 3 (Subscribe & Save, weekly)."]


def test_an_interval_change_heard_and_approved_is_said_once():
    from dataclasses import replace
    guard = _agreeing_guard(replace(BALLS, wants_recurring=True, recurring_every="month"))
    guard.hear(guard.check(CARTS["balls_sub"])["question"], "yes, a monthly subscription is fine")
    weekly = guard.check(CARTS["balls_sub_weekly"])
    assert weekly["decision"] == ASK
    assert weekly["reasons"] == ["You agreed to a subscription every month; this one charges "
                                 "$5.39 every week: Wilson US Open Extra Duty tennis balls, "
                                 "can of 3 (Subscribe & Save, weekly)."]


def test_a_dearer_renewal_after_agreeing_asks_again():
    from dataclasses import replace
    guard = _agreeing_guard(replace(BALLS, wants_recurring=True))
    guard.hear(guard.check(CARTS["balls_sub"])["question"], "ok")
    got = guard.check(CARTS["balls_sub_dearer"])
    assert got["decision"] == ASK
    assert got["reasons"] == ["You agreed to $5.39 every month; this subscription renews at "
                              "$6.49: Wilson US Open Extra Duty tennis balls, can of 3 "
                              "(Subscribe & Save)."]
    # cheaper renewals at the same interval are no new question
    cheaper = [{**CARTS["balls_sub"][0], "recurring": {"every": "month", "price": 4.99}}]
    assert guard.check(cheaper)["decision"] == PROCEED


def test_the_agreed_terms_are_asked_again_once_and_then_hold():
    from dataclasses import replace
    guard = _agreeing_guard(replace(BALLS, wants_recurring=True))
    guard.hear(guard.check(CARTS["balls_sub"])["question"], "ok")
    weekly = guard.check(CARTS["balls_sub_weekly"])
    guard.hear(weekly["question"], "weekly is fine too")
    assert guard.check(CARTS["balls_sub_weekly"])["decision"] == PROCEED


def test_the_interval_the_person_named_is_held():
    from dataclasses import replace
    monthly = replace(BALLS, wants_recurring=True, recurring_every="month")
    assert check(monthly, CARTS["balls_sub"])["decision"] == PROCEED
    got = check(monthly, CARTS["balls_sub_weekly"])
    assert got["decision"] == ASK
    assert got["reasons"] == ["Agreed to a subscription every month, this one charges $5.39 "
                              "every week: Wilson US Open Extra Duty tennis balls, can of 3 "
                              "(Subscribe & Save, weekly)."]
    assert check(replace(monthly, recurring_every="monthly"),
                 CARTS["balls_sub"])["decision"] == PROCEED


def test_a_limit_a_month_counts_every_charge_in_a_month():
    weekly = IntentFacts(raw="x", explicit_max_cents=1000, max_every="month",
                         wants_recurring=True)
    got = check(weekly, CARTS["tv_weekly"])
    assert got["decision"] == ASK
    assert got["reasons"] == ["Set a limit of $10.00 a month, the order costs $24.95 in "
                              "renewals over a month."]
    # the same $10 a month passes a monthly $9.99, and a weekly limit counts one charge
    monthly = [{**CARTS["tv"][0], "recurring": {"every": "month", "price": 9.99}}]
    assert check(weekly, monthly)["decision"] == PROCEED
    from dataclasses import replace
    assert check(replace(weekly, max_every="week"), CARTS["tv_weekly"])["decision"] == PROCEED
    # a yearly renewal is one charge in a month, and it is over $10
    yearly = [{**CARTS["tv"][0], "recurring": {"every": "year", "price": 99}}]
    assert check(weekly, yearly)["decision"] == ASK


@pytest.mark.parametrize("text,days", [("month", 365.25 / 12), ("monthly", 365.25 / 12),
                                       ("2 weeks", 14), ("every 3 months", 365.25 / 4),
                                       ("week", 7), ("Yearly", 365.25), ("fortnight", 14),
                                       ("whenever", None), ("", None)])
def test_intervals_are_read_in_days(text, days):
    got = coherence.interval_days(text)
    assert got == pytest.approx(days) if days else got is None


def test_charges_in_the_worst_period():
    assert coherence._charges_in("week", "month") == 5
    assert coherence._charges_in("month", "year") == 12
    assert coherence._charges_in("month", "month") == 1
    assert coherence._charges_in("year", "month") == 1
    assert coherence._charges_in("week", None) == 1


def test_models_disagreeing_on_the_interval_ask():
    a = IntentFacts(raw="x", wants_recurring=True, recurring_every="month")
    b = IntentFacts(raw="x", wants_recurring=True, recurring_every="week")
    merged = merge_facts([a, b])
    assert check(merged, CARTS["balls_sub"])["decision"] == ASK
    assert merge_facts([a, IntentFacts(raw="x", wants_recurring=True)]).recurring_every == "month"


def test_the_longest_limit_period_wins():
    a = IntentFacts(raw="x", explicit_max_cents=1000, max_every="week")
    b = IntentFacts(raw="x", explicit_max_cents=1000, max_every="month")
    assert merge_facts([a, b]).max_every == "month"
    assert merge_facts([a, IntentFacts(raw="x", explicit_max_cents=1000)]).max_every == "week"

