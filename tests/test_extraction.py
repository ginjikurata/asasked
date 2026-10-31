"""Extraction with no network: providers, comparing two models, stress sets."""

from dataclasses import fields
from types import SimpleNamespace

import pytest

from asasked import coherence, llm_extract
from asasked.coherence import BLOCK, WARN, IntentFacts, check_coherence, merge_facts
from asasked.llm_extract import RESPONSE_SCHEMA, SOFTENABLE_FIELDS, ExtractionError
from asasked.stress_phrases import CASES
from asasked.stress_phrases_en import CASES_EN

# ---------------------------------------------------------------------------
# Comparing two models
# ---------------------------------------------------------------------------


def test_agreeing_models_give_no_disputes():
    a = IntentFacts(brand="ASICS", color="black", raw="…")
    b = IntentFacts(brand="asics", color="black", raw="…")
    merged = merge_facts([a, b])
    assert merged.disputed == frozenset()
    assert merged.brand == "ASICS"


def test_disagreement_keeps_the_fact_and_marks_it():
    a = IntentFacts(color=None, size_label="42", needs_refundable=False)
    b = IntentFacts(color="black", size_label="44", needs_refundable=True)
    merged = merge_facts([a, b])
    assert merged.disputed == frozenset({"color", "size_label", "needs_refundable"})
    assert merged.color == "black"            # a found value beats null
    assert merged.size_label == "42"          # both found different ones: the first model wins
    assert merged.needs_refundable is True    # may have asked for returns


def test_deadline_found_by_any_takes_the_strictest_without_dispute():
    merged = merge_facts([IntentFacts(deadline_days=4, explicit_max_cents=20000),
                          IntentFacts(deadline_days=5, explicit_max_cents=22000)])
    assert (merged.deadline_days, merged.explicit_max_cents) == (4, 20000)
    assert merged.disputed == frozenset()
    # one model missed the deadline or the cap: they still block
    one_sided = merge_facts([IntentFacts(deadline_days=None, explicit_max_cents=20000),
                             IntentFacts(deadline_days=5, explicit_max_cents=None)])
    assert (one_sided.deadline_days, one_sided.explicit_max_cents) == (5, 20000)
    assert one_sided.disputed == frozenset()


def test_soft_is_union():
    merged = merge_facts([IntentFacts(soft=frozenset({"color"})),
                          IntentFacts(soft=frozenset({"quantity"}))])
    assert merged.soft == frozenset({"color", "quantity"})


def test_disputed_field_warns_instead_of_blocking():
    facts = IntentFacts(color="black", size_label="42", disputed=frozenset({"color"}))
    verdict = check_coherence(facts, [("ASI-GEL-44-WH", 1)], (10000, 15000))
    assert {(f.code, f.severity) for f in verdict.findings} == {
        ("color", WARN), ("size", BLOCK),
    }


def test_agreed_calls_every_provider(monkeypatch):
    answers = {"gemini": {"brand": "Babolat"}, "anthropic": {"brand": "HEAD"}}
    calls = []

    def fake(request, provider=None, today=None):
        calls.append(provider)
        return answers[provider]

    monkeypatch.setattr(coherence, "call_model", fake)
    facts = coherence.extract_intent_agreed("…", providers=("gemini", "anthropic"))
    assert calls == ["gemini", "anthropic"]
    assert facts.brand == "Babolat"
    assert facts.disputed == frozenset({"brand"})


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def test_unknown_provider():
    with pytest.raises(ExtractionError, match="Unknown provider"):
        llm_extract.call_model("…", provider="nope")


class _FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _fake_anthropic(monkeypatch, response):
    anthropic = pytest.importorskip("anthropic")
    messages = _FakeMessages(response)
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **kw: SimpleNamespace(messages=messages))
    return messages


def test_anthropic_request_and_parse(monkeypatch):
    text = '{"brand": "ASICS", "soft_fields": []}'
    messages = _fake_anthropic(monkeypatch, SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
    ))
    assert llm_extract.call_model("black ASICS", provider="anthropic")["brand"] == "ASICS"

    sent = messages.kwargs
    assert sent["model"] == llm_extract.CLAUDE_MODEL
    assert sent["system"] == llm_extract.SYSTEM_PROMPT
    assert sent["output_config"]["format"]["schema"] is RESPONSE_SCHEMA
    assert "temperature" not in sent          # the API no longer accepts sampling


