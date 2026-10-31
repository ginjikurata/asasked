"""Окно «свой запрос» на сайте: посетитель пишет просьбу, агент покупает в
песочнице-магазине, страж стоит перед оплатой.

    POST /try     {"request": "...", "visitor": "<хэш>"}  -> разбор одного прогона
    GET  /health  -> {"ok": true, "left_today": ...}

Устройство — как в бенчмарке, режим enforced:
- мандат «с потерями»: весь каталог до $300, детали просьбы в него не попадают;
- агент — одна дешёвая модель (LIVE_AGENT), страж — та же сверка двух моделей
  и детерминированный код;
- человек — сам посетитель. Как только агент спрашивает человека — по своей
  воле или потому что страж остановил оплату, — прогон замирает, посетитель
  видит вопрос и может ответить:

    POST /try     {"conversation": "<id>", "answer": "...", "visitor": "<хэш>"}

  Агент продолжает с того же места, с той же историей. Ответ на вопрос агента
  страж тоже слышит: факты извлекаются заново из просьбы вместе с ответом.
  Ответов не больше MAX_ANSWERS на просьбу; неотвеченный вопрос ждёт
  ANSWER_WAIT секунд, потом прогон закрывается.

Деньги считает сам сервис: не больше LIVE_PER_VISITOR просьб на посетителя
и LIVE_DAILY_CAP на всех за сутки (UTC), одновременно — LIVE_PARALLEL. Ответы
на вопросы — та же просьба, отдельно не считаются. Просьба, на которую агент
только ответил или переспросил человека (например, «привет»), попытку
посетителя не тратит — до FREE_PER_VISITOR таких в сутки. Общий дневной
потолок она тратит всё равно: модель вызывалась, и потолок должен быть
жёстким.
Слушает только localhost: снаружи к нему ходит маршрут сайта /api/try.
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import fields
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .coherence import IntentFacts, decide_before_purchase
from .guard import Guard
from .harness.agent import AGENTS, AgentResult, AgentSpec, run_agent
from .harness.tasks import TODAY
from .store.catalog_v1 import CATALOG
from .store.store import Mandate, Store

MAX_REQUEST_CHARS = 300
MAX_CENTS = 30_000
MAX_STEPS = 20
LIVE_AGENT = os.environ.get("LIVE_AGENT", "deepseek-v4-flash")
DAILY_CAP = int(os.environ.get("LIVE_DAILY_CAP", "200"))
PER_VISITOR = int(os.environ.get("LIVE_PER_VISITOR", "5"))
PARALLEL = int(os.environ.get("LIVE_PARALLEL", "3"))
FREE_PER_VISITOR = 10
MAX_ANSWERS = 3
MAX_ANSWER_CHARS = 300
ANSWER_WAIT = 600          # сколько вопрос ждёт ответа, секунд
RUN_WAIT = 290             # сколько ждём агента за один заход (маршрут сайта ждёт 300)
MAX_OPEN = 40              # разговоров, ждущих ответа, одновременно


class LimitError(Exception):
    """Отказ по лимиту: посетитель видит причину, денег не тратится."""

    def __init__(self, code: int, text: str):
        super().__init__(text)
        self.code = code


class _PersonAsked(Exception):
    """Вопрос человеку, на который ответа не будет: прогон на нём кончается."""


def mandate() -> Mandate:
    allow = tuple(p["sku"] for p in CATALOG if p["price_cents"] <= MAX_CENTS)
    return Mandate(prompt_summary="Buy tennis gear", allowlist=allow, quantity_cap=12,
                   amount_min_cents=100, amount_max_cents=MAX_CENTS)


# ---------------------------------------------------------------------------
# Что услышал страж — по-человечески
# ---------------------------------------------------------------------------

_LABELS = {
    "brand": "brand", "brand_not": "not", "model": "model", "color": "colour",
    "size_label": "size", "level": "level", "price_preference": "price",
    "explicit_max_cents": "at most", "quantity": "how many",
    "needs_refundable": "returns", "deadline_days": "arrives within",
}


def _value(name: str, value) -> str:
    if name == "explicit_max_cents":
        return f"${value / 100:,.2f}"
    if name == "needs_refundable":
        return "must be returnable"
    if name == "deadline_days":
        return f"{value} days"
    if name == "brand_not":
        return ", ".join(value)
    return str(value)


def _is_set(name: str, value) -> bool:
    return value not in (None, False, (), "")


def heard(facts: IntentFacts) -> list[dict]:
    """Факты стража строками «признак — значение»; мягкие и спорные помечены."""
    out = []
    for name, label in _LABELS.items():
        value = getattr(facts, name)
        if _is_set(name, value):
            out.append({"k": label, "v": _value(name, value),
                        "soft": name in facts.soft, "disputed": name in facts.disputed})
    for i, line in enumerate(facts.lines, 1):
        parts = [f"{_LABELS.get(k, k)} {_value(k, v)}" for k, v in line.items()
                 if _is_set(k, v)]
        out.append({"k": f"item {i}", "v": ", ".join(parts) or "one more item",
                    "soft": False, "disputed": "lines" in facts.disputed})
    for text in facts.other:
        out.append({"k": "also", "v": text, "soft": False, "disputed": "other" in facts.disputed})
    for text in facts.other_optional:
        out.append({"k": "also", "v": text, "soft": True, "disputed": False})
    return out


def _has_wishes(facts: IntentFacts) -> bool:
    return bool(facts.lines) or any(
        _is_set(f.name, getattr(facts, f.name)) for f in fields(IntentFacts)
        if f.name in _LABELS and f.name != "quantity")


# ---------------------------------------------------------------------------
# Журнал агента — коротко
# ---------------------------------------------------------------------------


def _item(store: Store, sku: str, qty: int = 1) -> dict:
    p = store.find(sku)
    return {"sku": sku, "name": p["name"], "qty": qty, "price": f"${p['price_cents'] / 100:,.2f}",
            "merchant": p["merchant_name"],
            "returns": "returnable" if p["refundable"] else "final sale",
            "delivery_days": p["ships_in_days"]}


def _steps(store: Store, call: dict) -> list[dict]:
    """Строки журнала для окна: что делал агент и что ему ответил человек."""
    if call["tool"] == "ask_user":
        return [{"k": "asked you", "v": call["args"].get("question", "")},
                {"k": "you", "v": call["result"].get("reply", "")}]
    text = _step(store, call)
    return [{"k": "agent", "v": text}] if text else []


def _step(store: Store, call: dict) -> str | None:
    tool, args, result = call["tool"], call["args"], call["result"]
    if "error" in result:
        return f"{tool}: {result['error']}"
    if tool == "search_products":
        return f"searched “{args.get('query', '')}” — {result.get('total', 0)} found"
    if tool == "get_product":
        return (f"opened {result['name']} · {result['merchant']} · {result['price']} · "
                f"{result['return_policy'].lower()} · {result['delivery_days']}d delivery")
    if tool == "add_to_cart":
        return f"added {store.find(args['sku'])['name']} ×{args.get('quantity', 1)}"
    if tool == "remove_from_cart":
        return f"removed {store.find(args['sku'])['name']}"
    if tool == "checkout":
        status = result.get("status")
        return {"needs_confirmation": "checkout → the guard stopped the payment",
                "placed": f"checkout → paid {result.get('total')}",
                "declined": "checkout → payment declined by Verifiable Intent"}.get(
                    status, f"checkout → {status}")
    return None  # view_cart и прочее в коротком журнале не нужно


def suggestions(store: Store, facts: IntentFacts, categories: set[str], m: Mandate,
                limit: int = 3) -> list[dict]:
    """Что страж пропустил бы без вопросов в тех же категориях — дешёвое сначала.

    Только для просьб об одном товаре: подбирать наборы из нескольких позиций
    здесь не нужно. Без названных признаков подходит всё — тогда и советовать
    нечего.
    """
    if facts.lines or not categories or not _has_wishes(facts):
        return []
    qty = facts.quantity or 1
    out = []
    for p in sorted(store.catalog, key=lambda p: (p["price_cents"], p["sku"])):
        if p["category"] not in categories or p["sku"] not in m.allowlist:
            continue
        units = p.get("units", 1)
        if qty % units:
            continue
        n = qty // units
        if p["stock"] < n:
            continue
        decision = decide_before_purchase(facts, [(p["sku"], n)],
                                          (m.amount_min_cents, m.amount_max_cents),
                                          m.allowlist, find=store.find)
        if decision.action == "proceed":
            out.append(_item(store, p["sku"], n))
            if len(out) == limit:
                break
    return out


# ---------------------------------------------------------------------------
# Разговор: одна просьба, агент, вопросы посетителю
# ---------------------------------------------------------------------------

class Conversation:
    """Одна просьба посетителя. Агент работает в своём потоке; вопрос человеку
    останавливает его, пока посетитель не ответит (или не уйдёт).

    run и extract подменяются в тестах (наивный агент, готовые факты).
    """

    def __init__(self, request: str, visitor: str = "", agent: AgentSpec | None = None,
                 extract: Callable[[str], IntentFacts] | None = None,
                 run: Callable[..., AgentResult] = run_agent):
        self.id = secrets.token_urlsafe(16)
        self.request, self.visitor = request, visitor
        self.spec = agent or AGENTS[LIVE_AGENT]
        self.store = Store()
        self.mandate = mandate()
        self.guard = Guard(request, today=TODAY, extract=extract)
        self.session = self.store.new_session(self.mandate, user_reply=self._person,
                                              guard=self.guard, guard_mode="enforced")
        self._run = run
        self._inbox: queue.Queue = queue.Queue()
        self._outbox: queue.Queue = queue.Queue()
        self.answers = 0
        self.waiting = False      # вопрос задан, ответа ждём
        self.done = False
        self.paid = True          # засчитана ли просьба в лимит посетителя
        self._blocks_answered = 0

    # ---- снаружи ----------------------------------------------------------

    def start(self) -> dict:
        threading.Thread(target=self._work, daemon=True).start()
        return self._next()

    def answer(self, text: str) -> dict:
        self.waiting = False
        self._inbox.put(text)
        return self._next()

    def close(self) -> None:
        """Посетитель ушёл или начал новую просьбу — ждать больше нечего."""
        if self.waiting:
            self.waiting = False
            self._inbox.put(None)

    def shopped(self) -> bool:
        """Делал ли агент что-то кроме вопросов человеку. Любой другой вызов,
        даже ошибочный, — это шаги модели, за которые заплачено."""
        return any(c["tool"] != "ask_user" for c in self.session.transcript)

    def _next(self) -> dict:
        try:
            return self._outbox.get(timeout=RUN_WAIT)
        except queue.Empty:
            raise LimitError(504, "The agent is taking too long. Try a simpler request.") from None

    # ---- в потоке агента --------------------------------------------------

    def _guard_pending(self) -> bool:
        """Сейчас спрашивают по просьбе стража: была остановка оплаты после
        последнего ответа человека."""
        blocks = sum(c["tool"] == "checkout"
                     and c["result"].get("status") == "needs_confirmation"
                     for c in self.session.transcript)
        return blocks > self._blocks_answered

    def _person(self, question: str) -> str:
        if self.answers >= MAX_ANSWERS:
            raise _PersonAsked(question)
        self.waiting = True
        self._outbox.put(self.report(asked=question, can_answer=True))
        try:
            answer = self._inbox.get(timeout=ANSWER_WAIT)
        except queue.Empty:
            answer = None
        self.waiting = False
        if answer is None:
            raise _PersonAsked(question)
        self.answers += 1
        if self._guard_pending():
            self._blocks_answered = sum(c["tool"] == "checkout"
                                        and c["result"].get("status") == "needs_confirmation"
                                        for c in self.session.transcript)
        else:
            self.guard.hear(question, answer)
        return answer

    def _work(self) -> None:
        result, asked = None, None
        try:
            result = self._run(self.spec, self.session, self.request, max_steps=MAX_STEPS)
        except _PersonAsked as e:
            asked = str(e)
        except Exception as e:  # noqa: BLE001 — посетитель видит сбой, сервис живёт
            result = AgentResult(stop="error", error=f"The run failed: {type(e).__name__}.")
        self.done = True
        self._outbox.put(self.report(result=result, asked=asked))

    def report(self, result: AgentResult | None = None, asked: str | None = None,
               can_answer: bool = False) -> dict:
        """Разбор для окна на сайте — на паузе (asked) или в конце (result)."""
        store, session, guard = self.store, self.session, self.guard
        facts = guard.facts()
        order = session.order
        last = guard.checks[-1] if guard.checks else None
        if asked is not None:
            outcome = "guard_asked" if self._guard_pending() else "agent_asked"
        elif result.stop == "error":
            outcome = "error"
        elif order is not None and order.placed:
            outcome = "bought"
        elif order is not None:
            outcome = "declined"
        else:
            outcome = "nothing"

        cart = order.purchase if order is not None else list(session.cart.items())
        categories = {store.find(sku)["category"] for sku, _ in cart}
        return {
            "request": self.request,
            "agent": self.spec.name,
            "today": TODAY,
            "conversation": self.id,
            "outcome": outcome,
            "question": asked,
            "can_answer": can_answer,
            "answers_left": MAX_ANSWERS - self.answers,
            "heard": heard(facts) if facts is not None else None,
            "heard_error": guard._error or None,
            "steps": [s for c in session.transcript for s in _steps(store, c)],
            "cart": [_item(store, sku, qty) for sku, qty in cart],
            "guard": None if last is None else {k: last[k] for k in ("decision", "reasons", "notes")},
            "vi": None if order is None else {k: order.vi.get(k) for k in
                                              ("chain_valid", "constraints_ok", "violations")},
            "suggestions": [] if facts is None else suggestions(store, facts, categories,
                                                                self.mandate),
            "final_text": result.final_text if result else "",
            "error": result.error if result and result.stop == "error" else "",
            "log": session.transcript,
        }


def try_request(request: str, agent: AgentSpec | None = None,
                extract: Callable[[str], IntentFacts] | None = None,
                answers: tuple[str, ...] = ()) -> dict:
    """Прогон целиком, без HTTP: answers — ответы на вопросы по порядку.

    Вопрос, на который ответов не хватило, заканчивает прогон и виден в разборе.
    """
    conv = Conversation(request, agent=agent, extract=extract)
    out = conv.start()
    for text in answers:
        if not out["can_answer"]:
            break
        out = conv.answer(text)
    if out["can_answer"]:
        conv.close()
        out = conv._next()
    return out


# ---------------------------------------------------------------------------
# Лимиты и HTTP
# ---------------------------------------------------------------------------


class Limits:
    def __init__(self, daily_cap: int = DAILY_CAP, per_visitor: int = PER_VISITOR,
                 parallel: int = PARALLEL, free_per_visitor: int = FREE_PER_VISITOR):
        self.daily_cap, self.per_visitor = daily_cap, per_visitor
        self.free_per_visitor = free_per_visitor
        self._slots = threading.BoundedSemaphore(parallel)
        self._lock = threading.Lock()
        self._day = ""
        self._total = 0
        self._visitors: Counter = Counter()
        self._free: Counter = Counter()

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._total = today, 0
            self._visitors.clear()
            self._free.clear()

    def left(self) -> int:
        with self._lock:
            self._roll()
            return max(0, self.daily_cap - self._total)

    def count(self, visitor: str) -> None:
        """Засчитывает просьбу до её начала: упавший прогон тоже стоил денег."""
        with self._lock:
            self._roll()
            if self._total >= self.daily_cap:
                raise LimitError(429, "The demo has used up today's budget. "
                                      "Try again tomorrow.")
            if self._visitors[visitor] >= self.per_visitor:
                raise LimitError(429, f"That's {self.per_visitor} requests from you today — "
                                      "the limit for this demo. Come back tomorrow.")
            self._total += 1
            self._visitors[visitor] += 1

    def refund(self, visitor: str) -> bool:
        """Возвращает посетителю попытку за просьбу без покупок — не больше
        free_per_visitor. Общий дневной счёт не уменьшается."""
        with self._lock:
            self._roll()
            if self._free[visitor] >= self.free_per_visitor or not self._visitors[visitor]:
                return False
            self._free[visitor] += 1
            self._visitors[visitor] -= 1
            return True

    def acquire(self) -> None:
        if not self._slots.acquire(blocking=False):
            raise LimitError(503, "Busy with other visitors' requests. "
                                  "Try again in a minute.")

    def take(self, visitor: str) -> None:
        self.count(visitor)
        try:
            self.acquire()
        except LimitError:
            with self._lock:
                self._total -= 1
                self._visitors[visitor] -= 1
            raise

    def release(self) -> None:
        self._slots.release()


class Desk:
    """Разговоры, ждущие ответа посетителя, и их счёт в лимитах."""

    def __init__(self, limits: Limits | None = None, **conversation_kw):
        self.limits = limits or Limits()
        self._kw = conversation_kw
        self._open: dict[str, Conversation] = {}
        self._lock = threading.Lock()

    def start(self, request: str, visitor: str) -> dict:
        with self._lock:
            self._prune()
            for conv in [c for c in self._open.values() if c.visitor == visitor]:
                conv.close()      # новая просьба закрывает старый разговор
                del self._open[conv.id]
            if len(self._open) >= MAX_OPEN:
                raise LimitError(503, "Busy with other visitors' requests. "
                                      "Try again in a minute.")
        self.limits.take(visitor)
        conv = Conversation(request, visitor, **self._kw)
        try:
            out = conv.start()
        finally:
            self.limits.release()
        return self._settle(conv, out)

    def answer(self, conversation: str, answer: str, visitor: str) -> dict:
        with self._lock:
            self._prune()
            conv = self._open.get(conversation)
            if conv is None or conv.visitor != visitor or not conv.waiting:
                raise LimitError(409, "This conversation has ended — send a new request.")
            conv.waiting = False  # второй ответ на тот же вопрос не пройдёт
        # Просьба, которую вернули как пустую, засчитывается, когда на неё ответили.
        try:
            if conv.paid:
                self.limits.acquire()
            else:
                self.limits.take(visitor)
        except LimitError:
            conv.waiting = True
            raise
        conv.paid = True
        try:
            out = conv.answer(answer)
        finally:
            self.limits.release()
        return self._settle(conv, out)

    def _settle(self, conv: Conversation, out: dict) -> dict:
        if conv.paid and not conv.shopped() and self.limits.refund(conv.visitor):
            conv.paid = False
        with self._lock:
            if out["can_answer"]:
                self._open[conv.id] = conv
            else:
                self._open.pop(conv.id, None)
        return out

    def _prune(self) -> None:
        for cid in [cid for cid, c in self._open.items() if c.done or not c.waiting]:
            del self._open[cid]


def check_request(data) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise LimitError(400, "Body must be a JSON object.")
    request = str(data.get("request") or "").strip()
    visitor = str(data.get("visitor") or "").strip()[:64] or "anonymous"
    if not request:
        raise LimitError(400, "Write what you'd like to buy.")
    if len(request) > MAX_REQUEST_CHARS:
        raise LimitError(400, f"Keep it under {MAX_REQUEST_CHARS} characters.")
    return request, visitor


def check_answer(data) -> tuple[str, str, str]:
    if not isinstance(data, dict):
        raise LimitError(400, "Body must be a JSON object.")
    conversation = str(data.get("conversation") or "").strip()[:64]
    answer = str(data.get("answer") or "").strip()
    visitor = str(data.get("visitor") or "").strip()[:64] or "anonymous"
    if not conversation:
        raise LimitError(400, "No conversation to answer.")
    if not answer:
        raise LimitError(400, "Write your answer.")
    if len(answer) > MAX_ANSWER_CHARS:
        raise LimitError(400, f"Keep it under {MAX_ANSWER_CHARS} characters.")
    return conversation, answer, visitor


def make_handler(desk: Desk):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                return self._send(200, {"ok": True, "left_today": desk.limits.left()})
            return self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/try":
                return self._send(404, {"error": "not found"})
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 4096)
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._send(400, {"error": "Body must be JSON."})
            try:
                if isinstance(data, dict) and "conversation" in data:
                    out = desk.answer(*check_answer(data))
                else:
                    out = desk.start(*check_request(data))
            except LimitError as e:
                return self._send(e.code, {"error": str(e)})
            except Exception as e:  # noqa: BLE001 — посетитель видит сбой, сервис живёт
                return self._send(500, {"error": f"The run failed: {type(e).__name__}."})
            return self._send(200, out)

        def log_message(self, fmt, *args):
            pass

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 3005, desk: Desk | None = None):
    return ThreadingHTTPServer((host, port), make_handler(desk or Desk()))
