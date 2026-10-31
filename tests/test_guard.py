"""Страж перед оплатой, режимы магазина, наивный агент, исправления движка."""

import pytest

from asasked.coherence import IntentFacts, check_coherence
from asasked.guard import Guard
from asasked.harness.agent import AGENTS, run_agent
from asasked.harness.tasks import HARD, PILOT
from asasked.llm_extract import ExtractionError
from asasked.store.store import GUARD_TOOL, TOOLS, Store

PILOT_BY_ID = {t.id: t for t in PILOT}
HARD_BY_ID = {t.id: t for t in HARD}
REFUND = PILOT_BY_ID["pilot-refund-variant"]
RIGHT = "ASI-GELRESOLUTION9-42-BLA-COU"
FINAL_SALE = "ASI-GELRESOLUTION9-42-BLA-OUT"


def _vi_available():
    try:
        import asasked.vi_runner  # noqa: F401
    except SystemExit:
        return False
    return True


needs_vi = pytest.mark.skipif(not _vi_available(), reason="нет клона verifiable-intent")


def _guard(task=REFUND, calls=None):
    def extract(request):
        if calls is not None:
            calls.append(request)
        return task.facts
    return Guard(task.request, extract=extract)


# ---------------------------------------------------------------------------
# Страж
# ---------------------------------------------------------------------------


def test_guard_proceeds_on_right_cart_and_asks_on_wrong():
    store, calls = Store(), []
    guard = _guard(calls=calls)
    ok = guard.check([(RIGHT, 1)], REFUND.mandate(), store.find)
    bad = guard.check([(FINAL_SALE, 1)], REFUND.mandate(), store.find)
    assert ok["decision"] == "proceed" and not ok["reasons"]
    assert bad["decision"] == "ask"
    assert "final sale" in bad["reasons"][0] and bad["question"].endswith("Should I still go ahead?")
    assert len(calls) == 1          # факты извлекаются один раз на просьбу
    assert len(guard.checks) == 2


def test_guard_asks_when_extraction_fails():
    def broken(_request):
        raise ExtractionError("proxy down")
    guard = Guard("anything", extract=broken)
    result = guard.check([(RIGHT, 1)], REFUND.mandate(), Store().find)
    assert result["decision"] == "ask" and result["error"] == "proxy down"
    assert "ASICS Gel-Resolution 9, size 42, black ×1" in result["question"]


# ---------------------------------------------------------------------------
# Магазин: режимы
# ---------------------------------------------------------------------------


def test_tools_per_mode():
    store = Store()
    assert store.new_session(REFUND.mandate()).tools() == TOOLS
    advisory = store.new_session(REFUND.mandate(), guard=_guard(), guard_mode="advisory")
    assert advisory.tools() == TOOLS + [GUARD_TOOL]
    enforced = store.new_session(REFUND.mandate(), guard=_guard(), guard_mode="enforced")
    assert enforced.tools() == TOOLS
    with pytest.raises(ValueError):
        store.new_session(REFUND.mandate(), guard_mode="enforced")


def test_advisory_tool():
    session = Store().new_session(REFUND.mandate(), guard=_guard(), guard_mode="advisory")
    assert session.call("check_before_checkout", {"confirm": True}) == {"error": "The cart is empty."}
    session.call("add_to_cart", {"sku": FINAL_SALE})
    assert session.call("check_before_checkout", {"confirm": True})["decision"] == "ask"
    off = Store().new_session(REFUND.mandate())
    assert "error" in off.call("check_before_checkout", {"confirm": True})


@needs_vi
def test_enforced_blocks_until_the_person_is_asked():
    session = Store().new_session(REFUND.mandate(), guard=_guard(), guard_mode="enforced",
                                  user_reply="Fine, buy it anyway.")
    session.call("add_to_cart", {"sku": FINAL_SALE})
    blocked = session.call("checkout", {"confirm": True})
    assert blocked["status"] == "needs_confirmation" and session.order is None
    session.call("ask_user", {"question": blocked["question"]})
    assert session.call("checkout", {"confirm": True})["status"] == "placed"


