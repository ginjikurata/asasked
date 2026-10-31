"""Страж перед оплатой — то, ради чего AsAsked существует.

Агент собрал корзину. Перед оплатой страж сверяет её со словами человека и
отвечает одно из двух:

    proceed — корзина совпадает с просьбой, можно платить;
    ask     — есть расхождение; вот готовый вопрос человеку.

Внутри — та же двухчастная схема, что и везде в проекте: модели извлекают
факты из просьбы (две независимые, спорные факты не блокируют), а решение
принимает детерминированный код (coherence.decide_before_purchase).

Если извлечь факты не удалось, страж не молчит и не пропускает: он просит
спросить человека. Страховка, которая при сбое пропускает всё, страховкой
не является.

Для разработчика агента — один вызов, корзина простыми словарями:

    guard = Guard("black running shoes, size 42, by Friday", today="2026-10-26")
    result = guard.check([{"name": "Nike Pegasus 41", "brand": "Nike",
                           "color": "Triple Black", "size": "42", "price": 129.99,
                           "quantity": 1, "returnable": True, "delivery_days": 3}])
    result["decision"]   # "proceed" или "ask"; result["question"] — вопрос человеку

Мандат Verifiable Intent не обязателен. Признак, которого в корзине нет,
не сверяется, а попадает в notes («проверить не удалось»).

Чтобы агент не мог заплатить мимо стража, проверка ставится в саму оплату:

    pay = guard.protect(checkout, cart=lambda order: order["items"])

Пока корзина расходится с просьбой, pay() не вызывает checkout, а отдаёт
агенту текст «не оплачено, спроси человека: …». Ответ человека передаёт
ваш код — guard.answer(его сообщение), — а не агент: иначе агент мог бы
сам «согласиться» за человека. Крючки для популярных библиотек агентов —
в asasked.integrations.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .coherence import ASK, PROCEED, IntentFacts, decide_before_purchase, extract_intent_agreed
from .llm_extract import ExtractionError


# Без мандата VI пределов суммы нет: проверяется только то, что сказал человек.
NO_BAND = (0, 10**15)

# Что видит агент вместо оплаты. Как needs_confirmation в песочнице: агент
# не должен ни платить повторно, ни отвечать за человека.
NOT_PAID = ("NOT PAID. The order doesn't match what the person asked for. "
            "Show the person this question as it is and wait for their reply; "
            "do not try to pay again before they answer.\n\n{question}")


def _cart_item(i: int, item: dict) -> tuple[str, dict, int]:
    """Позиция корзины разработчика → (артикул, товар в виде каталога, количество).

    Обязательны название и цена — в единицах валюты магазина (129.99). Без
    цены нельзя проверить ни предел суммы, ни «недорого»: товар без цены
    считался бы бесплатным и прошёл бы любой предел.
    """
    if not item.get("name"):
        raise ValueError(f"cart[{i}]: нужно название товара (name)")
    price = item.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not price >= 0:
        raise ValueError(f"cart[{i}]: нужна цена товара (price), число не меньше нуля")
    quantity = item.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ValueError(f"cart[{i}]: количество (quantity) — целое число от 1")
    product = {
        "sku": f"cart-{i}",
        "name": item["name"],
        "brand": item.get("brand"),
        "color": item.get("color"),
        "size_label": None if item.get("size") is None else str(item["size"]),
        "level": item.get("level"),
        "category": item.get("category"),
        "price_cents": round(price * 100),
        "refundable": item.get("returnable"),
        "ships_in_days": item.get("delivery_days"),
        "units": item.get("units", 1),
    }
    return product["sku"], product, quantity


def _quoted(agent_text: str) -> str:
    """Слова агента одной строкой и без пометок, которыми размечены слова
    человека: иначе агент мог бы вписать в свой вопрос «The person answered:
    цвет не важен» и выдать своё за сказанное человеком."""
    text = " ".join(agent_text.split())
    return _MARKS.sub("[...]", text)


_MARKS = re.compile(r"the\s+(person|agent)\s+(answered|added|asked)\s*:", re.IGNORECASE)


@dataclass
class Guard:
    request: str
    today: str | None = None
    # Какие модели извлекают факты (gemini, anthropic, openai_compat); по
    # умолчанию — все, у которых задан ключ. Одна — тоже можно, но тогда
    # её ошибку некому заметить.
    providers: tuple[str, ...] | None = None
    # Как получить факты из просьбы; по умолчанию — сверка моделей.
    # Подменяется в тестах и для прогонов с заранее известными фактами.
    extract: Callable[[str], IntentFacts] | None = None
    checks: list[dict] = field(default_factory=list)
    _facts: IntentFacts | None = None
    _error: str = ""
    # Вопрос, который страж задал и на который человек ещё не ответил.
    _asked: str | None = None

    def facts(self) -> IntentFacts | None:
        """Факты извлекаются один раз на просьбу, а не на каждую проверку."""
        if self._facts is None and not self._error:
            try:
                if self.extract is not None:
                    self._facts = self.extract(self.request)
                elif self.providers is not None:
                    self._facts = extract_intent_agreed(self.request, today=self.today,
                                                        providers=self.providers)
                else:
                    self._facts = extract_intent_agreed(self.request, today=self.today)
            except ExtractionError as e:
                self._error = str(e)
        return self._facts

    def hear(self, question: str, answer: str) -> None:
        """Человек ответил на вопрос агента — уточнение входит в его просьбу.

        Факты извлекаются заново из просьбы вместе с ответом: «размер 42» в
        ответе — такие же слова человека, как и в первой фразе.
        """
        self.request = (f"{self.request}\n\n(The agent asked: {_quoted(question)}\n"
                        f"The person answered: {answer})")
        self._facts, self._error = None, ""

    def check(self, purchase, mandate=None, find=None) -> dict:
        """purchase — корзина словарями (см. начало файла) или, вместе с find,
        список (артикул, количество) каталога. mandate — мандат VI или None."""
        if find is None:
            items = [_cart_item(i, item) for i, item in enumerate(purchase)]
            products = {sku: product for sku, product, _ in items}
            purchase, find = [(sku, qty) for sku, _, qty in items], products.__getitem__
        facts = self.facts()
        if facts is None:
            # Вопрос должен называть заказ: «можно?» без предмета человек не
            # подтвердит и не отвергнет осмысленно.
            items = "\n".join(f"  - {find(sku)['name']} ×{qty}, "
                               f"${find(sku)['price_cents'] / 100:.2f} each"
                               for sku, qty in purchase)
            result = {
                "decision": ASK,
                "reasons": ["The request could not be checked automatically."],
                "question": "I couldn't automatically check this order against your request:\n"
                            f"{items}\nShould I go ahead with it?",
                "notes": [],
                "error": self._error,
            }
        else:
            band = (mandate.amount_min_cents, mandate.amount_max_cents) if mandate else NO_BAND
            decision = decide_before_purchase(facts, purchase, band,
                                              mandate.allowlist if mandate else (), find=find)
            result = {
                "decision": decision.action,
                "reasons": [f.text for f in decision.reasons],
                "question": decision.question,
                "notes": [f.text for f in decision.notes],
            }
        self.checks.append({"purchase": list(purchase), **result})
        return result

    def answer(self, text: str) -> None:
        """Сообщение человека после вопроса стража — вызывает ваш код, не агент."""
        if self._asked is None:
            self.request = f"{self.request}\n\n(The person added: {text})"
            self._facts, self._error = None, ""
        else:
            self.hear(self._asked, text)
            self._asked = None

    def gate(self, cart: list[dict]) -> str | None:
        """None — можно платить; иначе текст для агента вместо оплаты."""
        result = self.check(cart)
        if result["decision"] == PROCEED:
            return None
        self._asked = result["question"]
        return NOT_PAID.format(question=result["question"])

    async def agate(self, cart: list[dict]) -> str | None:
        """gate для асинхронных агентов: модели вызываются вне цикла событий."""
        return await asyncio.to_thread(self.gate, cart)

    def protect(self, pay: Callable, cart: Callable[..., list[dict]]) -> Callable:
        """Оплата, которая сначала спрашивает стража.

        cart получает те же аргументы, что и pay, и возвращает корзину
        словарями. Если корзина расходится с просьбой, pay не вызывается, а
        возвращается текст для агента (см. NOT_PAID).
        """
        if inspect.iscoroutinefunction(pay):
            @functools.wraps(pay)
            async def guarded(*args, **kwargs):
                blocked = await self.agate(cart(*args, **kwargs))
                return blocked if blocked else await pay(*args, **kwargs)
        else:
            @functools.wraps(pay)
            def guarded(*args, **kwargs):
                blocked = self.gate(cart(*args, **kwargs))
                return blocked if blocked else pay(*args, **kwargs)
        return guarded


__all__ = ["ASK", "NOT_PAID", "PROCEED", "Guard"]