def test_anthropic_unfinished_answer_is_an_error(monkeypatch):
    _fake_anthropic(monkeypatch, SimpleNamespace(stop_reason="refusal", content=[]))
    with pytest.raises(ExtractionError, match="refusal"):
        llm_extract.call_model("…", provider="anthropic")


class _FakeHTTP:
    """A mock urlopen: answers with prepared replies in turn."""

    def __init__(self, replies):
        self.replies, self.bodies = list(replies), []

    def __call__(self, req, timeout=None, context=None):
        import io
        import json
        import urllib.error

        self.bodies.append(json.loads(req.data))
        code, payload = self.replies.pop(0)
        raw = json.dumps(payload).encode()
        if code != 200:
            raise urllib.error.HTTPError(req.full_url, code, "err", {}, io.BytesIO(raw))
        return _Ctx(io.BytesIO(raw))


class _Ctx:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        return self.resp

    def __exit__(self, *a):
        return False


def _openai_compat(monkeypatch, replies):
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_BASE_URL", "https://proxy.test/v1")
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_API_KEY", "k")
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_MODEL", "some/model")
    monkeypatch.setattr(llm_extract.time, "sleep", lambda s: None)
    http = _FakeHTTP(replies)
    monkeypatch.setattr(llm_extract.urllib.request, "urlopen", http)
    return http


def _chat(text):
    return {"choices": [{"message": {"content": text}}]}


def test_openai_compat_degrades_format_on_400(monkeypatch):
    http = _openai_compat(monkeypatch, [
        (400, {"error": "json_schema unsupported"}),
        (200, _chat('{"brand": "HEAD", "soft_fields": []}')),
    ])
    assert llm_extract.call_model("…", provider="openai_compat")["brand"] == "HEAD"
    assert [b["response_format"]["type"] for b in http.bodies] == ["json_schema", "json_object"]
    assert http.bodies[0]["model"] == "some/model"


def test_openai_compat_retries_short_503(monkeypatch):
    http = _openai_compat(monkeypatch, [
        (503, {"error": {"retry_after_seconds": 6}}),
        (200, _chat('{"brand": null, "soft_fields": []}')),
    ])
    assert llm_extract.call_model("…", provider="openai_compat")["brand"] is None
    assert len(http.bodies) == 2


def test_openai_compat_needs_config(monkeypatch):
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_MODEL", None)
    with pytest.raises(ExtractionError, match="OPENAI_COMPAT"):
        llm_extract.call_model("…", provider="openai_compat")


# ---------------------------------------------------------------------------
# Schema and phrase sets
# ---------------------------------------------------------------------------


def test_schema_matches_intent_facts():
    facts_fields = {f.name for f in fields(IntentFacts)} - {"raw", "soft", "disputed", "lines",
                                                             "other", "other_optional"}
    assert set(SOFTENABLE_FIELDS) == facts_fields
    # deadline_weekday is not a fact but raw material: the code counts days to it (days_until)
    assert set(RESPONSE_SCHEMA["properties"]) == facts_fields | {
        "lines", "soft_fields", "deadline_weekday", "other_conditions"}
    assert set(RESPONSE_SCHEMA["required"]) == set(RESPONSE_SCHEMA["properties"])


@pytest.mark.parametrize("cases", [CASES, CASES_EN], ids=["ru", "en"])
def test_stress_sets_are_well_formed(cases):
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))
    facts_fields = {f.name for f in fields(IntentFacts)}
    for c in cases:
        assert set(c.expect or {}) <= facts_fields, c.id
        assert c.expect_soft <= set(SOFTENABLE_FIELDS), c.id


def test_ru_and_en_ids_do_not_collide():
    assert not {c.id for c in CASES} & {c.id for c in CASES_EN}


