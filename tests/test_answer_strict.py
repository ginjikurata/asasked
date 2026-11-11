"""After the person answered the guard's question, one model alone cannot
weaken a requirement: a misread "no" must not let the refused cart through."""

from asasked import coherence
from asasked.coherence import IntentFacts, merge_facts
from asasked.guard import Guard

def test_after_an_answer_a_dispute_does_not_soften_a_stop():
    keeps = IntentFacts(raw="x", needs_refundable=True)
    drops = IntentFacts(raw="x", needs_refundable=False)
    assert "needs_refundable" in merge_facts([keeps, drops]).disputed
    strict = merge_facts([keeps, drops], strict=True)
    assert strict.needs_refundable is True and strict.disputed == frozenset()


def test_after_an_answer_soft_needs_every_model():
    soft = IntentFacts(raw="x", color="black", soft=frozenset({"color"}))
    firm = IntentFacts(raw="x", color="black")
    dropped = IntentFacts(raw="x")
    assert merge_facts([soft, firm], strict=True).soft == frozenset()
    assert merge_facts([soft, dropped], strict=True).soft == {"color"}
    assert merge_facts([soft, firm]).soft == {"color"}


def test_after_an_answer_the_reading_with_more_items_is_taken_whole():
    racket = {"brand": "Babolat", "model": "Pure Aero 98", "quantity": 1}
    bag = {"brand": "Babolat", "model": "Pure Aero Bag", "quantity": 1}
    both = IntentFacts(raw="x", lines=(racket, bag))
    one = IntentFacts(raw="x", brand="Babolat", model="Pure Aero 98", quantity=1)
    for order in ([one, both], [both, one]):
        got = merge_facts(order, strict=True)
        assert got.lines == (racket, bag) and got.disputed == frozenset()
        assert got.model is None and got.quantity is None
    assert "line_count" in merge_facts([one, both]).disputed


def test_strict_follows_the_answer_in_the_request(monkeypatch):
    seen = []
    monkeypatch.setattr(coherence, "merge_facts", lambda r, strict: seen.append(strict) or r[0])
    monkeypatch.setattr(coherence, "extract_intent", lambda *a: IntentFacts(raw="x"))
    coherence.extract_intent_agreed("buy it", providers=("a",))
    guard = Guard("buy it", today="Wednesday, 11 November 2026", providers=("a",))
    guard.hear("Go ahead?", "no")
    guard.facts()
    assert seen == [False, True]


def test_a_broken_number_is_asked_again(monkeypatch):
    answers = iter([{"deadline_days": -1}, {"deadline_days": None, "explicit_max_cents": 2000}])
    monkeypatch.setattr(coherence, "call_model", lambda *a, **k: next(answers))
    facts = coherence.extract_intent("under $20")
    assert facts.deadline_days is None and facts.explicit_max_cents == 2000


def test_a_number_broken_twice_fails(monkeypatch):
    import pytest
    monkeypatch.setattr(coherence, "call_model", lambda *a, **k: {"explicit_max_cents": 0})
    with pytest.raises(coherence.ExtractionError):
        coherence.extract_intent("buy it")
