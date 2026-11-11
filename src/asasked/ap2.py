"""The guard in an AP2 (Agent Payments Protocol, v0.2) shopping agent.

In AP2 the merchant signs the cart as a checkout JWT (a UCP Checkout object),
and the Shopping Agent then signs a closed Checkout Mandate over its hash.
That signature is the agent's commitment to pay for exactly this cart, so
the guard goes right before it: the spec itself suggests "deterministic code
verifies the closed Mandate being created before being signed"
(docs/ap2/implementation_considerations.md, Agent Key).

    guard = Guard("black running shoes, size 42, I need to be able to return them")
    sign = protect_presentation(guard, create_checkout_presentation, details=catalog.get)

While the merchant's cart differs from the request, sign() does not sign and
gives the agent the question for the person instead (see guard.NOT_PAID).

Where the request comes from. AP2 v0.1 had it in the Intent Mandate
(natural_language_description); v0.2 removed the Intent Mandate, and its open
Checkout Mandate carries only constraints (merchants, item ids, quantities).
So the request is the person's words from the conversation, passed by your
code, not retold by the agent.

A UCP item has an id, a title and a price, nothing else: no colour, size or
returns. Those come from the merchant's catalog through details(item_id);
without it the guard can only check names, prices and quantities, and notes
what it could not check.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
from collections.abc import Callable

from .guard import Guard

# The guard compares prices in hundredths. Currencies with another minor unit
# (JPY, KWD, ...) would need their own conversion and are refused, not guessed.
TWO_DECIMAL = frozenset({"USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF", "SEK", "NOK",
                         "DKK", "PLN", "CZK", "SGD", "HKD", "MXN", "BRL", "INR", "CNY",
                         "ZAR", "RUB", "TRY", "ILS", "AED"})

# Item attributes the guard knows (see guard._cart_item); details() may give these.
DETAILS = ("brand", "color", "size", "level", "category", "returnable", "delivery_days", "units",
           "recurring")


class CheckoutError(ValueError):
    """The checkout JWT is malformed or is not the one the agent is about to sign."""


def _b64decode(s: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (ValueError, TypeError) as e:
        raise CheckoutError(f"not base64url: {e}") from e


def checkout_hash(checkout_jwt: str) -> str:
    """The checkout_hash AP2 puts in the closed Checkout Mandate (sha-256, base64url)."""
    raw = hashlib.sha256(checkout_jwt.encode("ascii")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def checkout_payload(checkout_jwt: str, expected_hash: str | None = None) -> dict:
    """The UCP Checkout object inside a merchant's checkout JWT.

    The merchant's signature is not checked here: the merchant checks its own
    JWT when the order is completed. What matters to the guard is that it reads
    the very cart the agent signs, so with expected_hash (the checkout_hash
    the agent passes along) a JWT that does not match it is refused.
    """
    if not isinstance(checkout_jwt, str) or checkout_jwt.count(".") != 2:
        raise CheckoutError("the checkout must be a compact JWT")
    if expected_hash is not None and checkout_hash(checkout_jwt) != expected_hash:
        raise CheckoutError("checkout_hash is not the hash of this checkout JWT: "
                            "the agent would sign a different cart from the one checked")
    try:
        payload = json.loads(_b64decode(checkout_jwt.split(".")[1]))
    except ValueError as e:
        raise CheckoutError(f"the checkout payload is not JSON: {e}") from e
    if not isinstance(payload, dict) or not isinstance(payload.get("line_items"), list):
        raise CheckoutError("the checkout has no line_items")
    return payload


def cart_from_checkout(checkout_jwt: str, expected_hash: str | None = None,
                       details: Callable[[str], dict | None] | None = None) -> list[dict]:
    """The merchant's cart as the guard's cart lines (see Guard.check).

    details(item_id) returns what the merchant's catalog knows about an item
    (brand, color, size, returnable, delivery_days, ...), or None.
    """
    payload = checkout_payload(checkout_jwt, expected_hash)
    currency = payload.get("currency")
    if currency not in TWO_DECIMAL:
        raise CheckoutError(f"currency {currency!r} is not supported: "
                            "only currencies with two decimal places")
    cart = []
    for i, line in enumerate(payload["line_items"]):
        item = line.get("item") if isinstance(line, dict) else None
        if not isinstance(item, dict) or not item.get("id"):
            raise CheckoutError(f"line_items[{i}] has no item id")
        price = item.get("price")
        if isinstance(price, bool) or not isinstance(price, int) or price < 0:
            raise CheckoutError(f"line_items[{i}]: the price must be an integer in minor units")
        extra = (details(item["id"]) if details else None) or {}
        cart.append({
            "name": item.get("title") or item["id"],
            "price": price / 100,
            "quantity": line.get("quantity", 1),
            **{k: extra[k] for k in DETAILS if extra.get(k) is not None},
        })
    return cart


def protect_presentation(guard: Guard, sign: Callable,
                         details: Callable[[str], dict | None] | None = None) -> Callable:
    """The agent's tool that signs the closed Checkout Mandate, asking the guard first.

    sign takes the merchant's checkout as checkout_jwt and checkout_hash, by
    name or position, as create_checkout_presentation in the AP2 samples does.
    """
    signature = inspect.signature(sign)
    if "checkout_jwt" not in signature.parameters:
        raise TypeError("the signing tool must take checkout_jwt")

    def cart(*args, **kwargs) -> list[dict]:
        bound = signature.bind_partial(*args, **kwargs).arguments
        if "checkout_jwt" not in bound:
            raise CheckoutError("the signing tool was called without checkout_jwt")
        return cart_from_checkout(bound["checkout_jwt"], bound.get("checkout_hash"), details)

    return guard.protect(sign, cart=cart)


__all__ = ["CheckoutError", "cart_from_checkout", "checkout_hash", "checkout_payload",
           "protect_presentation"]