def test_openai_compat_retries_broken_response(monkeypatch):
    import http.client
    http_fake = _openai_compat(monkeypatch, [(200, _chat('{"brand": "HEAD", "soft_fields": []}'))])
    calls = {"n": 0}
    real = http_fake.__call__

    def flaky(req, timeout=None, context=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise http.client.IncompleteRead(b"partial")
        return real(req, timeout)

    monkeypatch.setattr(llm_extract.urllib.request, "urlopen", flaky)
    assert llm_extract.call_model("…", provider="openai_compat")["brand"] == "HEAD"
    assert calls["n"] == 2


def test_parse_json_takes_the_first_object():
    from asasked.llm_extract import _parse_json
    text = ('```json\n{"brand": "HEAD", "soft_fields": []}\n```\n\nWait, maybe '
            '{"brand": "Wilson"} instead.')
    assert _parse_json(text) == {"brand": "HEAD", "soft_fields": []}
    with pytest.raises(ExtractionError):
        _parse_json("no json here")


def test_days_until_counts_the_named_day_in_code():
    from asasked.coherence import days_until
    monday = "Monday, 2 November 2026"
    assert days_until("friday", monday) == 4
    assert days_until("saturday", monday) == 5
    assert days_until("monday", monday) == 7      # "by Monday" means next Monday
    assert days_until("friday", None) is None
    assert days_until(None, monday) is None


def test_named_weekday_overrides_the_models_count(monkeypatch):
    def fake(request, provider=None, today=None):
        return {"deadline_days": 5, "deadline_weekday": "wednesday"}
    monkeypatch.setattr(coherence, "call_model", fake)
    facts = coherence.extract_intent("by Wednesday", today="Monday, 2 November 2026")
    assert facts.deadline_days == 2
    # with no today's date there is nothing to count from: the model's estimate stays
    assert coherence.extract_intent("by Wednesday").deadline_days == 5


# ---------------------------------------------------------------------------
# Requirements with no field
# ---------------------------------------------------------------------------

GLUTEN_FREE = [("BAR-1", 1)]


def _one_item(_sku):
    return {"sku": "BAR-1", "name": "Energy bar, 12 pack", "brand": None, "color": None,
            "size_label": None, "level": None, "price_cents": 1200, "refundable": True,
            "ships_in_days": 2, "units": 1}


def test_requirement_without_a_field_is_asked_about_not_lost():
    facts = IntentFacts(other=("gluten-free",), other_optional=("gift-wrapped",))
    verdict = check_coherence(facts, GLUTEN_FREE, (0, 10**9), find=_one_item)
    assert not verdict.coherent
    assert [(f.code, f.severity) for f in verdict.findings] == [("other", BLOCK), ("other", WARN)]
    assert "gluten-free" in verdict.findings[0].text
    assert check_coherence(IntentFacts(), GLUTEN_FREE, (0, 10**9), find=_one_item).coherent


def test_extraction_splits_required_and_optional_conditions(monkeypatch):
    from asasked import coherence
    monkeypatch.setattr(coherence, "call_model", lambda r, p=None, today=None: {
        "other_conditions": [{"text": " gluten-free ", "optional": False},
                             {"text": "Gluten-free", "optional": True},
                             {"text": "gift-wrapped", "optional": True}]})
    facts = coherence.extract_intent("…")
    assert (facts.other, facts.other_optional) == (("gluten-free",), ("gift-wrapped",))
    monkeypatch.setattr(coherence, "call_model", lambda r, p=None, today=None: {
        "soft_fields": ["other_conditions"],
        "other_conditions": [{"text": "gift-wrapped", "optional": True}]})
    assert coherence.extract_intent("…").other_optional == ("gift-wrapped",)
    monkeypatch.setattr(coherence, "call_model", lambda r, p=None, today=None: {
        "other_conditions": ["gluten-free"]})
    with pytest.raises(ExtractionError):
        coherence.extract_intent("…")


def test_requirement_heard_by_one_model_only_warns():
    merged = merge_facts([IntentFacts(other=("gluten-free", "no nuts")), IntentFacts()])
    assert merged.other == ("gluten-free", "no nuts") and "other" in merged.disputed
    verdict = check_coherence(merged, GLUTEN_FREE, (0, 10**9), find=_one_item)
    assert verdict.coherent and {f.severity for f in verdict.findings} == {WARN}
    both = merge_facts([IntentFacts(other=("gluten-free",)),
                        IntentFacts(other=("Gluten free",), other_optional=("gift-wrapped",))])
    assert both.other == ("gluten-free",) and both.disputed == frozenset()
    assert both.other_optional == ("gift-wrapped",)
