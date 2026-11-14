"""The person's request read from their signed L2 mandate."""

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from asasked.coherence import IntentFacts
from asasked.guard import Guard
from asasked.mandate import MandateError, payees_from_mandate, request_from_mandate

REQUEST = "Black ASICS in size 42, I need to be able to return them."
SHOE = {"name": "ASICS Gel-Nimbus 26", "brand": "ASICS", "color": "Black",
        "size": "42", "price": 159.00, "returnable": False}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _enc(value) -> str:
    return _b64(json.dumps(value, separators=(",", ":")).encode())


def _disclosure(*value) -> str:
    return _enc(["salt-" + str(len(value)), *value])


def _digest(d: str) -> str:
    return _b64(hashlib.sha256(d.encode("ascii")).digest())


def _jwk(key) -> dict:
    n = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256",
            "x": _b64(n.x.to_bytes(32, "big")), "y": _b64(n.y.to_bytes(32, "big"))}


def _l2(key, payload: dict, disclosures=(), commit=True) -> str:
    payload = {"nonce": "n", "aud": "https://agent.example", "iat": 0, "_sd_alg": "sha-256",
               **payload}
    if commit:
        payload["_sd"] = [_digest(d) for d in disclosures]
    signing_input = f"{_enc({'alg': 'ES256', 'typ': 'kb-sd-jwt+kb'})}.{_enc(payload)}"
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    jwt = f"{signing_input}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return "~".join([jwt, *disclosures]) + "~"


@pytest.fixture
def key():
    return ec.generate_private_key(ec.SECP256R1())


def _checkout(summary=None) -> str:
    mandate = {"vct": "mandate.checkout.open.1", "constraints": []}
    if summary is not None:
        mandate["prompt_summary"] = summary
    return _disclosure(mandate)


def test_reads_the_request_from_the_checkout_mandate(key):
    # spec/credential-format.md: prompt_summary inside the checkout mandate
    assert request_from_mandate(_l2(key, {}, [_checkout(REQUEST)]), _jwk(key)) == REQUEST


def test_reads_the_request_as_a_disclosed_claim(key):
    # spec/README.md: a selectively disclosable L2 claim
    l2 = _l2(key, {}, [_disclosure("prompt_summary", REQUEST), _checkout()])
    assert request_from_mandate(l2, _jwk(key)) == REQUEST


def test_reads_the_request_as_a_plain_claim(key):
    # the TypeScript implementation puts it straight into the payload
    assert request_from_mandate(_l2(key, {"prompt_summary": REQUEST}), _jwk(key)) == REQUEST


def test_the_same_request_in_two_places_is_one(key):
    l2 = _l2(key, {"prompt_summary": REQUEST}, [_checkout(" " + REQUEST)])
    assert request_from_mandate(l2, _jwk(key)) == REQUEST


def test_two_different_requests_are_refused(key):
    l2 = _l2(key, {"prompt_summary": REQUEST}, [_checkout("White Nike, any size.")])
    with pytest.raises(MandateError, match="two different"):
        request_from_mandate(l2, _jwk(key))


def test_no_request_in_the_mandate(key):
    assert request_from_mandate(_l2(key, {}, [_checkout()]), _jwk(key)) is None


def test_a_disclosure_the_signature_does_not_reach_is_ignored(key):
    # Anyone can append a disclosure; only those the signed payload commits to count.
    signed = _l2(key, {}, [_checkout()])
    assert request_from_mandate(signed + _checkout("White Nike, any size.") + "~",
                                _jwk(key)) is None


def test_a_reworded_request_breaks_the_signature(key):
    jwt, rest = _l2(key, {"prompt_summary": REQUEST}).split("~", 1)
    head, payload, sig = jwt.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged = _enc({**claims, "prompt_summary": "Any ASICS, final sale is fine."})
    with pytest.raises(MandateError, match="signature"):
        request_from_mandate(f"{head}.{forged}.{sig}~{rest}", _jwk(key))


def test_another_key_is_refused(key):
    other = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(MandateError, match="signature"):
        request_from_mandate(_l2(other, {"prompt_summary": REQUEST}), _jwk(key))


