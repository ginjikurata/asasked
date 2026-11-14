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
    # an item that renews and charges again also gets
    # "recurring": {"every": "month", "price": 12.99}
    result["decision"]   # "proceed" or "ask"; result["question"] is the question for the person

An on-chain payment can be checked too, before the agent signs it:
guard.check(cart, payment={"token": "USDC", "amount": 129.99, "to": ...,
"merchant": ..., "rate": 1.0}) also compares the token, network, recipient,
amount and swap slippage with the request and the cart (see asasked.payment).
A payment to an address that is not the shop's, for more than the order, or
through a swap that may lose too much gets a third decision, "refuse": no
answer of the person's approves it (result["refused"]), the payment itself has
to change. A cart question, if there is one, still comes with it. The shop's
address is whatever the shop's payment request says, unless it is pinned:
Guard(request, payees=[...]), or payees in the person's signed mandate. Then
a payment to any other address is refused, even if the request names it.

A Verifiable Intent mandate is optional. A feature the cart does not have is
not checked but goes into notes ("could not be checked"). With the person's
signed L2 mandate, Guard.from_mandate(l2, user_jwk) takes the request from it
rather than from the agent; with claimed=, the agent's account of the request,
it also notes where that account differs from what the person signed.

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

from .coherence import (ASK, BLOCK, PROCEED, Decision, IntentFacts, check_agreed_renewals,
                        decide_before_purchase, renewal_terms,
                        extract_intent_agreed, retelling_differences)
from .llm_extract import ExtractionError
from .mandate import payees_from_mandate, request_from_mandate
from .payment import check_payment, parse_payment, refused


# Without a VI mandate there are no amount limits: only what the person said is checked.
NO_BAND = (0, 10**15)

# The third decision, for a payment no answer of the person's can approve.
REFUSE = "refuse"

# What the agent sees instead of payment. Like needs_confirmation in the
# sandbox: the agent must neither pay again nor answer for the person.
NOT_PAID = ("NOT PAID. The order doesn't match what the person asked for. "
            "Show the person this question as it is and wait for their reply; "
            "do not try to pay again before they answer.\n\n{question}")

# A refused payment: asking the person would not help, and a "yes" would not
# change the answer, so the agent is told to change the payment instead.
REFUSED = ("NOT PAID. This payment can't be made as it is, and no answer from the person "
           "can approve it:\n{reasons}\nChange the payment itself: pay the address on the "
           "shop's invoice, the amount of the order, with any swap kept within the allowed "
           "slippage and guaranteed to cover the amount. Do not ask the person to approve "
           "this payment.")
# Said after REFUSED when the cart needs the person's answer as well.
UNCHECKED = "I couldn't automatically check this order against your request:"
ALSO_ASK = ("\n\nThe order also doesn't match what the person asked for. Show the person "
            "this question as it is and wait for their reply before paying:\n\n{question}")


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
        "recurring": _recurring(i, item.get("recurring")),
    }
    return product["sku"], product, quantity


def _recurring(i: int, value) -> dict | None:
    """A cart line's "recurring" -> {"every", "price_cents"} or None.

    {"every": "month", "price": 12.99}: the item renews and charges again;
    "price" is what each renewal costs, if not the item's price (a free trial
    that becomes $12.99 a month). None or false: a one-time purchase, or the
    shop doesn't say.
    """
    if value is None or value is False:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("every"), str) \
            or not value["every"].strip():
        raise ValueError(f'cart[{i}]: recurring is {{"every": "month", "price": 12.99}} '
                         "(price optional) or null")
    price = value.get("price")
    if price is not None and (isinstance(price, bool) or not isinstance(price, (int, float))
                              or not price >= 0):
        raise ValueError(f"cart[{i}]: recurring price must be a number not below zero")
    return {"every": value["every"].strip(),
            "price_cents": None if price is None else round(price * 100)}


def _renews(product: dict) -> str:
    recurring = product.get("recurring")
    if not recurring:
        return ""
    cents = recurring.get("price_cents")
    cents = product["price_cents"] if cents is None else cents
    return f", then ${cents / 100:.2f} every {recurring['every']}"


