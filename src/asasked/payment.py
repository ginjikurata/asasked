"""Checks of an on-chain payment before the agent signs it.

The cart check (coherence.py) asks "is this what the person asked for?".
When the agent pays in crypto there is a second question: "is this payment
the one the cart and the person call for?". The wrong token, a swap that can
lose a tenth of the money, a recipient address that is not the shop's: none
of these show in the cart.

Everything here is plain arithmetic and string comparison. Amounts, addresses
and rates come from the caller: the shop's payment request (x402, Solana Pay)
and the swap quote. The guard does not read the chain, fetch prices or sign;
a forged quote or merchant address passed in defeats these checks, so pass
what the shop and the swap provider returned, not what the agent says.

The shop's address can be pinned: Guard(payees=[...]) or payees in the
person's signed mandate (asasked.mandate.payees_from_mandate). Then the
payment may go only to an approved address, and a forged payment request
naming another one is refused.

The payment, next to the cart in Guard.check(cart, payment=...):

    {"token": "USDC", "network": "solana", "amount": 129.99,
     "to": "<recipient in the transaction>", "merchant": "<the shop's address>",
     "rate": 1.0,                      # one USDC in the cart's currency
     "swap": {"from_token": "ASASKED", "amount_in": 250000, "rate": 0.00053,
              "quote_out": 132.1, "min_out": 130.8}}   # amounts of "token"
"""

from __future__ import annotations

from .coherence import BLOCK, WARN, Finding, IntentFacts, _lower, _ticker

# How far the payment may differ from the cart total before it counts: a rate
# rounded to a few digits must not stop a right payment.
AMOUNT_TOLERANCE = 0.005
# A swap may lose this much to slippage before the payment is refused (1%).
MAX_SLIPPAGE_BPS = 100
# Blocking findings the person's answer cannot approve: the payment must change.
# A pay-amount warning (paying less than the order) is not one.
REFUSED_CODES = frozenset({"pay-recipient", "pay-amount", "pay-slippage", "pay-swap-short"})


def refused(finding: Finding) -> bool:
    """A finding no answer of the person's can approve (see REFUSED_CODES)."""
    return finding.severity == BLOCK and finding.code in REFUSED_CODES


def _number(value, where: str, required: bool = False) -> float | None:
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError(f"payment: {where} must be a number above zero")
    return float(value)


