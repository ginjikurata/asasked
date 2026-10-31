"""The guard before payment: what AsAsked exists for.

The agent has filled a cart. Before payment the guard checks it against the
person's words and answers one of two things:

    proceed: the cart matches the request, payment can go ahead;
    ask:     there is a mismatch; here is a ready question for the person.

Inside is the same two-part design as everywhere in the project: models
extract facts from the request (two independent ones; disputed facts do not
block), and deterministic code makes the decision
(coherence.decide_before_purchase).

If the facts cannot be extracted, the guard neither stays silent nor lets the
purchase through: it asks to check with the person. A safeguard that lets
everything through when it fails is no safeguard.

For an agent developer it is one call, with the cart as plain dicts:

    guard = Guard("black running shoes, size 42, by Friday", today="2026-10-26")
    result = guard.check([{"name": "Nike Pegasus 41", "brand": "Nike",
                           "color": "Triple Black", "size": "42", "price": 129.99,
                           "quantity": 1, "returnable": True, "delivery_days": 3}])
    result["decision"]   # "proceed" or "ask"; result["question"] is the question for the person

A Verifiable Intent mandate is optional. A feature the cart does not have is
not checked but goes into notes ("could not be checked").

So that the agent cannot pay around the guard, the check goes into payment itself:

    pay = guard.protect(checkout, cart=lambda order: order["items"])

While the cart differs from the request, pay() does not call checkout but
gives the agent the text "not paid, ask the person: ...". The person's answer
is passed on by your code, guard.answer(their message), not by the agent:
otherwise the agent could "agree" on the person's behalf. Hooks for popular
agent libraries are in asasked.integrations.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import functools
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .coherence import ASK, PROCEED, IntentFacts, decide_before_purchase, extract_intent_agreed
from .llm_extract import ExtractionError


# Without a VI mandate there are no amount limits: only what the person said is checked.
NO_BAND = (0, 10**15)

# What the agent sees instead of payment. Like needs_confirmation in the
# sandbox: the agent must neither pay again nor answer for the person.
NOT_PAID = ("NOT PAID. The order doesn't match what the person asked for. "
            "Show the person this question as it is and wait for their reply; "
            "do not try to pay again before they answer.\n\n{question}")


def _cart_item(i: int, item: dict) -> tuple[str, dict, int]:
    """A developer's cart line -> (sku, item in catalog form, quantity).

    Name and price are required, the price in the shop's currency units
    (129.99). Without a price neither the amount limit nor "cheap" can be
    checked: an item with no price would count as free and pass any limit.
    """
    if not item.get("name"):
        raise ValueError(f"cart[{i}]: the item needs a name (name)")
    price = item.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not price >= 0:
        raise ValueError(f"cart[{i}]: the item needs a price (price), a number not below zero")
    quantity = item.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ValueError(f"cart[{i}]: quantity must be an integer from 1")
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
    """The agent's words on one line and without the marks that label the
    person's words: otherwise the agent could write "The person answered:
    colour does not matter" into its question and pass its words off as theirs."""
    text = " ".join(agent_text.split())
    return _MARKS.sub("[...]", text)


_MARKS = re.compile(r"the\s+(person|agent)\s+(answered|added|asked)\s*:", re.IGNORECASE)


def today_in_words() -> str:
    """Today's date in words ("Saturday, 31 October 2026"): deadlines such
    as "by Friday" are counted from it."""
    d = dt.date.today()
    return f"{d:%A}, {d.day} {d:%B %Y}"


@dataclass
class Guard:
    request: str
    # Today's date in words; defaults to this machine's date. If the person's
    # day is different (time zone), pass it.
    today: str | None = None
    # Which models extract facts (gemini, anthropic, openai_compat); by
    # default, every one with a key set. One is fine too, but then nobody
    # notices its mistake.
    providers: tuple[str, ...] | None = None
    # How to get facts from the request; by default, model agreement.
    # Replaced in tests and for runs with facts known in advance.
    extract: Callable[[str], IntentFacts] | None = None
    checks: list[dict] = field(default_factory=list)
    _facts: IntentFacts | None = None
    _error: str = ""
    # The question the guard asked that the person has not answered yet.
    _asked: str | None = None

    def __post_init__(self) -> None:
        if self.today is None:
            self.today = today_in_words()

    def facts(self) -> IntentFacts | None:
        """Facts are extracted once per request, not on every check."""
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
        """The person answered the agent's question: the clarification joins their request.

        Facts are extracted again from the request together with the answer:
        "size 42" in an answer is as much the person's words as the first sentence.
        """
        self.request = (f"{self.request}\n\n(The agent asked: {_quoted(question)}\n"
                        f"The person answered: {answer})")
        self._facts, self._error = None, ""

    def check(self, purchase, mandate=None, find=None) -> dict:
        """purchase is the cart as dicts (see the top of this file) or, together
        with find, a list of catalog (sku, quantity). mandate is a VI mandate or None."""
        if find is None:
            items = [_cart_item(i, item) for i, item in enumerate(purchase)]
            products = {sku: product for sku, product, _ in items}
            purchase, find = [(sku, qty) for sku, _, qty in items], products.__getitem__
        facts = self.facts()
        if facts is None:
            # The question must name the order: the person cannot meaningfully
            # confirm or reject "may I?" with no subject.
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
        """The person's message after the guard's question: called by your code, not the agent."""
        if self._asked is None:
            self.request = f"{self.request}\n\n(The person added: {text})"
            self._facts, self._error = None, ""
        else:
            self.hear(self._asked, text)
            self._asked = None

    def gate(self, cart: list[dict]) -> str | None:
        """None: payment can go ahead; otherwise the text for the agent instead of payment."""
        result = self.check(cart)
        if result["decision"] == PROCEED:
            return None
        self._asked = result["question"]
        return NOT_PAID.format(question=result["question"])

    async def agate(self, cart: list[dict]) -> str | None:
        """gate for async agents: models are called outside the event loop."""
        return await asyncio.to_thread(self.gate, cart)

    def protect(self, pay: Callable, cart: Callable[..., list[dict]]) -> Callable:
        """Payment that asks the guard first.

        cart gets the same arguments as pay and returns the cart as dicts. If
        the cart differs from the request, pay is not called and the text for
        the agent is returned instead (see NOT_PAID).
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