@needs_vi
def test_enforced_rechecks_after_cart_change_and_passes_right_cart():
    session = Store().new_session(REFUND.mandate(), guard=_guard(), guard_mode="enforced")
    session.call("add_to_cart", {"sku": FINAL_SALE})
    assert session.call("checkout", {"confirm": True})["status"] == "needs_confirmation"
    session.call("ask_user", {"question": "?"})
    session.call("remove_from_cart", {"sku": FINAL_SALE})
    session.call("add_to_cart", {"sku": RIGHT})
    assert session.call("checkout", {"confirm": True})["status"] == "placed"
    assert [c["decision"] for c in session.guard.checks] == ["ask", "proceed"]


# ---------------------------------------------------------------------------
# Наивный агент
# ---------------------------------------------------------------------------


@needs_vi
@pytest.mark.parametrize("reply,bought", [("No, don't buy that.", False),
                                          ("Yes, go ahead.", True)])
def test_naive_agent_follows_the_persons_answer(reply, bought):
    session = Store().new_session(REFUND.mandate(), guard=_guard(), guard_mode="enforced",
                                  user_reply=reply)
    run_agent(AGENTS["naive"], session, REFUND.request)
    assert len(session.questions) == 1
    assert (session.order is not None and session.order.placed) is bought


@needs_vi
def test_naive_agent_without_guard_just_buys():
    session = Store().new_session(REFUND.mandate())
    result = run_agent(AGENTS["naive"], session, REFUND.request)
    assert result.stop == "done" and session.order.placed and not session.questions


# ---------------------------------------------------------------------------
# Исправления движка
# ---------------------------------------------------------------------------


def test_cheap_compares_within_the_named_model():
    task = HARD_BY_ID["hard-deadline-over-price"]
    m = task.mandate()
    verdict = check_coherence(task.facts, [("YON-EZONE98-414-BLU-ACE", 1)],
                              (m.amount_min_cents, m.amount_max_cents), m.allowlist,
                              find=Store().find)
    assert "price" not in {f.code for f in verdict.findings}


def test_wrong_model_is_flagged():
    verdict = check_coherence(IntentFacts(brand="Babolat", model="Pure Aero 98"),
                              [("BAB-PUREDRIVE-438-BLU-ACE", 1)], (100, 30000),
                              find=Store().find)
    assert [f.code for f in verdict.findings] == ["model"]


def test_quantity_counts_cans_not_packs():
    find = Store().find
    four_pack = [("PEN-CHAMPIONSHIP-12B-YEL-COU", 1)]
    assert check_coherence(IntentFacts(quantity=4), four_pack, (100, 6000), find=find).coherent
    two = check_coherence(IntentFacts(quantity=2), four_pack, (100, 6000), find=find)
    assert [f.code for f in two.findings] == ["quantity"]
    one_can = check_coherence(IntentFacts(quantity=4), [("PEN-CHAMPIONSHIP-3B-YEL-COU", 1)],
                              (100, 6000), find=find)
    assert [f.code for f in one_can.findings] == ["quantity"]   # меньше просьбы — тоже


# ---------------------------------------------------------------------------
# Несколько вариантов в одном заказе
# ---------------------------------------------------------------------------

TWO_PAIRS = IntentFacts(brand="Nike", model="Court Lite 4", color="white",
                        lines=({"size_label": "40", "quantity": 1},
                               {"size_label": "43", "quantity": 1}))
W40, W43 = "NIK-COURTLITE4-40-WHI-ACE", "NIK-COURTLITE4-43-WHI-ACE"


def _codes(facts, purchase):
    return sorted(f.code for f in check_coherence(facts, purchase, (100, 20000),
                                                  find=Store().find).findings)


