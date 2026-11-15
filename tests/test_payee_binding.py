"""The payee check against the signed-manifest reference kit's own test vector
(github.com/magentixai/x402-signed-manifest-ref, Apache-2.0), with the
network replaced by stubs."""

import hashlib
import json

import pytest

from asasked.payee_binding import (BOUND, INCONCLUSIVE, Binding, PayeeChecker, canonical_bytes,
                                   check_payee)

HOST = "x402.magentix.ai"
ORIGIN = f"https://{HOST}"
NET = "eip155:8453"
PAY_TO = "0x8cbEEe7CD026F1CaAA041FB35d9fdE705dB503C2"
OTHER = "0x1111111111111111111111111111111111111111"

MANIFEST = (
    '{"x402Version":2,"resources":[{"path":"/example","price":"0.01","asset":"USDC",'
    '"network":"eip155:8453"}],"payTo":{"eip155:8453":"0x8cbEEe7CD026F1CaAA041FB35d9fdE705dB503C2"},'
    '"acceptedNetworks":["eip155:8453"],"host":{"role":"origin","settlementAddresses":'
    '{"eip155:8453":["0x8cbEEe7CD026F1CaAA041FB35d9fdE705dB503C2"]}},'
    '"version":{"descriptorVersion":1,"issuedAt":"2026-08-11T00:00:00Z"}}')
DIGEST = "d743be2828e4019640e0f30748a49b81f624fffbacbe2a436b367d4428bb681c"
SIG = "VJ0T6As3Jofbgdwz3yLYEzVhTCoiGLVD4WvU5IgJY6lB4v7LZdhluyz3rH7AiZdAc_b0ZLPGQe9YJjJ_CILcCg"
KID = "s1._x402key.x402.magentix.ai"
KEY = "_CZl4qb5azp7U-EL4QAFDh6PwXUdmthCo5sLYV6FzFU"


def signature(**changes):
    doc = {"v": "x402sig1", "canon": "RFC8785-JCS", "sig_input": "canonical-bytes",
           "alg": "Ed25519", "kid": KID, "sig": SIG,
           "content_digest": {"alg": "SHA-256", "value": DIGEST},
           "signedAt": "2026-08-14T15:59:01Z"}
    doc.update(changes)
    return json.dumps({k: v for k, v in doc.items() if v is not None}).encode()


def site(manifest=MANIFEST, sig=None, status=200, sig_status=200, fail=False):
    asked = []

    def get(url):
        asked.append(url)
        if fail:
            from asasked.payee_binding import _Unavailable
            raise _Unavailable(f"{url}: connection refused")
        if url == f"{ORIGIN}/.well-known/x402":
            return status, manifest.encode() if isinstance(manifest, str) else manifest
        if url == f"{ORIGIN}/.well-known/x402.sig":
            return sig_status, signature() if sig is None else sig
        return 404, b""
    get.asked = asked
    return get


def dns(records=None, fail=False):
    def txt(name):
        if fail:
            raise OSError("SERVFAIL")
        if name == KID:
            return [f"v=x402key1; alg=Ed25519; k={KEY}"] if records is None else records
        return []
    return txt


def check(pay_to=PAY_TO, network=NET, get=None, txt=None, origin=ORIGIN):
    return check_payee(origin, network, pay_to, get=get or site(), txt=txt or dns())


# --- Canonical form -------------------------------------------------------------

def test_reference_manifest_canonical_digest():
    assert hashlib.sha256(canonical_bytes(json.loads(MANIFEST))).hexdigest() == DIGEST


@pytest.mark.parametrize("value, text", [
    (0, "0"), (-0.0, "0"), (1.0, "1"), (100.0, "100"), (123.45, "123.45"), (0.001, "0.001"),
    (1e-6, "0.000001"), (1e-7, "1e-7"), (1.5e-7, "1.5e-7"), (1e21, "1e+21"),
    (1e20, "100000000000000000000"), (12345678901234567890.0, "12345678901234567000"),
    (-2.5, "-2.5"), (2 ** 53, "9007199254740992"), (4.5e300, "4.5e+300"),
    (0.1 + 0.2, "0.30000000000000004"),
])
def test_numbers_as_ecmascript_writes_them(value, text):
    assert canonical_bytes(value).decode() == text


def test_keys_sorted_by_utf16_and_strings_escaped():
    # RFC 8785 section 3.2.3: U+1F600 (surrogates D83D DE00) sorts before U+FB33.
    value = {"דּ": 1, "\U0001f600": 2, "b": "a\"\\\n\x01é", "a": [True, None]}
    assert canonical_bytes(value).decode() == (
        '{"a":[true,null],"b":"a\\"\\\\\\n\\u0001é","\U0001f600":2,"דּ":1}')


