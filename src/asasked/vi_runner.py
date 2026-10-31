"""Builds a real Verifiable Intent chain for a scenario and verifies it with
the genuine library from the Mastercard repository.

Nothing is simulated here: signatures, selective disclosure, layer binding
and constraint checks are all called from the SDK as they are.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid
from pathlib import Path

def _find_vi_sdk() -> Path:
    """Where the agent-intent/verifiable-intent clone lives.

    An absolute path must not be hard-coded here: the project would stop
    working after the folder moves or on another machine. Search order: the
    environment variable, then the usual places next to the project.
    """
    here = Path(__file__).resolve().parents[2]
    candidates = []
    if env_path := os.environ.get("VI_SDK_PATH"):
        candidates.append(Path(env_path).expanduser())
    candidates += [
        here.parent / "verifiable-intent",   # next to the project folder
        here / "verifiable-intent",          # inside the project folder
    ]
    for path in candidates:
        if (path / "src" / "verifiable_intent").is_dir():
            return path
    raise SystemExit(
        "Verifiable Intent SDK not found. Looked in:\n"
        + "\n".join(f"  - {c}" for c in candidates)
        + "\n\nClone it next to the project:\n"
        "  git clone https://github.com/agent-intent/verifiable-intent.git\n"
        "or set its path in the VI_SDK_PATH variable."
    )


VI = _find_vi_sdk()
for p in (str(VI / "src"), str(VI / "examples")):
    if p not in sys.path:
        sys.path.insert(0, p)

from helpers import get_agent_keys, get_issuer_keys, get_merchant_keys, get_user_keys  # noqa: E402
from verifiable_intent.crypto.disclosure import (  # noqa: E402
    _b64url_encode, build_selective_presentation, hash_bytes, hash_disclosure,
)
from verifiable_intent.crypto.sd_jwt import decode_sd_jwt, resolve_disclosures  # noqa: E402
from verifiable_intent.crypto.signing import _jwt_encode  # noqa: E402
from verifiable_intent.issuance.agent import create_layer3_checkout, create_layer3_payment  # noqa: E402
from verifiable_intent.issuance.issuer import create_layer1  # noqa: E402
from verifiable_intent.issuance.user import create_layer2_autonomous  # noqa: E402
from verifiable_intent.models.agent_mandate import (  # noqa: E402
    CheckoutL3Mandate, FinalCheckoutMandate, FinalPaymentMandate, PaymentL3Mandate,
)
from verifiable_intent.models.constraints import (  # noqa: E402
    AllowedMerchantConstraint, AllowedPayeeConstraint,
    CheckoutLineItemsConstraint, PaymentAmountConstraint,
)
from verifiable_intent.models.issuer_credential import IssuerCredential  # noqa: E402
from verifiable_intent.models.user_mandate import (  # noqa: E402
    CheckoutMandate, MandateMode, PaymentMandate, UserMandate,
)
from verifiable_intent.verification.chain import verify_chain  # noqa: E402
from verifiable_intent.verification.constraint_checker import check_constraints  # noqa: E402

from . import catalog  # noqa: E402

PAYMENT_INSTRUMENT = {
    "type": "mastercard.srcDigitalCard",
    "id": "f199c3dd-7106-478b-9b5f-7af9ca725170",
    "description": "Mastercard **** 1234",
}


def _checkout_jwt(purchase, merchant_keys, find, merchant):
    now = int(time.time())
    items, total = [], 0
    for sku, qty in purchase:
        p = find(sku)
        total += p["price_cents"] * qty
        items.append({"sku": p["sku"], "name": p["name"], "quantity": qty,
                      "unitPrice": p["price_cents"] / 100})
    payload = {
        "iss": merchant["website"], "sub": "cart_checkout",
        "iat": now, "exp": now + 3600,
        "cart": {"items": items, "subTotal": {"amount": total / 100, "currencyCode": "USD"}},
    }
    jwt = _jwt_encode({"alg": "ES256", "typ": "JWT", "kid": merchant_keys.kid},
                      payload, merchant_keys.private_key)
    return jwt, total


def _find_disc(sd_jwt, predicate):
    for s, v in zip(sd_jwt.disclosures, sd_jwt.disclosure_values):
        value = v[-1] if v else None
        if predicate(value):
            return s
    return None


def run_vi(scn, find=catalog.find, merchants=None, merchant=None) -> dict:
    """Returns: chain authenticity, constraint compliance, violations.

    scn is anything with the fields allowlist, prompt_summary, quantity_cap,
    amount_min_cents, amount_max_cents, purchase (a scenario or an order from
    the sandbox store). find looks a product up by sku, merchants are the
    allowed merchants, merchant is the one bought from (the first by default).
    """
    # Only the fields the standard describes go into the mandate.
    merchants = [{k: m[k] for k in ("id", "name", "website")}
                 for m in (merchants or catalog.MERCHANTS)]
    merchant_entry = next(m for m in merchants
                          if m["id"] == (merchant["id"] if merchant else merchants[0]["id"]))
    now = int(time.time())
    issuer, user, agent, merchant_keys = (
        get_issuer_keys(), get_user_keys(), get_agent_keys(), get_merchant_keys()
    )

    # --- L1 -----------------------------------------------------------
    l1 = create_layer1(IssuerCredential(
        iss="https://www.mastercard.com", sub="user-001", iat=now, exp=now + 86400,
        aud="https://wallet.example.com", cnf_jwk=user.public_jwk,
        email="user@example.com", pan_last_four="1234", scheme="Mastercard",
    ), issuer.private_key)

    acceptable = [{"id": s, "title": find(s)["name"]} for s in scn.allowlist]

    # --- L2 -----------------------------------------------------------
    mandate = UserMandate(
        nonce=str(uuid.uuid4()), aud="https://agent.example", iat=now,
        iss="https://wallet.example.com", exp=now + 86400,
        mode=MandateMode.AUTONOMOUS,
        sd_hash=hash_bytes(l1.serialize().encode("ascii")),
        prompt_summary=scn.prompt_summary,
        checkout_mandate=CheckoutMandate(
            cnf_jwk=agent.public_jwk, cnf_kid="agent-key-1",
            constraints=[
                AllowedMerchantConstraint(allowed=merchants),
                CheckoutLineItemsConstraint(items=[{
                    "id": "line-1", "acceptable_items": acceptable,
                    "quantity": scn.quantity_cap,
                }]),
            ],
        ),
        payment_mandate=PaymentMandate(
            cnf_jwk=agent.public_jwk, cnf_kid="agent-key-1",
            payment_instrument=PAYMENT_INSTRUMENT,
            risk_data={"device_id": "dev-1", "ip_address": "10.0.0.1"},
            constraints=[
                PaymentAmountConstraint(currency="USD", min=scn.amount_min_cents,
                                        max=scn.amount_max_cents),
                AllowedPayeeConstraint(allowed=merchants),
            ],
        ),
        merchants=merchants, acceptable_items=acceptable,
    )
    l2 = create_layer2_autonomous(mandate, user.private_key)
    l2_ser = l2.serialize()
    l2_base = l2_ser.split("~")[0]

    # --- the agent buys ------------------------------------------------
    jwt, total = _checkout_jwt(scn.purchase, merchant_keys, find, merchant_entry)
    c_hash = _b64url_encode(hashlib.sha256(jwt.encode("utf-8")).digest())
    nonce = str(uuid.uuid4())

    pay_disc = _find_disc(l2, lambda v: isinstance(v, dict) and v.get("vct") == "mandate.payment.open.1")
    chk_disc = _find_disc(l2, lambda v: isinstance(v, dict) and v.get("vct") == "mandate.checkout.open.1")
    mer_disc = _find_disc(l2, lambda v: isinstance(v, dict) and v.get("name") == merchant_entry["name"])
    itm_disc = _find_disc(l2, lambda v: isinstance(v, dict) and v.get("id") == scn.allowlist[0])

    l3a = create_layer3_payment(PaymentL3Mandate(
        nonce=nonce, aud="https://www.mastercard.com", iat=now,
        iss="https://agent.example", exp=now + 300,
        final_payment=FinalPaymentMandate(
            transaction_id=c_hash, payee=merchant_entry,
            payment_amount={"currency": "USD", "amount": total},
            payment_instrument=PAYMENT_INSTRUMENT,
        ),
        final_merchant=merchant_entry,
    ), agent.private_key, l2_base, pay_disc, mer_disc)

    l3b = create_layer3_checkout(CheckoutL3Mandate(
        nonce=nonce, aud=merchant_entry["website"], iat=now,
        iss="https://agent.example", exp=now + 300,
        final_checkout=FinalCheckoutMandate(checkout_jwt=jwt, checkout_hash=c_hash),
    ), agent.private_key, l2_base, chk_disc, itm_disc)

    # --- chain verification --------------------------------------------
    l1_parsed, l2_parsed = decode_sd_jwt(l1.serialize()), decode_sd_jwt(l2_ser)
    l2_payment_ser = build_selective_presentation(l2_base, [pay_disc, mer_disc])
    chain = verify_chain(l1_parsed, l2_parsed, l3_payment=l3a,
                         issuer_public_key=issuer.public_key,
                         l1_serialized=l1.serialize(), l2_serialized=l2_ser,
                         l2_payment_serialized=l2_payment_ser)

    violations: list[str] = []
    satisfied = False
    if chain.valid:
        l2_claims = resolve_disclosures(l2_parsed)
        disc_by_hash = {hash_disclosure(s): v for s, v in
                        zip(l2_parsed.disclosures, l2_parsed.disclosure_values)}

        pay_constraints, chk_constraints = [], []
        for d in l2_claims.get("delegate_payload", []):
            if not isinstance(d, dict):
                continue
            if d.get("vct") == "mandate.payment.open.1":
                pay_constraints = d.get("constraints", [])
            elif d.get("vct") == "mandate.checkout.open.1":
                chk_constraints = d.get("constraints", [])

        fulfillment = {}
        for d in chain.l3_payment_claims.get("delegate_payload", []):
            if isinstance(d, dict) and d.get("vct") == "mandate.payment.1":
                fulfillment = dict(d)
        for c in pay_constraints:
            if c.get("type") == "mandate.payment.allowed_payees":
                fulfillment["allowed_merchants"] = [
                    disc_by_hash[r["..."]][-1] for r in c.get("allowed", [])
                    if isinstance(r, dict) and r.get("...") in disc_by_hash
                ]

        pay_res = check_constraints(pay_constraints, fulfillment)

        # the merchant's side: the same constraints, the cart as line_items
        chk_inline = []
        for c in chk_constraints:
            c = dict(c)
            if c.get("type") == "mandate.checkout.line_items":
                c["items"] = [{"id": "line-1", "acceptable_items": acceptable,
                               "quantity": scn.quantity_cap}]
            chk_inline.append(c)
        chk_res = check_constraints(chk_inline, {
            "line_items": [{"id": sku, "quantity": q} for sku, q in scn.purchase],
            "merchant": merchant_entry,
            "allowed_merchants": merchants,
        })

        satisfied = pay_res.satisfied and chk_res.satisfied
        violations = list(pay_res.violations) + list(chk_res.violations)

    return {
        "chain_valid": chain.valid,
        "chain_errors": list(chain.errors),
        "constraints_ok": satisfied,
        "violations": violations,
        "total_cents": total,
        # Raw signed artifacts, so that a second implementation of the
        # standard can validate them itself and compare its answer with
        # ours rather than take our word for it.
        "artifacts": {
            "layer1": l1.serialize(),
            "layer2": l2_ser,
            "layer2_payment_presentation": l2_payment_ser,
            "layer3_payment": l3a.serialize(),
            "layer3_checkout": l3b.serialize(),
        },
        "keys": {
            "issuer_public_jwk": issuer.public_jwk,
            "user_public_jwk": user.public_jwk,
            "agent_public_jwk": agent.public_jwk,
            "merchant_public_jwk": merchant_keys.public_jwk,
        },
    }