def test_lines_match_each_variant_in_any_order():
    assert _codes(TWO_PAIRS, [(W43, 1), (W40, 1)]) == []


def test_lines_catch_missing_extra_and_wrong_quantity():
    assert _codes(TWO_PAIRS, [(W43, 1)]) == ["missing"]
    assert _codes(TWO_PAIRS, [(W43, 2)]) == ["missing", "quantity"]
    assert _codes(TWO_PAIRS, [(W40, 1), (W43, 1), ("NIK-COURTLITE4-44-WHI-ACE", 1)]) == ["extra"]
    assert _codes(TWO_PAIRS, [(W40, 1), ("NIK-COURTLITE4-44-WHI-ACE", 1)]) == ["size"]


def test_shared_facts_still_apply_to_every_line():
    grey40 = "NIK-COURTLITE4-40-GRE-ACE"
    assert _codes(TWO_PAIRS, [(grey40, 1), (W43, 1)]) == ["color"]


def test_disputed_lines_only_warn():
    from dataclasses import replace
    # модели разошлись в том, сколько вещей просили, — лишняя позиция только
    # предупреждает
    disputed = replace(TWO_PAIRS, disputed=frozenset({"lines", "line_count"}))
    extra = [(W40, 1), (W43, 1), ("NIK-COURTLITE4-44-WHI-ACE", 1)]
    verdict = check_coherence(disputed, extra, (100, 20000), find=Store().find)
    assert verdict.coherent and [f.code for f in verdict.findings] == ["extra"]
    # разошлись в размере строки — размер предупреждает
    cart = [(W40, 1), ("NIK-COURTLITE4-44-WHI-ACE", 1)]
    details = replace(TWO_PAIRS, disputed=frozenset({"lines", "lines.size_label"}))
    verdict = check_coherence(details, cart, (100, 20000), find=Store().find)
    assert verdict.coherent and [f.code for f in verdict.findings] == ["size"]
    # разошлись только в количестве — размер, который обе услышали, блокирует
    details = replace(TWO_PAIRS, disputed=frozenset({"lines", "lines.quantity"}))
    verdict = check_coherence(details, cart, (100, 20000), find=Store().find)
    assert not verdict.coherent


def test_merge_disputes_only_the_line_fields_that_differ():
    from asasked.coherence import merge_facts
    # случай из прогона: Gemini не назвал количество, модели обе услышали
    # Wilson Super Tour — подмена на Championship должна остановить заказ
    full = IntentFacts(lines=({"brand": "HEAD", "model": "Tour", "quantity": 1},
                              {"brand": "Wilson", "model": "Super Tour", "quantity": 1}))
    bare = IntentFacts(lines=({"brand": "Wilson", "model": "Super Tour"},
                              {"brand": "HEAD", "model": "Tour"}))
    merged = merge_facts([bare, full])
    assert merged.disputed == {"lines", "lines.quantity"}
    assert merged.lines == ({"brand": "Wilson", "model": "Super Tour", "quantity": 1},
                            {"brand": "HEAD", "model": "Tour", "quantity": 1})
    verdict = check_coherence(merged, [("HEA-TOUR-3B-YEL-ACE", 1),
                                       ("WIL-CHAMPIONSHIP-3B-YEL-ACE", 1)],
                              (100, 20000), find=Store().find)
    assert not verdict.coherent and "model" in [f.code for f in verdict.findings]


def test_missing_item_blocks_even_if_one_extractor_heard_it():
    from asasked.coherence import merge_facts
    # случай из прогона: Gemini слил «ракетку и банку мячей» в одну вещь,
    # агент купил только ракетку — страж пропустил заказ
    one = IntentFacts(brand="Nike", model="Court Lite 4", color="white", size_label="43")
    merged = merge_facts([one, TWO_PAIRS])
    assert "line_count" in merged.disputed and merged.lines == TWO_PAIRS.lines
    verdict = check_coherence(merged, [(W43, 1)], (100, 20000), find=Store().find)
    assert not verdict.coherent and "missing" in [f.code for f in verdict.findings]