def _quoted(agent_text: str) -> str:
    """The agent's words on one line and without the marks that label the
    person's words: otherwise the agent could write "The person answered:
    colour does not matter" into its question and pass its words off as theirs."""
    text = " ".join(agent_text.split())
    return _MARKS.sub("[...]", text)


_MARKS = re.compile(r"the\s+(person|agent)\s+(answered|added|asked)\s*:", re.IGNORECASE)

# A bare "yes" read by plain code, for when the models that read answers are
# down. Only an answer made of these words and nothing else: "yes, but in
# black" or "no" is not one, and the person is asked again.
_YES = {"yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "confirmed", "approve",
        "approved", "да", "ага", "ок", "окей", "хорошо", "конечно", "давай",
        "подтверждаю", "согласен", "согласна"}
_FILLER = {"go", "ahead", "please", "fine", "buy", "pay", "it", "that", "is", "do",
           "покупай", "оплачивай", "плати", "бери", "можно", "пожалуйста", "оформляй"}


def plain_yes(answer: str) -> bool:
    words = re.findall(r"[^\W\d_]+", answer.lower())
    return (bool(words) and len(words) <= 6 and any(w in _YES for w in words)
            and all(w in _YES or w in _FILLER for w in words))


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
    # The agent's own account of the request, when the request itself comes
    # from the signed mandate (from_mandate): the two are compared once.
    claimed: str | None = None
    # Payment addresses the person approved (or their signed mandate names):
    # an on-chain payment may go only there, whatever the shop's payment
    # request says. Empty: the shop's address is taken from that request.
    payees: tuple[str, ...] = ()
    _signed: str = ""
    _retold: list | None = None
    _facts: IntentFacts | None = None
    _error: str = ""
    # The question the guard asked that the person has not answered yet.
    _asked: str | None = None
    # With no facts, the order as last put to the person, and the order they
    # said a plain yes to: that order, and only that one, may then be paid.
    _unchecked_shown: str | None = None
    _unchecked_approved: str | None = None
    # Subscriptions in the last order checked, and those in orders the person
    # was asked about and answered: sku -> (every, cents per renewal). An
    # answer agrees to the subscription as it was shown, not to any other.
    _offered: dict = field(default_factory=dict)
    _agreed: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.today is None:
            self.today = today_in_words()
        if isinstance(self.payees, str):
            self.payees = (self.payees,)
        self.payees = tuple(p.strip() for p in self.payees if isinstance(p, str) and p.strip())

    @classmethod
    def from_mandate(cls, l2: str, user_jwk: dict, claimed: str | None = None,
                     **kwargs) -> Guard:
        """The guard for the request the person signed, not the agent's retelling of it.

        l2 is the person's L2 mandate as presented, user_jwk their public key
        from the verified L1 (see asasked.mandate). A bad signature raises
        MandateError. A mandate with no request in it cannot be checked, so
        every check asks the person, as when extraction fails.

        claimed is the request as the agent tells it, if it does. The cart is
        checked against the signed request either way; where the agent's
        version says something else (another colour, no returns), the check
        adds a note: the agent is shopping for something the person did not sign.

        Payees in the mandate with a CAIP-10 id ("solana:<chain>:<address>")
        become the guard's payees, unless payees= is passed.
        """
        request = request_from_mandate(l2, user_jwk)
        kwargs.setdefault("payees", payees_from_mandate(l2, user_jwk))
        guard = cls(request or "", claimed=claimed, **kwargs)
        guard._signed = request or ""
        if request is None:
            guard._error = "The mandate carries no request from the person (prompt_summary)."
        return guard

    def _extract(self, text: str) -> IntentFacts:
        if self.extract is not None:
            return self.extract(text)
        if self.providers is not None:
            return extract_intent_agreed(text, today=self.today, providers=self.providers)
        return extract_intent_agreed(text, today=self.today)

    def facts(self) -> IntentFacts | None:
        """Facts are extracted once per request, not on every check."""
        if self._facts is None and not self._error:
            try:
                self._facts = self._extract(self.request)
            except ExtractionError as e:
                self._error = str(e)
        return self._facts

    def retold(self) -> list:
        """Where the agent's account (claimed) differs from the signed request.

        Compared once, against the request as signed, before the person's
        later answers: those are new words, not a retelling.
        """
        if self._retold is None:
            self._retold = []
            same = " ".join((self.claimed or "").split()) == " ".join(self._signed.split())
            if self.claimed and self._signed and not same:
                try:
                    # Before any answer the request is the signed one: its facts are at hand.
                    signed = self._facts if self.request == self._signed and self._facts \
                        else self._extract(self._signed)
                    claimed = self._extract(self.claimed)
                except ExtractionError as e:
                    self._retold = ["Could not compare the agent's account of the request "
                                    f"with the one you signed: {e}"]
                else:
                    self._retold = [f.text for f in retelling_differences(signed, claimed)]
        return self._retold

    def hear(self, question: str, answer: str) -> None:
        """The person answered the agent's question: the clarification joins their request.

        Facts are extracted again from the request together with the answer:
        "size 42" in an answer is as much the person's words as the first sentence.
        """
        self.request = (f"{self.request}\n\n(The agent asked: {_quoted(question)}\n"
                        f"The person answered: {answer})")
        self._facts, self._error = None, ""
        # Only ever stricter: a "no" leaves wants_recurring false, and the
        # terms seen stop a different subscription slipping in after a "yes".
        self._agreed = {**self._agreed, **self._offered}

    def check(self, purchase, mandate=None, find=None, payment=None,
              spent_before: float = 0) -> dict:
        """purchase is the cart as dicts (see the top of this file) or, together
        with find, a list of catalog (sku, quantity). mandate is a VI mandate or None.
        payment is the on-chain payment the agent is about to sign (see
        asasked.payment), or None when it pays some other way. spent_before is
        what was already paid earlier for this same request, in the cart's
        currency (an agent paying an API call by call): the person's limit
        counts it as well as this cart."""
        if isinstance(spent_before, bool) or not isinstance(spent_before, (int, float)) \
                or not spent_before >= 0:
            raise ValueError("spent_before must be a number not below zero")
        # Not rounded to cents: a thousand payments of a tenth of a cent are a dollar.
        earlier = spent_before * 100
        if find is None:
            items = [_cart_item(i, item) for i, item in enumerate(purchase)]
            products = {sku: product for sku, product, _ in items}
            purchase, find = [(sku, qty) for sku, _, qty in items], products.__getitem__
        payment = parse_payment(payment)
        total = sum(find(sku)["price_cents"] * qty for sku, qty in purchase)
        changed = check_agreed_renewals(self._agreed, purchase, find)
        self._offered = renewal_terms(purchase, find)
        facts = self.facts()
        if facts is None:
            # Recipient, amount and slippage need no facts: they are refused
            # all the same (with no facts, every payment block is a refusal).
            refusals = [f for f in check_payment(IntentFacts(), payment, total,
                                                 payees=self.payees) if refused(f)]
            # The question must name the order: the person cannot meaningfully
            # confirm or reject "may I?" with no subject.
            items = "\n".join(f"  - {find(sku)['name']} ×{qty}, "
                               f"${find(sku)['price_cents'] / 100:.2f} each{_renews(find(sku))}"
                               for sku, qty in purchase)
            self._unchecked_shown = items
            if items == self._unchecked_approved and not refusals and not changed:
                # Otherwise a "yes" is asked about again for as long as the
                # models are down, and the order is never paid.
                result = {
                    "decision": PROCEED, "reasons": [], "refused": [], "question": None,
                    "notes": ["Not checked against the request automatically: the person "
                              "approved this order as it was shown to them."],
                    "error": self._error,
                }
                self.checks.append({"purchase": list(purchase), **result,
                                    **({"payment": payment} if payment else {})})
                return result
            result = {
                "decision": REFUSE if refusals else ASK,
                "reasons": ["The request could not be checked automatically."]
                           + [f.text for f in changed + refusals],
                "refused": [f.text for f in refusals],
                "question": f"{UNCHECKED}\n{items}\nShould I go ahead with it?",
                "notes": [],
                "error": self._error,
            }
        else:
            band = (mandate.amount_min_cents, mandate.amount_max_cents) if mandate else NO_BAND
            decision = decide_before_purchase(facts, purchase, band,
                                              mandate.allowlist if mandate else (), find=find,
                                              spent_before_cents=earlier)
            if changed:
                # The same interval change can come from the person's words and from
                # the cart they approved; say it once, in the "you agreed" form.
                tails = [c.text.split("this one ", 1)[1] for c in changed
                         if "this one " in c.text]
                kept = [f for f in decision.reasons
                        if not (f.code == "recurring-interval"
                                and any(f.text.endswith(t) for t in tails))]
                decision = Decision(action=ASK, reasons=kept + changed,
                                    notes=decision.notes)
            over = any(f.code == "explicit-max" for f in decision.reasons + decision.notes)
            paying = check_payment(facts, payment, total, over_limit=over,
                                   payees=self.payees, spent_before_cents=earlier)
            refusals = [f for f in paying if refused(f)]
            if paying:
                # The person is asked only what their answer can settle.
                reasons = decision.reasons + [f for f in paying
                                              if f.severity == BLOCK and not refused(f)]
                decision = Decision(action=ASK if reasons else PROCEED, reasons=reasons,
                                    notes=decision.notes + [f for f in paying
                                                            if f.severity != BLOCK])
            result = {
                "decision": REFUSE if refusals else decision.action,
                "reasons": [f.text for f in decision.reasons + refusals],
                "refused": [f.text for f in refusals],
                "question": decision.question,
                "notes": [f.text for f in decision.notes] + self.retold(),
            }
        self.checks.append({"purchase": list(purchase), **result,
                            **({"payment": payment} if payment else {})})
        return result

    def answer(self, text: str) -> None:
        """The person's message after the guard's question: called by your code, not the agent."""
        if self._asked is None:
            self.request = f"{self.request}\n\n(The person added: {text})"
            self._facts, self._error = None, ""
        else:
            if self._asked.startswith(UNCHECKED) and plain_yes(text):
                self._unchecked_approved = self._unchecked_shown
            self.hear(self._asked, text)
            self._asked = None

    def gate(self, cart: list[dict], payment: dict | None = None,
             spent_before: float = 0) -> str | None:
        """None: payment can go ahead; otherwise the text for the agent instead of payment."""
        result = self.check(cart, payment=payment, spent_before=spent_before)
        if result["decision"] == PROCEED:
            return None
        self._asked = result["question"]
        if result["decision"] == REFUSE:
            reasons = "\n".join(f"  - {text}" for text in result["refused"])
            told = REFUSED.format(reasons=reasons)
            return told + ALSO_ASK.format(question=self._asked) if self._asked else told
        return NOT_PAID.format(question=result["question"])

    async def agate(self, cart: list[dict], payment: dict | None = None,
                    spent_before: float = 0) -> str | None:
        """gate for async agents: models are called outside the event loop."""
        return await asyncio.to_thread(self.gate, cart, payment, spent_before)

    def protect(self, pay: Callable, cart: Callable[..., list[dict]],
                payment: Callable[..., dict | None] | None = None) -> Callable:
        """Payment that asks the guard first.

        cart gets the same arguments as pay and returns the cart as dicts. If
        the cart differs from the request, pay is not called and the text for
        the agent is returned instead (see NOT_PAID, and REFUSED for a payment
        no answer can approve). payment, if given, gets
        the same arguments too and returns the on-chain payment about to be
        signed (see asasked.payment), checked together with the cart.
        """
        def paying(*args, **kwargs):
            return payment(*args, **kwargs) if payment else None

        if inspect.iscoroutinefunction(pay):
            @functools.wraps(pay)
            async def guarded(*args, **kwargs):
                blocked = await self.agate(cart(*args, **kwargs), paying(*args, **kwargs))
                return blocked if blocked else await pay(*args, **kwargs)
        else:
            @functools.wraps(pay)
            def guarded(*args, **kwargs):
                blocked = self.gate(cart(*args, **kwargs), paying(*args, **kwargs))
                return blocked if blocked else pay(*args, **kwargs)
        return guarded


__all__ = ["ASK", "NOT_PAID", "PROCEED", "REFUSE", "REFUSED", "Guard"]