def test_a_trailing_key_binding_jwt_is_not_a_disclosure(key):
    l2 = _l2(key, {}, [_checkout(REQUEST)]) + "aaa.bbb.ccc"
    assert request_from_mandate(l2, _jwk(key)) == REQUEST


@pytest.mark.parametrize("bad", ["", "not-a-jwt~", "a.b.c~"])
def test_malformed_mandates_raise(key, bad):
    with pytest.raises(MandateError):
        request_from_mandate(bad, _jwk(key))


def test_guard_checks_against_the_signed_request(key):
    heard = []

    def extract(request):
        heard.append(request)
        return IntentFacts(brand="ASICS", color="black", size_label="42", needs_refundable=True)

    guard = Guard.from_mandate(_l2(key, {}, [_checkout(REQUEST)]), _jwk(key), extract=extract)
    result = guard.check([SHOE])
    assert heard == [REQUEST]
    assert result["decision"] == "ask" and "final sale" in result["reasons"][0]


def test_guard_asks_when_the_mandate_has_no_request(key):
    guard = Guard.from_mandate(_l2(key, {}, [_checkout()]), _jwk(key),
                               extract=lambda _r: pytest.fail("nothing to extract"))
    result = guard.check([{**SHOE, "returnable": True}])
    assert result["decision"] == "ask"
    assert "prompt_summary" in result["error"]
    assert "ASICS Gel-Nimbus 26" in result["question"]


def test_mastercard_sdk_leaves_the_request_out():
    # UserMandate takes prompt_summary, but create_layer2_autonomous does not sign
    # it into L2 (356c296). If this starts failing, the SDK has fixed it.
    vi_runner = pytest.importorskip("asasked.vi_runner", exc_type=SystemExit)
    from asasked.scenarios import SCENARIOS
    result = vi_runner.run_vi(SCENARIOS[0])
    assert SCENARIOS[0].prompt_summary
    assert request_from_mandate(result["artifacts"]["layer2"],
                                result["keys"]["user_public_jwk"]) is None


def _facts(request):
    if "white" in request.lower():
        return IntentFacts(brand="ASICS", color="white", size_label="42")
    return IntentFacts(brand="ASICS", color="black", size_label="42", needs_refundable=True)


def test_the_agent_retelling_the_request_is_flagged(key):
    heard = []

    def extract(request):
        heard.append(request)
        return _facts(request)

    guard = Guard.from_mandate(_l2(key, {}, [_checkout(REQUEST)]), _jwk(key),
                               claimed="White ASICS, size 42.", extract=extract)
    result = guard.check([{**SHOE, "color": "White", "returnable": True}])
    # The cart is checked against the signed words, not the agent's.
    assert result["decision"] == "ask" and "black" in result["reasons"][0].lower()
    note = result["notes"][-1]
    assert "colour: the person signed black, the agent says white" in note
    assert "returns: the person signed must be returnable, the agent says not said" in note
    assert "size" not in note
    guard.check([{**SHOE, "returnable": True}])
    assert heard == [REQUEST, "White ASICS, size 42."]   # compared once


def test_the_same_request_in_other_spacing_is_not_a_retelling(key):
    guard = Guard.from_mandate(_l2(key, {}, [_checkout(REQUEST)]), _jwk(key),
                               claimed="  " + REQUEST.replace(" ", "  "), extract=_facts)
    assert guard.check([{**SHOE, "returnable": True}]) == {
        "decision": "proceed", "reasons": [], "refused": [], "question": None, "notes": []}


def test_a_retelling_with_the_same_facts_is_not_flagged(key):
    guard = Guard.from_mandate(_l2(key, {}, [_checkout(REQUEST)]), _jwk(key),
                               claimed="They want black ASICS 42 that can be returned.",
                               extract=_facts)
    assert guard.check([{**SHOE, "returnable": True}])["notes"] == []