def _text(value, where: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payment: {where} must be a non-empty string")
    return value.strip()


def parse_payment(value) -> dict | None:
    """A caller's payment dict -> the same, checked and in one spelling.

    None is no payment (the order is paid some other way, or the caller does
    not say). Anything malformed raises ValueError, like a cart line without
    a price: a payment the guard cannot read must not pass as checked.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("payment must be a dict (see asasked.payment)")
    payment = {
        "token": _ticker(_text(value.get("token"), "token", required=True)),
        "network": _lower(_text(value.get("network"), "network")),
        "amount": _number(value.get("amount"), "amount", required=True),
        "to": _text(value.get("to"), "to", required=True),
        "merchant": _text(value.get("merchant"), "merchant"),
        "rate": _number(value.get("rate"), "rate"),
        "swap": None,
        "max_slippage_bps": MAX_SLIPPAGE_BPS,
    }
    bps = value.get("max_slippage_bps")
    if bps is not None:
        if isinstance(bps, bool) or not isinstance(bps, (int, float)) or not 0 <= bps <= 10000:
            raise ValueError("payment: max_slippage_bps must be a number from 0 to 10000")
        payment["max_slippage_bps"] = bps
    swap = value.get("swap")
    if swap is not None:
        if not isinstance(swap, dict):
            raise ValueError("payment: swap must be a dict or null")
        payment["swap"] = {
            "from_token": _ticker(_text(swap.get("from_token"), "swap.from_token",
                                        required=True)),
            "amount_in": _number(swap.get("amount_in"), "swap.amount_in", required=True),
            "rate": _number(swap.get("rate"), "swap.rate"),
            "quote_out": _number(swap.get("quote_out"), "swap.quote_out", required=True),
            "min_out": _number(swap.get("min_out"), "swap.min_out", required=True),
        }
        if payment["swap"]["min_out"] > payment["swap"]["quote_out"]:
            raise ValueError("payment: swap.min_out cannot be above swap.quote_out")
    return payment


def _same_address(a: str, b: str) -> bool:
    # EVM addresses are hex and their case is only a checksum; Solana and
    # other base58 addresses are case-sensitive.
    if a.lower().startswith("0x") and b.lower().startswith("0x"):
        return a.lower() == b.lower()
    return a == b


def _amount(x: float) -> str:
    return f"{x:,.6f}".rstrip("0").rstrip(".")


def _money(cents: float) -> str:
    return f"${cents / 100:,.2f}"


def check_payment(facts: IntentFacts, payment: dict | None, total_cents: int,
                  over_limit: bool = False, payees: tuple[str, ...] = (),
                  spent_before_cents: float = 0) -> list[Finding]:
    """Findings on the payment, in the same form as the cart's.

    payment is parse_payment's result or None. total_cents is the cart total
    (today's prices). over_limit says the cart check already found the cart
    over the person's limit: the payment then does not repeat it. payees are
    the addresses the person approved (Guard(payees=...), or their signed
    mandate): when given, the money may go only there, whatever the shop's
    payment request says. spent_before_cents is what was already paid for the
    same request: it counts against the person's limit too.
    """
    def sev(field_name: str) -> str:
        return WARN if field_name in facts.soft or field_name in facts.disputed else BLOCK

    found: list[Finding] = []
    if payment is None:
        wanted = " on ".join(v for v in (facts.pay_with, facts.pay_network
                                         and facts.pay_network.capitalize()) if v)
        if wanted:
            field_name = "pay_with" if facts.pay_with else "pay_network"
            found.append(Finding(
                "pay-unchecked", sev(field_name),
                f"You asked to pay with {wanted}; I can't see how this order will be paid."))
        return found

    swap = payment["swap"]

    # The recipient: no fact of the person's makes paying a stranger right.
    if payees:
        # The shop's payment request can be forged; the person's approval can't.
        if not any(_same_address(payment["to"], p) for p in payees):
            found.append(Finding(
                "pay-recipient", BLOCK,
                f"The payment goes to {payment['to']}, which is not an address the person "
                f"approved ({', '.join(payees)})."))
        elif payment["merchant"] is not None and not _same_address(payment["to"],
                                                                  payment["merchant"]):
            found.append(Finding(
                "unchecked", WARN,
                f"The shop's payment request names {payment['merchant']}, not the approved "
                f"address {payment['to']}; the shop may not see this payment."))
    elif payment["merchant"] is None:
        found.append(Finding(
            "unchecked", WARN,
            "The shop's payment address wasn't given, so I couldn't check who receives the money."))
    elif not _same_address(payment["to"], payment["merchant"]):
        found.append(Finding(
            "pay-recipient", BLOCK,
            f"The payment goes to {payment['to']}, not to the shop's address "
            f"{payment['merchant']}."))
    else:
        found.append(Finding(
            "pay-unpinned", WARN,
            "The shop's address comes from its payment request, not from an address the "
            "person approved, so a forged request would not be caught."))

    given = swap["from_token"] if swap else payment["token"]
    if facts.pay_with and given != facts.pay_with:
        found.append(Finding(
            "pay-token", sev("pay_with"),
            f"Asked to pay with {facts.pay_with}, the payment uses {given}."))

    if facts.pay_network:
        if payment["network"] is None:
            found.append(Finding(
                "unchecked", WARN,
                f"Asked to pay on {facts.pay_network.capitalize()}; "
                "the payment doesn't say which network."))
        elif payment["network"] != facts.pay_network:
            found.append(Finding(
                "pay-network", sev("pay_network"),
                f"Asked to pay on {facts.pay_network.capitalize()}, the payment goes out on "
                f"{payment['network'].capitalize()}."))

    # The amount the shop receives against the cart.
    overpaid = False
    if payment["rate"] is None:
        found.append(Finding(
            "unchecked", WARN,
            f"No {payment['token']} rate was given, so I couldn't check the payment "
            "against the order total."))
    else:
        paid = payment["amount"] * payment["rate"] * 100
        slack = max(1, total_cents * AMOUNT_TOLERANCE)
        shown = f"{_amount(payment['amount'])} {payment['token']} (about {_money(paid)})"
        if paid > total_cents + slack:
            overpaid = True
            found.append(Finding(
                "pay-amount", BLOCK,
                f"The payment is {shown}, the order total is {_money(total_cents)}."))
        elif paid < total_cents - slack:
            found.append(Finding(
                "pay-amount", WARN,
                f"The payment is {shown}, less than the order total of {_money(total_cents)}; "
                "the shop may refuse it."))

    # What leaves the person's wallet, swap costs included, against their limit.
    # Not while the amount itself is refused: the person would be asked about
    # a sum that cannot be paid anyway; the corrected payment is checked again.
    if facts.explicit_max_cents and not over_limit and not overpaid:
        rate = swap["rate"] if swap else payment["rate"]
        if rate is not None:
            spent = (swap["amount_in"] if swap else payment["amount"]) * rate * 100
            earlier = max(0, spent_before_cents)
            # A millionth of a cent of slack, for sums of sub-cent payments in floats.
            if spent + earlier > facts.explicit_max_cents + 1e-6:
                before = (f", with {_money(earlier)} already paid for this request"
                          if earlier else "")
                found.append(Finding(
                    "pay-max", sev("explicit_max_cents"),
                    f"Set a limit of {_money(facts.explicit_max_cents)}; paying takes "
                    f"{_amount(swap['amount_in'] if swap else payment['amount'])} {given}, "
                    f"about {_money(spent)}{before}."))

    if swap:
        loss = (swap["quote_out"] - swap["min_out"]) / swap["quote_out"] * 10000
        if loss > payment["max_slippage_bps"]:
            found.append(Finding(
                "pay-slippage", BLOCK,
                f"The swap from {swap['from_token']} to {payment['token']} may give up to "
                f"{loss / 100:.2f}% less than quoted (allowed: "
                f"{payment['max_slippage_bps'] / 100:.2f}%)."))
        if swap["min_out"] < payment["amount"]:
            found.append(Finding(
                "pay-swap-short", BLOCK,
                f"The swap guarantees only {_amount(swap['min_out'])} {payment['token']}, "
                f"the payment needs {_amount(payment['amount'])}."))
    return found


__all__ = ["AMOUNT_TOLERANCE", "MAX_SLIPPAGE_BPS", "REFUSED_CODES", "check_payment",
           "parse_payment", "refused"]