def test_lines_disputed_in_details_still_block_missing_and_order_wide_facts():
    from dataclasses import replace
    # случай из прогона: число вещей обе модели услышали одинаково,
    # агент купил только одну — пропуск второй блокирует
    details = replace(TWO_PAIRS, disputed=frozenset({"lines"}))
    verdict = check_coherence(details, [(W43, 1)], (100, 20000), find=Store().find)
    assert not verdict.coherent and [f.code for f in verdict.findings] == ["missing"]
    # случай из прогона: «всё к пятнице» — условие на весь заказ, а не на строку
    late = replace(details, deadline_days=1)
    verdict = check_coherence(late, [(W40, 1), (W43, 1)], (100, 20000), find=Store().find)
    assert not verdict.coherent and {f.code for f in verdict.findings} == {"deadline"}


def test_extraction_parses_lines(monkeypatch):
    from asasked import coherence
    monkeypatch.setattr(coherence, "call_model", lambda r, p=None, today=None: {
        "brand": "Nike", "lines": [{"model": None, "color": None, "size_label": "40",
                                    "quantity": 1},
                                   {"model": None, "color": None, "size_label": "43",
                                    "quantity": 1}],
        "soft_fields": []})
    facts = coherence.extract_intent("…")
    assert facts.lines == ({"size_label": "40", "quantity": 1},
                           {"size_label": "43", "quantity": 1})
    monkeypatch.setattr(coherence, "call_model", lambda r, p=None, today=None: {
        "lines": [{"size_label": "40", "model": None, "color": None, "quantity": None}]})
    assert coherence.extract_intent("…").lines == ()      # одна строка — не варианты


def test_canonical_lines_make_two_extractors_agree():
    from asasked.coherence import canonical, merge_facts
    a = canonical(IntentFacts(quantity=2, lines=(
        {"model": "Court Lite 4", "color": "white", "size_label": "40", "quantity": 1},
        {"model": "Court Lite 4", "color": "white", "size_label": "43", "quantity": 1})))
    b = canonical(IntentFacts(model="Court Lite 4", color="white", lines=(
        {"size_label": "40", "quantity": 1}, {"size_label": "43", "quantity": 1})))
    merged = merge_facts([a, b])
    assert merged.disputed == frozenset()
    assert merged.lines == ({"size_label": "40", "quantity": 1},
                            {"size_label": "43", "quantity": 1})
    assert (merged.model, merged.color, merged.quantity) == ("Court Lite 4", "white", None)


def test_excluded_brand_is_flagged_and_merged_strictly():
    from asasked.coherence import merge_facts
    verdict = check_coherence(IntentFacts(brand_not=("Wilson",)),
                              [("WIL-ULTRAPOWER-438-BLU-COU", 1)], (100, 30000),
                              find=Store().find)
    assert [(f.code, f.severity) for f in verdict.findings] == [("brand-excluded", "block")]
    merged = merge_facts([IntentFacts(brand_not=("Wilson",)), IntentFacts()])
    assert merged.brand_not == ("Wilson",) and "brand_not" not in merged.disputed


# Разные вещи в одном заказе: у каждой свой бренд и свои условия
RACKET_AND_BALLS = IntentFacts(lines=(
    {"brand": "HEAD", "model": "Graphene Spark", "size_label": "4 3/8", "needs_refundable": True},
    {"brand": "Wilson", "model": "Championship", "quantity": 1, "deadline_days": 2}))
SPARK = "HEA-GRAPHENESPARK-438-RED-ACE"
CHAMP = "WIL-CHAMPIONSHIP-3B-YEL-ACE"


def test_lines_with_different_brands():
    assert _codes(RACKET_AND_BALLS, [(SPARK, 1), (CHAMP, 1)]) == []
    # бренд одной вещи не переносится на другую, а подмена внутри строки видна
    assert _codes(RACKET_AND_BALLS, [(SPARK, 1), ("PEN-CHAMPIONSHIP-3B-YEL-COU", 1)]) == [
        "brand", "deadline"]