def test_a_disputed_fact_is_not_blamed_on_the_agent():
    from asasked.coherence import retelling_differences
    signed = IntentFacts(color="black", disputed=frozenset({"color"}))
    assert retelling_differences(signed, IntentFacts(color="white")) == []
    assert retelling_differences(IntentFacts(other=("gluten-free",)), IntentFacts())[0].text \
        .count("other requirements differ") == 1


def test_the_reworded_demo_is_caught_only_from_the_mandate():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).parent.parent / "scripts" / "demo_reworded.py"
    spec = importlib.util.spec_from_file_location("demo_reworded", path)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    for task in demo.TASKS:
        placed = {name: bool((s := demo.run(task, g)).order and s.order.placed)
                  for name, g in demo.guards(task).items()}
        control = task is demo.TASKS[-1]
        assert placed == {"on the agent's words": True, "from the signed mandate": control}


SOL = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
THIEF = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
SOL_ID = f"solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp:{SOL}"


def _payment(*allowed, payee=None) -> str:
    mandate = {"vct": "mandate.payment.open.1",
               "constraints": [{"type": "mandate.payment.allowed_payees",
                                "allowed": list(allowed)}]}
    if payee is not None:
        mandate = {"vct": "mandate.payment.1", "payee": payee}
    return _disclosure(mandate)


def test_reads_the_approved_address_from_a_payee_disclosure(key):
    # As the VI SDK writes it: the payee is its own disclosure, referenced by digest.
    shop = _enc(["salt-p", {"id": SOL_ID, "name": "Shop", "website": "https://shop.example"}])
    l2 = _l2(key, {}, [shop, _payment({"...": _digest(shop)}), _checkout(REQUEST)])
    assert payees_from_mandate(l2, _jwk(key)) == (SOL,)


def test_reads_inline_and_immediate_mode_payees(key):
    evm = "0x52908400098527886E0F7030069857D2E4169EE7"
    inline = _payment({"id": f"eip155:1:{evm}", "name": "Shop", "website": "https://s.example"})
    assert payees_from_mandate(_l2(key, {}, [inline]), _jwk(key)) == (evm,)
    immediate = _payment(payee={"id": SOL_ID, "name": "Shop", "website": "https://s.example"})
    assert payees_from_mandate(_l2(key, {}, [immediate]), _jwk(key)) == (SOL,)


def test_payees_without_an_address_pin_nothing(key):
    # A merchant id that is not CAIP-10, an undisclosed payee, a checkout mandate
    plain = _payment({"id": "merchant-42", "name": "Shop", "website": "https://s.example"},
                     {"...": "undisclosed-digest"})
    assert payees_from_mandate(_l2(key, {}, [plain, _checkout(REQUEST)]), _jwk(key)) == ()


def test_a_payee_the_signature_does_not_reach_is_ignored(key):
    shop = _enc(["salt-p", {"id": SOL_ID, "name": "Shop", "website": "https://s.example"}])
    payment = _payment({"...": _digest(shop)})
    l2 = _l2(key, {}, [payment])            # signed without the payee disclosure
    added = l2 + _enc(["salt-x", {"id": f"solana:x:{THIEF}", "name": "T", "website": "t"}]) + "~"
    assert payees_from_mandate(added, _jwk(key)) == ()


def test_from_mandate_pins_the_signed_address(key):
    shop = _enc(["salt-p", {"id": SOL_ID, "name": "Shop", "website": "https://s.example"}])
    l2 = _l2(key, {}, [shop, _payment({"...": _digest(shop)}), _checkout(REQUEST)])
    facts = IntentFacts(brand="ASICS", color="black", size_label="42")
    guard = Guard.from_mandate(l2, _jwk(key), extract=lambda _r: facts)
    assert guard.payees == (SOL,)
    forged = {"token": "USDC", "amount": 159.0, "to": THIEF, "merchant": THIEF, "rate": 1.0}
    shoe = {**SHOE, "returnable": True}
    assert guard.check([shoe], payment=forged)["decision"] == "refuse"
    assert guard.check([shoe], payment={**forged, "to": SOL})["decision"] == "proceed"
    # payees= passed by the caller wins over the mandate's
    assert Guard.from_mandate(l2, _jwk(key), payees=[THIEF]).payees == (THIEF,)
