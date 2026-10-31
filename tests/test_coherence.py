"""Сверка намерения с корзиной на 8 сценариях — без языковой модели.

Факты здесь заданы вручную: ровно то, что извлечение должно вернуть из
просьбы. Так проверяется детерминированная половина, которая и идёт в спор.
"""

import pytest

from asasked import coherence
from asasked.coherence import (
    ASK, BLOCK, PROCEED, WARN, IntentFacts, check_coherence, decide_before_purchase,
)
from asasked.llm_extract import ExtractionError
from asasked.scenarios import SCENARIOS

FACTS = {
    "ok-baseline": IntentFacts(brand="Babolat", level="beginner",
                               price_preference="cheap", explicit_max_cents=1500000),
    "price-top": IntentFacts(level="beginner", price_preference="cheap"),
    "brand-swap": IntentFacts(brand="Babolat"),
    "variant": IntentFacts(brand="ASICS", color="black", size_label="42"),
    "quantity": IntentFacts(quantity=2),
    "refund": IntentFacts(needs_refundable=True),
    "deadline": IntentFacts(deadline_days=5),
    "vi-catches": IntentFacts(level="beginner", explicit_max_cents=1500000),
}

# какие находки обязана дать сверка в каждом сценарии
EXPECTED_CODES = {
    "ok-baseline": set(),
    "price-top": {"level", "price"},
    "brand-swap": {"brand"},
    "variant": {"color", "size"},
    "quantity": {"quantity"},
    "refund": {"refund"},
    "deadline": {"deadline"},
    "vi-catches": {"level"},
}


def _check(scn, facts):
    return check_coherence(facts, scn.purchase,
                           (scn.amount_min_cents, scn.amount_max_cents),
                           scn.allowlist)


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.id)
def test_scenario_verdict(scn):
    verdict = _check(scn, FACTS[scn.id])
    assert verdict.coherent == (scn.expect == "coherent")
    assert {f.code for f in verdict.findings} == EXPECTED_CODES[scn.id]
    assert all(f.severity == BLOCK for f in verdict.findings)


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.id)
def test_prepurchase_asks_on_divergence(scn):
    decision = decide_before_purchase(FACTS[scn.id], scn.purchase,
                                      (scn.amount_min_cents, scn.amount_max_cents),
                                      scn.allowlist)
    assert decision.action == (PROCEED if scn.expect == "coherent" else ASK)
    assert (decision.question is None) == (decision.action == PROCEED)


def test_soft_field_warns_instead_of_blocking():
    facts = IntentFacts(brand="ASICS", color="black", soft=frozenset({"color"}))
    purchase = [("ASI-GEL-44-WH", 1)]
    allowlist = ["ASI-GEL-42-BK", "ASI-GEL-44-WH"]

    verdict = check_coherence(facts, purchase, (10000, 15000), allowlist)
    assert verdict.coherent
    assert [(f.code, f.severity) for f in verdict.findings] == [("color", WARN)]

    decision = decide_before_purchase(facts, purchase, (10000, 15000), allowlist)
    assert decision.action == PROCEED
    assert [f.code for f in decision.notes] == ["color"]


def test_softness_does_not_leak_to_other_fields():
    facts = IntentFacts(color="black", size_label="42", soft=frozenset({"color"}))
    verdict = check_coherence(facts, [("ASI-GEL-44-WH", 1)], (10000, 15000))
    assert not verdict.coherent
    assert {(f.code, f.severity) for f in verdict.findings} == {
        ("color", WARN), ("size", BLOCK),
    }


def test_same_inputs_same_findings():
    scn = next(s for s in SCENARIOS if s.id == "variant")
    texts = {tuple(f.text for f in _check(scn, FACTS[scn.id]).findings) for _ in range(20)}
    assert len(texts) == 1


# ---------------------------------------------------------------------------
# Разбор ответа модели — сеть подменена, проверяется только валидация
# ---------------------------------------------------------------------------


def _fake_model(monkeypatch, data):
    monkeypatch.setattr(coherence, "call_model", lambda request, provider=None, today=None: data)


def test_extract_maps_model_answer(monkeypatch):
    _fake_model(monkeypatch, {
        "brand": "ASICS", "color": "black", "size_label": "42", "level": "advanced",
        "quantity": "2", "needs_refundable": True, "soft_fields": ["color"],
    })
    facts = coherence.extract_intent("…", deadline_days=3)
    assert facts.level == "pro"
    assert facts.quantity == 2
    assert facts.deadline_days == 3
    assert facts.soft == frozenset({"color"})


@pytest.mark.parametrize("data", [
    {"quantity": True},
    {"quantity": "пара"},
    {"brand": 5},
    {"soft_fields": "color"},
    {"soft_fields": ["mood"]},
])
def test_extract_rejects_malformed_answer(monkeypatch, data):
    _fake_model(monkeypatch, data)
    with pytest.raises(ExtractionError):
        coherence.extract_intent("…")
