"""The guard as an MCP server: the agent asks it before paying.

One tool, check_order(request, cart). The answer "proceed" means payment can
go ahead; "ask" means do not pay, show the person the ready question and call
the check again together with their answer (answers); "refuse" means the
on-chain payment itself is wrong (another address, more than the order, a
swap that may lose too much) and must change, whatever the person answers.
The server remembers
nothing between calls except facts already extracted: the same request is not
sent to the models twice.

An MCP server cannot stop an agent from paying without a check: it only
answers when asked. And it takes the agent at its word: the request and the
person's answers are sent by the agent itself, so the agent may retell the
request its own way or answer for the person. It is a second opinion for an
agent that wants one, not a lock. If payment goes through your own code, it is
safer to call Guard right there (see guard.py): there the person's answer
comes from your code (guard.answer), not from the agent.

Run: asasked-mcp (stdio). Model keys come from the environment, as for Guard.
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
- "refuse": do NOT pay, and do not ask the person to approve this payment:
  no answer can. Change the payment as "refused" says (the shop's address,
  the order's amount, a tighter swap) and check again. If there is also a
  question, show it to the person as with "ask".
"notes" are things that could not be checked (the shop didn't say); mention
them to the person if they matter.
When paying on-chain, also pass "payment": the transaction you are about to
sign, with the shop's address and rate and any swap quote exactly as the shop
and the swap provider returned them."""


class Recurring(BaseModel):
    every: str = Field(description="How often it charges again: 'month', 'year', '4 weeks'")
    price: float | None = Field(None, ge=0, description=(
        "What each renewal costs, if not the item's price (a free trial that "
        "becomes 12.99 a month: price 0, recurring price 12.99)"))


class CartItem(BaseModel):
    name: str = Field(description="Product name as the shop shows it")
    brand: str | None = None
    color: str | None = Field(None, description="As the shop names it, e.g. 'Midnight Blue'")
    size: str | None = None
    price: float = Field(ge=0, description="Price of one item, in the same currency "
                                           "the person used for any limit")
    quantity: int = Field(1, ge=1)
    units: int = Field(1, ge=1, description=(
        "How many of what the person counts one item holds, counted their way: "
        "if they asked for cans of balls, a can of 3 balls is 1 and a pack of 4 "
        "cans is 4; if they asked for balls, the can is 3. 1 when one item is "
        "one of what they asked for"))
    returnable: bool | None = Field(None, description="Can it be returned; null if the shop doesn't say")
    delivery_days: int | None = Field(None, description="Days until it arrives")
    recurring: Recurring | None = Field(None, description=(
        "Set when the item renews and charges again (a subscription, a trial "
        "that turns paid, subscribe-and-save); null for a one-time purchase"))
    level: str | None = Field(None, description="beginner / intermediate / advanced, if the shop says")
    category: str | None = None


class Swap(BaseModel):
    from_token: str = Field(description="The token leaving the person's wallet, e.g. 'ASASKED'")
    amount_in: float = Field(gt=0, description="How much of from_token the swap takes")
    rate: float | None = Field(None, gt=0, description=(
        "Value of one from_token in the cart's currency, if known"))
    quote_out: float = Field(gt=0, description="Expected amount of the payment token out")
    min_out: float = Field(gt=0, description="Guaranteed minimum out (after slippage)")


class Payment(BaseModel):
    token: str = Field(description="The token the shop receives, e.g. 'USDC'")
    network: str | None = Field(None, description="The chain, e.g. 'solana'")
    amount: float = Field(gt=0, description="How much of token the shop receives, in whole units")
    to: str = Field(description="The recipient address in the transaction")
    merchant: str | None = Field(None, description=(
        "The address the shop's payment request names, as the shop returned it"))
    rate: float | None = Field(None, gt=0, description=(
        "Value of one token in the cart's currency (1.0 for USDC and dollar prices)"))
    swap: Swap | None = Field(None, description="Set when the person's token is swapped first")
    max_slippage_bps: float | None = Field(None, ge=0, le=10000, description=(
        "Slippage the swap may lose before asking; default 100 (1%)"))


class CheckResult(BaseModel):
    decision: str = Field(description='"proceed": pay. "ask": don\'t pay, show the person the '
                                      'question. "refuse": don\'t pay, change the payment')
    question: str | None = Field(None, description="For the person, as it is, when asking")
    reasons: list[str] = Field(description="What doesn't match the request")
    refused: list[str] = Field(default_factory=list, description=(
        "Payment problems no answer of the person's can approve: change the payment"))
    notes: list[str] = Field(description="What could not be checked or only roughly matches")


class Answer(BaseModel):
    question: str = Field(description="The question you showed the person")
    answer: str = Field(description="What the person replied, in their own words")


server = MCPServer(name="asasked", instructions=INSTRUCTIONS)

# Facts are extracted from the request by models, which is slow and costs
# money; a recheck of a corrected cart reuses them.
_guards: OrderedDict[tuple, Guard] = OrderedDict()
_KEEP = 64
# How to extract facts; None means by models (replaced in tests).
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
                today: str | None = None, payment: Payment | None = None) -> CheckResult:
    """Check a cart against what the person asked for, before paying.

    request: the person's request in their own words, not your summary.
    cart: every item you are about to pay for.
    answers: questions you already asked the person and their replies.
    today: today's date in words ("Monday, 2 November 2026"), if the
    person's day differs from the server's; deadlines like "by Friday" count
    from it.
    payment: the on-chain payment you are about to sign, if paying in crypto.

    Returns decision ("proceed", "ask" or "refuse"), question (for the
    person, when asking), reasons, refused (what must change in the payment)
    and notes.
    """
    guard = _guard(request, answers or [], today or today_in_words())
    result = guard.check([item.model_dump() for item in cart],
                         payment=payment.model_dump(exclude_none=True) if payment else None)
    fields = ("decision", "question", "reasons", "refused", "notes")
    return CheckResult(**{k: result[k] for k in fields})


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
