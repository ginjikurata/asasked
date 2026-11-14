"""The person's request, read from their signed Verifiable Intent mandate.

Without a mandate the guard has to take the agent's word for what the person
asked: an agent could reword the request and the guard would check the cart
against the wrong words. The L2 mandate is signed by the person's own key, so
its prompt_summary is the person's request as they approved it, and the agent
cannot change it without breaking the signature.

Where prompt_summary lives is not settled in VI v0.1, so all three places are read:

- inside the checkout mandate disclosure (spec/credential-format.md, §4 example);
- as a selectively disclosable L2 claim (spec/README.md, the L2 table);
- as a plain L2 claim (the TypeScript implementation, verifiable-intent@0.1.0).

The Mastercard Python SDK (356c296) accepts prompt_summary in UserMandate but
does not write it into the signed L2, so its mandates carry no request.

Only the L2 signature and the disclosure digests are checked here: that the
request is the one the key holder signed. Whether that key is the person's
(the L1 issuer signature, expiry, the rest of the chain) is the chain
verification's job, done before this, e.g. by verify_chain in the VI SDK.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

CHECKOUT_VCT = "mandate.checkout.open.1"


class MandateError(ValueError):
    """The mandate is malformed or its signature does not verify."""


def _b64decode(s: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (ValueError, TypeError) as e:
        raise MandateError(f"not base64url: {e}") from e


def _json(s: str):
    try:
        return json.loads(_b64decode(s))
    except ValueError as e:
        raise MandateError(f"not JSON: {e}") from e


def _digest(disclosure: str) -> str:
    raw = hashlib.sha256(disclosure.encode("ascii")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_key(jwk: dict) -> ec.EllipticCurvePublicKey:
    if not isinstance(jwk, dict) or jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise MandateError("the user key must be an EC P-256 JWK")
    try:
        x = int.from_bytes(_b64decode(jwk["x"]), "big")
        y = int.from_bytes(_b64decode(jwk["y"]), "big")
        return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    except (KeyError, TypeError, ValueError) as e:
        raise MandateError(f"the user key is malformed: {e}") from e


def _verify(jwt: str, key: ec.EllipticCurvePublicKey) -> dict:
    """The JWS payload, if its ES256 signature verifies over the segments as sent."""
    parts = jwt.split(".")
    if len(parts) != 3:
        raise MandateError("the L2 JWT must have three parts")
    header, payload, signature = _json(parts[0]), _json(parts[1]), _b64decode(parts[2])
    if not isinstance(header, dict) or header.get("alg") != "ES256":
        raise MandateError("the L2 JWT must be signed with ES256")
    if len(signature) != 64:
        raise MandateError("an ES256 signature is 64 bytes")
    der = encode_dss_signature(int.from_bytes(signature[:32], "big"),
                               int.from_bytes(signature[32:], "big"))
    try:
        key.verify(der, f"{parts[0]}.{parts[1]}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise MandateError("the L2 signature does not verify with the user key") from None
    if not isinstance(payload, dict):
        raise MandateError("the L2 payload must be a JSON object")
    return payload


def _digests(value) -> set[str]:
    """Every digest a signed value commits to: _sd entries and {"...": digest} refs."""
    found: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("..."), str):
            found.add(value["..."])
        if isinstance(value.get("_sd"), list):
            found.update(d for d in value["_sd"] if isinstance(d, str))
        for v in value.values():
            found |= _digests(v)
    elif isinstance(value, list):
        for v in value:
            found |= _digests(v)
    return found


def _committed(payload: dict, disclosures: list[str]) -> list[list]:
    """Disclosures the signature reaches, directly or through other disclosures.

    One the signed payload does not commit to was added by someone else and is
    dropped, not trusted.
    """
    return list(_committed_by_digest(payload, disclosures).values())


def _committed_by_digest(payload: dict, disclosures: list[str]) -> dict[str, list]:
    """The same as _committed, keyed by digest, to resolve {"...": digest} refs."""
    decoded = {}
    for d in disclosures:
        value = _json(d)
        if not isinstance(value, list) or len(value) not in (2, 3):
            raise MandateError("a disclosure must be a JSON array of 2 or 3 elements")
        decoded[_digest(d)] = value
    reached, frontier = set(), _digests(payload)
    while frontier:
        new = {h for h in frontier if h in decoded} - reached
        reached |= new
        frontier = set().union(*(_digests(decoded[h][-1]) for h in new)) if new else set()
    return {h: decoded[h] for h in reached}


def request_from_mandate(l2: str, user_jwk: dict) -> str | None:
    """The person's request from a serialized L2 mandate, or None if it carries none.

    l2 is the L2 SD-JWT as presented (<jwt>~<disclosure>~...~[kb-jwt]);
    user_jwk is the person's public key, from cnf.jwk of the verified L1.
    Raises MandateError if the mandate is malformed or the signature fails.
    """
    if not isinstance(l2, str) or not l2:
        raise MandateError("the mandate must be a serialized SD-JWT")
    jwt, *rest = l2.split("~")
    disclosures = [d for d in rest if d and "." not in d]   # a trailing KB-JWT has dots
    payload = _verify(jwt, _public_key(user_jwk))

    texts = [payload.get("prompt_summary")]
    for value in _committed(payload, disclosures):
        if len(value) == 3 and value[1] == "prompt_summary":
            texts.append(value[2])
        elif isinstance(value[-1], dict) and value[-1].get("vct") == CHECKOUT_VCT:
            texts.append(value[-1].get("prompt_summary"))
    # The same text in two places is one request; spacing aside.
    found = {" ".join(t.split()): t.strip() for t in texts if isinstance(t, str) and t.strip()}
    if len(found) > 1:
        # Two different requests in one mandate: picking one would be a guess.
        raise MandateError("the mandate carries two different requests")
    return next(iter(found.values()), None)


# A CAIP-10 account id: <namespace>:<chain reference>:<address>, e.g.
# "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp:<address>" or "eip155:1:0x...".
_CAIP10 = re.compile(r"^[-a-z0-9]{3,8}:[-_a-zA-Z0-9]{1,32}:([-.%a-zA-Z0-9]{1,128})$")


def payees_from_mandate(l2: str, user_jwk: dict) -> tuple[str, ...]:
    """Payment addresses the person approved in their signed L2 mandate.

    VI's mandate.payment.allowed_payees lists payees by id, name and website;
    it has no field for an on-chain address. A payee whose id is a CAIP-10
    account id ("solana:<chain>:<address>") names one, and that address is
    returned. Payees with other ids, and undisclosed payees, give none: an
    empty tuple means the mandate pins no address, not that none is allowed.
    Raises MandateError if the mandate is malformed or the signature fails.
    """
    if not isinstance(l2, str) or not l2:
        raise MandateError("the mandate must be a serialized SD-JWT")
    jwt, *rest = l2.split("~")
    disclosures = [d for d in rest if d and "." not in d]
    payload = _verify(jwt, _public_key(user_jwk))
    committed = _committed_by_digest(payload, disclosures)

    mandates = [v[-1] for v in committed.values() if isinstance(v[-1], dict)]
    mandates += [m for m in payload.get("delegate_payload") or [] if isinstance(m, dict)]
    found: list[str] = []
    for m in mandates:
        if not str(m.get("vct", "")).startswith("mandate.payment"):
            continue
        # Immediate mode names the one payee; autonomous mode lists allowed ones.
        entries = [m["payee"]] if isinstance(m.get("payee"), dict) else []
        for c in m.get("constraints") or []:
            if isinstance(c, dict) and c.get("type") == "mandate.payment.allowed_payees":
                entries += c.get("allowed") or []
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("..."), str):
                entry = committed.get(entry["..."], [None])[-1]
            payee_id = entry.get("id") if isinstance(entry, dict) else None
            match = _CAIP10.match(payee_id) if isinstance(payee_id, str) else None
            if match and match.group(1) not in found:
                found.append(match.group(1))
    return tuple(found)


__all__ = ["MandateError", "payees_from_mandate", "request_from_mandate"]