def test_no_nan():
    with pytest.raises(ValueError):
        canonical_bytes(float("nan"))


# --- Outcomes -------------------------------------------------------------------

def test_reference_site_binds_its_address():
    binding = check()
    assert (binding.outcome, binding.reason) == (BOUND, "payee-bound")
    assert binding.origin == ORIGIN and binding.network == NET and binding.pay_to == PAY_TO


def test_evm_case_is_only_a_checksum():
    assert check(pay_to=PAY_TO.lower()).outcome == BOUND


def test_unlisted_address_is_inconclusive_not_excluded():
    # The manifest doesn't say its list is complete.
    binding = check(pay_to=OTHER)
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "payto-not-listed")
    assert "other addresses" in binding.detail


def test_other_network_is_inconclusive():
    binding = check(network="solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp")
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "payto-not-listed")
    assert "no address" in binding.detail


def test_flipped_signature_is_invalid():
    bad = SIG[:10] + ("A" if SIG[10] != "A" else "B") + SIG[11:]
    binding = check(get=site(sig=signature(sig=bad)))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "signature-invalid")


def test_changed_manifest_is_canon_mismatch_not_invalid():
    # Our digest no longer matches the published one: the fault may be ours.
    changed = MANIFEST.replace(PAY_TO, OTHER)
    binding = check(pay_to=OTHER, get=site(manifest=changed))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "canon-mismatch")


def test_no_signature_file():
    assert check(get=site(sig_status=404)).reason == "unsigned"


def test_catch_all_json_is_not_a_signature():
    # Hosts that answer every /.well-known path with the same document.
    binding = check(get=site(sig=MANIFEST.encode()))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "unsigned")


def test_key_from_another_domain_authorizes_nothing():
    binding = check(get=site(sig=signature(kid="s1._x402key.attacker.example")))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "unauthorized-signer")


def test_parent_domain_key_is_not_the_hosts():
    binding = check(get=site(sig=signature(kid="s1._x402key.magentix.ai")))
    assert binding.reason == "unauthorized-signer"


def test_trailing_dot_in_kid_is_the_same_name():
    assert check(get=site(sig=signature(kid=KID + "."))).outcome == BOUND


def test_no_key_in_dns():
    assert check(txt=dns(records=[])).reason == "key-not-found"


def test_wrong_key_in_dns():
    other = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    binding = check(txt=dns(records=[f"v=x402key1; alg=Ed25519; k={other}"]))
    assert binding.outcome == INCONCLUSIVE
    assert binding.reason in ("signature-invalid", "key-not-found")


def test_unknown_suite():
    assert check(get=site(sig=signature(alg="RS256"))).reason == "unsupported"


def test_no_manifest():
    assert check(get=site(status=404)).reason == "no-manifest"


def test_unreachable_site_is_resolution_failed():
    binding = check(get=site(fail=True))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "resolution-failed")


def test_dns_failure_is_resolution_failed():
    binding = check(txt=dns(fail=True))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "resolution-failed")


@pytest.mark.parametrize("origin", ["http://x402.magentix.ai", "x402.magentix.ai",
                                    "https://x402.magentix.ai:8443"])
def test_origin_must_be_https_on_default_port(origin):
    with pytest.raises(ValueError):
        check(origin=origin)


def test_origin_path_is_ignored_host_is_lowered():
    get = site()
    binding = check_payee("https://X402.Magentix.AI/some/path", NET, PAY_TO, get=get, txt=dns())
    assert binding.outcome == BOUND and binding.origin == ORIGIN


def test_binding_rejects_unknown_outcome():
    with pytest.raises(ValueError):
        Binding("maybe", "x", ORIGIN, NET, PAY_TO)


# --- Kept answers ---------------------------------------------------------------

def test_checker_keeps_answers_but_not_failed_lookups():
    good = site()
    checker = PayeeChecker(get=good, txt=dns())
    assert checker(ORIGIN, NET, PAY_TO).outcome == BOUND
    assert checker(ORIGIN, NET, PAY_TO).outcome == BOUND
    assert len(good.asked) == 2                 # manifest and signature, once

    down = site(fail=True)
    checker = PayeeChecker(get=down, txt=dns())
    checker(ORIGIN, NET, PAY_TO)
    checker(ORIGIN, NET, PAY_TO)
    assert len(down.asked) == 2                 # tried again
