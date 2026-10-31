"""Страж как MCP-сервер: агент спрашивает его перед оплатой.

Один инструмент — check_order(просьба, корзина). Ответ «proceed» — можно
платить; «ask» — не платить, показать человеку готовый вопрос и вызвать
проверку ещё раз вместе с его ответом (answers). Сервер ничего не помнит
между вызовами, кроме уже извлечённых фактов: одна и та же просьба не
отправляется моделям дважды.

MCP-сервер не может помешать агенту заплатить без проверки — он только
отвечает, когда спросят. И верит агенту на слово: просьбу и ответы человека
(answers) присылает сам агент, так что агент может пересказать просьбу
по-своему или ответить за человека. Это второе мнение для агента, который
его хочет, а не замок. Если оплата идёт через ваш код, надёжнее вызывать
Guard прямо в нём (см. guard.py): там ответ человека приходит из вашего кода
(guard.answer), а не от агента.

Запуск: asasked-mcp (stdio). Ключи моделей — из окружения, как у Guard.
"""

from __future__ import annotations

from collections import OrderedDict

from pydantic import BaseModel, Field

from mcp.server.mcpserver import MCPServer

from .guard import Guard, today_in_words

INSTRUCTIONS = """\
Before paying for anything on a person's behalf, call check_order with their
request in their own words and the cart you are about to pay for.
- "proceed": the cart matches the request; go ahead.
- "ask": do NOT pay. Show the person the question as it is, then call
  check_order again with the same request, the cart you now intend to buy,
  and every question and answer so far in "answers".
"notes" are things that could not be checked (the shop didn't say); mention
them to the person if they matter."""


class CartItem(BaseModel):
    name: str = Field(description="Product name as the shop shows it")
    brand: str | None = None
    color: str | None = Field(None, description="As the shop names it, e.g. 'Midnight Blue'")
    size: str | None = None
    price: float = Field(ge=0, description="Price of one item, in the same currency "
                                           "the person used for any limit")
    quantity: int = Field(1, ge=1)
    units: int = Field(1, description="Pieces per item, e.g. 6 for a 6-pack")
    returnable: bool | None = Field(None, description="Can it be returned; null if the shop doesn't say")
    delivery_days: int | None = Field(None, description="Days until it arrives")
    level: str | None = Field(None, description="beginner / intermediate / advanced, if the shop says")
    category: str | None = None


class CheckResult(BaseModel):
    decision: str = Field(description='"proceed": pay. "ask": don\'t pay, show the person the question')
    question: str | None = Field(None, description="For the person, as it is, when asking")
    reasons: list[str] = Field(description="What doesn't match the request")
    notes: list[str] = Field(description="What could not be checked or only roughly matches")


class Answer(BaseModel):
    question: str = Field(description="The question you showed the person")
    answer: str = Field(description="What the person replied, in their own words")


server = MCPServer(name="asasked", instructions=INSTRUCTIONS)

# Факты из просьбы извлекаются моделями — это медленно и платно; при
# повторной проверке исправленной корзины берутся готовые.
_guards: OrderedDict[tuple, Guard] = OrderedDict()
_KEEP = 64
# Как извлекать факты; None — моделями (подменяется в тестах).
EXTRACT = None


def _guard(request: str, answers: list[Answer], today: str) -> Guard:
    key = (request, tuple((a.question, a.answer) for a in answers), today)
    if key in _guards:
        _guards.move_to_end(key)
        return _guards[key]
    guard = Guard(request, today=today, extract=EXTRACT)
    for a in answers:
        guard.hear(a.question, a.answer)
    _guards[key] = guard
    while len(_guards) > _KEEP:
        _guards.popitem(last=False)
    return guard


@server.tool()
def check_order(request: str, cart: list[CartItem], answers: list[Answer] | None = None,
                today: str | None = None) -> CheckResult:
    """Check a cart against what the person asked for, before paying.

    request: the person's request in their own words, not your summary.
    cart: every item you are about to pay for.
    answers: questions you already asked the person and their replies.
    today: today's date in words ("Monday, 2 November 2026"), if the
    person's day differs from the server's; deadlines like "by Friday" count
    from it.

    Returns decision ("proceed" or "ask"), question (for the person, when
    asking), reasons and notes.
    """
    guard = _guard(request, answers or [], today or today_in_words())
    result = guard.check([item.model_dump() for item in cart])
    return CheckResult(**{k: result[k] for k in ("decision", "question", "reasons", "notes")})


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
