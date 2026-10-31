"""Окно «свой запрос»: разбор прогона, подсказки и лимиты — без модели и сети."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from asasked.coherence import IntentFacts
from asasked.harness.agent import AGENTS, AgentResult
from asasked.live import (MAX_ANSWERS, Desk, Limits, LimitError, check_answer, check_request,
                          make_server, try_request)

from test_guard import FINAL_SALE, RIGHT, needs_vi

NAIVE = AGENTS["naive"]
REQUEST = "ASICS Gel-Resolution 9, black, size 42. I need to be able to return them."
FACTS = IntentFacts(brand="ASICS", model="Gel-Resolution 9", color="black", size_label="42",
                    needs_refundable=True)


def _run(request=REQUEST, facts=FACTS, answers=()):
    return try_request(request, agent=NAIVE, extract=lambda _r: facts, answers=answers)


def _asker(*questions, search=False):
    """Агент без магазина: задаёт вопросы по очереди и заканчивает
    (search — потом ищет по ответам, то есть уже ходит по магазину)."""
    def run(spec, session, request, max_steps):
        replies = [session.call("ask_user", {"question": q})["reply"] for q in questions]
        if search:
            session.call("search_products", {"query": " ".join(replies)})
        return AgentResult(stop="done", final_text=" / ".join(replies))
    return run


@needs_vi
def test_guard_stops_final_sale_and_the_visitor_sees_the_question():
    out = _run()
    assert out["outcome"] == "guard_asked"
    assert out["cart"][0]["sku"] == FINAL_SALE
    assert "final sale" in out["question"]
    assert out["guard"]["decision"] == "ask"
    assert "the guard stopped the payment" in out["steps"][-1]["v"]
    assert out["can_answer"] is False      # без ответов прогон закрыт
    assert {"k": "returns", "v": "must be returnable", "soft": False,
            "disputed": False} in out["heard"]


@needs_vi
def test_suggestions_are_what_the_guard_would_let_through():
    skus = [s["sku"] for s in _run()["suggestions"]]
    assert skus and skus[0] == RIGHT and FINAL_SALE not in skus


@needs_vi
def test_matching_purchase_is_paid():
    facts = IntentFacts(brand="ASICS", model="Gel-Resolution 9", color="black", size_label="42")
    out = _run("ASICS Gel-Resolution 9, black, size 42", facts)
    assert out["outcome"] == "bought"
    assert out["vi"]["chain_valid"] and out["vi"]["constraints_ok"]


@needs_vi
def test_visitor_answers_the_guard_and_the_order_goes_through():
    out = _run(answers=("Yes, final sale is fine, go ahead",))
    assert out["outcome"] == "bought"
    assert {"k": "you", "v": "Yes, final sale is fine, go ahead"} in out["steps"]
    assert out["answers_left"] == MAX_ANSWERS - 1


@needs_vi
def test_visitor_says_no_and_nothing_is_bought():
    out = _run(answers=("No, I need to be able to return them",))
    assert out["outcome"] == "nothing" and out["vi"] is None


def test_dialogue_goes_on_and_ends_when_answers_run_out():
    desk = Desk(Limits(), run=_asker("Which size?", "Which colour?", "Which brand?", "Sure?"),
                extract=lambda text: IntentFacts(size_label="42") if "42" in text else IntentFacts())
    out = desk.start("shoes", "v")
    out = desk.answer(out["conversation"], "42", "v")
    assert out["question"] == "Which colour?"
    assert {"k": "size", "v": "42", "soft": False, "disputed": False} in out["heard"]
    with pytest.raises(LimitError):
        desk.answer(out["conversation"], "black", "someone else")
    out = desk.answer(out["conversation"], "black", "v")
    out = desk.answer(out["conversation"], "Babolat", "v")
    assert out["question"] == "Sure?" and not out["can_answer"] and out["answers_left"] == 0
    with pytest.raises(LimitError) as ended:
        desk.answer(out["conversation"], "yes", "v")
    assert ended.value.code == 409


def test_greeting_does_not_use_up_an_attempt_but_answering_does():
    limits = Limits(daily_cap=10, per_visitor=1)
    desk = Desk(limits, run=_asker("What would you like to buy?", search=True),
                extract=lambda _t: IntentFacts())
    first = desk.start("hi", "v")
    second = desk.start("hello", "v")          # первая не засчитана
    assert limits.left() == 10
    with pytest.raises(LimitError):
        desk.answer(first["conversation"], "balls", "v")   # закрыта новой просьбой
    desk.answer(second["conversation"], "balls", "v")      # ответ — уже просьба
    assert limits.left() == 9
    with pytest.raises(LimitError) as spent:
        desk.start("hi again", "v")
    assert spent.value.code == 429


def test_nothing_found_and_no_wishes_means_no_suggestions():
    out = _run("a pizza margherita", IntentFacts())
    assert out["outcome"] == "nothing" and out["cart"] == [] and out["suggestions"] == []


def test_request_checks():
    assert check_request({"request": "  balls  ", "visitor": "v"}) == ("balls", "v")
    for bad in ({}, {"request": " "}, {"request": "x" * 301}, []):
        with pytest.raises(LimitError):
            check_request(bad)
    assert check_answer({"conversation": "c", "answer": " 42 ", "visitor": "v"}) == ("c", "42", "v")
    for bad in ({"answer": "42"}, {"conversation": "c", "answer": ""},
                {"conversation": "c", "answer": "x" * 301}):
        with pytest.raises(LimitError):
            check_answer(bad)


def test_limits_per_visitor_daily_and_parallel():
    limits = Limits(daily_cap=3, per_visitor=2, parallel=1)
    limits.take("a")
    with pytest.raises(LimitError) as busy:
        limits.take("b")          # одно место — занято
    assert busy.value.code == 503
    limits.release()
    limits.take("a")
    limits.release()
    with pytest.raises(LimitError):
        limits.take("a")          # у «a» кончились
    limits.take("b")
    limits.release()
    with pytest.raises(LimitError):
        limits.take("c")          # кончился общий дневной потолок
    assert limits.left() == 0


def test_refund_is_capped():
    limits = Limits(daily_cap=10, per_visitor=5, free_per_visitor=1)
    limits.count("a")
    assert limits.refund("a") and limits.left() == 10
    limits.count("a")
    assert not limits.refund("a") and limits.left() == 9
    assert not limits.refund("nobody")


def test_http_counts_runs_and_answers_json():
    server = make_server(port=0, desk=Desk(Limits(daily_cap=1, per_visitor=5), agent=NAIVE,
                                           extract=lambda _t: IntentFacts()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"

    def post(body):
        req = urllib.request.Request(f"{url}/try", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    try:
        code, out = post({"request": "a pizza margherita", "visitor": "v"})
        assert code == 200 and out["outcome"] == "nothing"
        assert post({"conversation": out["conversation"], "answer": "x", "visitor": "v"})[0] == 409
        assert post({"request": "balls", "visitor": "w"})[0] == 429
        assert post({"request": ""})[0] == 400
        with urllib.request.urlopen(f"{url}/health") as r:
            assert json.load(r) == {"ok": True, "left_today": 0}
    finally:
        server.shutdown()