def test_line_conditions_stay_on_their_line():
    # возврат просили для ракетки, срок — только для мячей: у невозвратной
    # ракетки с доставкой 4 дня расхождение одно — возврат
    assert _codes(RACKET_AND_BALLS, [("HEA-GRAPHENESPARK-438-RED-OUT", 1), (CHAMP, 1)]) == [
        "refund"]
    # мячи с долгой доставкой — расхождение по сроку только у мячей
    assert _codes(RACKET_AND_BALLS, [(SPARK, 1), ("WIL-CHAMPIONSHIP-12B-YEL-BAS", 1)]) == [
        "deadline", "quantity"]


def test_extraction_parses_brand_and_conditions_per_line(monkeypatch):
    from asasked import coherence
    monkeypatch.setattr(coherence, "call_model", lambda r, p=None, today=None: {
        "lines": [{"brand": "HEAD", "model": "Graphene Spark", "color": None,
                   "size_label": "4 3/8", "quantity": None, "needs_refundable": True,
                   "deadline_days": None, "deadline_weekday": None},
                  {"brand": "Wilson", "model": "Championship", "color": None,
                   "size_label": None, "quantity": 1, "needs_refundable": False,
                   "deadline_days": 5, "deadline_weekday": "wednesday"}],
        "soft_fields": []})
    facts = coherence.extract_intent("…", today="Monday, 26 October 2026")
    assert facts.lines == (
        {"brand": "HEAD", "model": "Graphene Spark", "size_label": "4 3/8",
         "needs_refundable": True},
        {"brand": "Wilson", "model": "Championship", "quantity": 1, "deadline_days": 2})


def test_canonical_lifts_shared_brand_and_refund():
    from asasked.coherence import canonical
    facts = canonical(IntentFacts(lines=(
        {"brand": "Nike", "size_label": "40", "needs_refundable": True},
        {"brand": "Nike", "size_label": "43", "needs_refundable": True})))
    assert (facts.brand, facts.needs_refundable) == ("Nike", True)
    assert facts.lines == ({"size_label": "40"}, {"size_label": "43"})


@needs_vi
def test_enforced_consent_does_not_carry_over_to_a_changed_cart():
    # человека спросили о прежней корзине; новую страж ещё не видел — и
    # любой вопрос агента не должен открывать оплату мимо стража
    session = Store().new_session(REFUND.mandate(), guard=_guard(), guard_mode="enforced",
                                  user_reply="Fine.")
    session.call("add_to_cart", {"sku": FINAL_SALE})
    assert session.call("checkout", {"confirm": True})["status"] == "needs_confirmation"
    session.call("ask_user", {"question": "?"})
    session.call("remove_from_cart", {"sku": FINAL_SALE})  # корзина изменилась: другой
    session.call("add_to_cart", {"sku": "ASI-GELRESOLUTION9-44-WHI-OUT"})  # цвет и размер
    session.call("ask_user", {"question": "Shall I?"})
    assert session.call("checkout", {"confirm": True})["status"] == "needs_confirmation"
    assert session.order is None


def test_too_many_lines_go_to_the_person():
    facts = IntentFacts(lines=tuple({"size_label": str(40 + i), "quantity": 1} for i in range(9)))
    found = check_coherence(facts, [(W40, 1)] * 9, (100, 10**9), find=Store().find)
    assert [f.code for f in found.findings] == ["lines"]
    assert found.findings[0].severity == "block"


def test_guard_knows_today_without_being_told():
    from asasked.guard import today_in_words
    assert Guard("shoes", extract=lambda _r: IntentFacts()).today == today_in_words()
    assert Guard("shoes", today="Monday, 2 November 2026").today == "Monday, 2 November 2026"
