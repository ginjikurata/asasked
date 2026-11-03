"""The guard before the agent signs an AP2 closed Checkout Mandate."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from asasked.ap2 import (CheckoutError, cart_from_checkout, checkout_hash,
                         protect_presentation)
from asasked.coherence import IntentFacts
from asasked.guard import Guard

REQUEST = "Black ASICS in size 42, I need to be able to return them."
CATALOG = {
    "asics-nimbus-42-blk": {"brand": "ASICS", "color": "Black", "size": "42",
                            "returnable": False, "delivery_days": 3},
    "asics-nimbus-42-blk-r": {"brand": "ASICS", "color": "Black", "size": "42",
                              "returnable": True, "delivery_days": 3},
}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _checkout_jwt(item_id: str, price: int = 15900, quantity: int = 1,
                  currency: str = "USD") -> str:
    """A merchant-signed UCP Checkout, shaped as the AP2 merchant sample builds it."""
    payload = {
        "id": "cart_1",
        "merchant": {"id": "m1", "name": "Run Shop", "website": "https://run.example"},
        "line_items": [{"id": "li_0", "quantity": quantity,
                        "item": {"id": item_id, "title": "ASICS Gel-Nimbus 26", "price": price},
                        "totals": [{"type": "total", "amount": price * quantity}]}],
        "status": "incomplete", "currency": currency,
        "totals": [{"type": "subtotal", "amount": price * quantity},
                   {"type": "total", "amount": price * quantity}],
        "links": [],
    }
    key = ec.generate_private_key(ec.SECP256R1())
    head = _b64(json.dumps({"alg": "ES256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{body}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _guard() -> Guard:
    return Guard(REQUEST, extract=lambda _r: IntentFacts(
        brand="ASICS", color="black", size_label="42", needs_refundable=True))


def test_the_cart_is_read_from_the_checkout():
    cart = cart_from_checkout(_checkout_jwt("asics-nimbus-42-blk", quantity=2),
                              details=CATALOG.get)
    assert cart == [{"name": "ASICS Gel-Nimbus 26", "price": 159.0, "quantity": 2,
                     "brand": "ASICS", "color": "Black", "size": "42",
                     "returnable": False, "delivery_days": 3}]


def test_without_details_only_name_price_and_quantity():
    assert cart_from_checkout(_checkout_jwt("x")) == [
        {"name": "ASICS Gel-Nimbus 26", "price": 159.0, "quantity": 1}]


def test_a_hash_of_another_cart_is_refused():
    jwt = _checkout_jwt("asics-nimbus-42-blk-r")
    with pytest.raises(CheckoutError, match="different cart"):
        cart_from_checkout(jwt, checkout_hash(_checkout_jwt("asics-nimbus-42-blk")))
    assert cart_from_checkout(jwt, checkout_hash(jwt))


@pytest.mark.parametrize("bad", ["", "not-a-jwt", "a.b.c"])
def test_malformed_checkouts_raise(bad):
    with pytest.raises(CheckoutError):
        cart_from_checkout(bad)


def test_another_minor_unit_is_refused():
    with pytest.raises(CheckoutError, match="JPY"):
        cart_from_checkout(_checkout_jwt("x", price=15900, currency="JPY"))


def test_signing_is_held_while_the_cart_differs_from_the_request():
    signed = []

    def create_checkout_presentation(checkout_jwt, checkout_hash, nonce, aud="merchant"):
        signed.append(checkout_jwt)
        return {"checkout_mandate": "chk_1"}

    guard = _guard()
    sign = protect_presentation(guard, create_checkout_presentation, details=CATALOG.get)

    final_sale = _checkout_jwt("asics-nimbus-42-blk")
    out = sign(final_sale, checkout_hash(final_sale), nonce="n1")
    assert signed == [] and out.startswith("NOT PAID") and "final sale" in out

    returnable = _checkout_jwt("asics-nimbus-42-blk-r")
    out = sign(checkout_jwt=returnable, checkout_hash=checkout_hash(returnable), nonce="n2")
    assert out == {"checkout_mandate": "chk_1"} and signed == [returnable]


def test_the_signing_tool_must_take_the_checkout():
    with pytest.raises(TypeError):
        protect_presentation(_guard(), lambda cart, nonce: None)
