"""The ENS payee-name check, with Ethereum replaced by a dict of records."""

import pytest

from asasked.payee_binding import BOUND, EXCLUDED, INCONCLUSIVE, PayeeChecker, check_payee
from asasked.payee_name import (DEFAULT_EVM_COIN, NAME_WRAPPER, PARENT_CANNOT_CONTROL,
                                RpcReader, _dns_encode, check_payee_name, coin_type,
                                declared_name, keccak256, namehash)
from asasked.payee_binding import _Unavailable

NOW = 1_794_731_567
YEAR = 365 * 24 * 60 * 60
NAME = "pay.weather.eth"
SITE = "https://api.weather.example"
BASE = "eip155:8453"
SOL = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
OURS = "0x8e61630a73a38b5a1b7ae8daa8aead364403631c"
THEIRS = "0x1111111111111111111111111111111111111111"


class Chain:
    """Records of names on a pretend Ethereum, read as RpcReader reads them."""

    def __init__(self, text=None, addr=None, expiry=NOW + YEAR, grace=90 * 86400,
                 wrapped=None, down=False):
        self.texts = text or {}
        self.addrs = addr or {}
        self.expiry, self.grace = expiry, grace
        self.wrapped = wrapped or {}          # name -> (owner, fuses, expiry)
        self.down = down

    def now(self):
        if self.down:
            raise _Unavailable("no answer")
        return NOW

    def text(self, name, key):
        return self.texts.get(key)

    def addr(self, name, coin):
        return self.addrs.get(coin)

    def second_level(self, label):
        return self.expiry, self.grace

    def registry_owner(self, name):
        return NAME_WRAPPER if name in self.wrapped else "0x" + "22" * 20

    def wrapper_data(self, name):
        return self.wrapped[name]


def records(origins=SITE, payto=None, base=OURS, **kwargs):
    text = {"org.x402.origins": origins}
    if payto:
        text["org.x402.payto"] = payto
    addr = {coin_type(BASE): bytes.fromhex(base[2:])} if base else {}
    return Chain(text, addr, **kwargs)


def check(chain, pay_to=OURS, origin=SITE, network=BASE, name=NAME):
    return check_payee_name(name, origin, network, pay_to, reader=chain)


def test_keccak_and_namehash_match_ethereum():
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert namehash("eth").hex() == "93cdeb708b7545dc668eb9280176169d1c33cfd8ed6f04690a0bcc88a93fc4ae"
    assert namehash("foo.eth").hex() == "de9b09fd7c5f901e23a3f19fecc54828e9c848539801e86591bd9801b019f84f"
    assert _dns_encode("pay.eth") == b"\x03pay\x03eth\x00"


def test_coin_types():
    assert coin_type("eip155:1") == 60
    assert coin_type(BASE) == 0x80000000 | 8453
    assert coin_type(SOL) == 501
    assert coin_type("solana:devnet") is None


def test_listed_origin_and_address_bind():
    binding = check(records())
    assert (binding.outcome, binding.reason, binding.method) == (BOUND, "payee-bound", "x402-payee-name")
    assert NAME in binding.detail and binding.origin == SITE


def test_evm_case_is_only_a_checksum():
    assert check(records(), pay_to=OURS.upper().replace("0X", "0x")).outcome == BOUND


def test_another_address_for_the_network_is_excluded():
    binding = check(records(), pay_to=THEIRS)
    assert (binding.outcome, binding.reason) == (EXCLUDED, "payto-not-listed")


def test_payto_list_binds_and_excludes():
    chain = records(base=None, payto=f"{BASE}:{THEIRS} eip155:1:{OURS}")
    assert check(chain, pay_to=THEIRS).outcome == BOUND
    assert check(chain, pay_to=OURS).outcome == EXCLUDED     # listed for mainnet, not Base


def test_no_payee_for_the_network_is_inconclusive():
    binding = check(records(base=None, payto=f"eip155:1:{OURS}"), network="eip155:10")
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "payto-not-listed")


def test_default_evm_address_applies_to_any_evm_chain():
    chain = Chain({"org.x402.origins": SITE}, {DEFAULT_EVM_COIN: bytes.fromhex(OURS[2:])})
    assert check(chain, network="eip155:42161").outcome == BOUND
    assert check(chain, network="eip155:42161", pay_to=THEIRS).outcome == EXCLUDED


def test_solana_address_is_compared_as_base58():
    key = bytes(range(1, 33))
    from asasked.payee_name import _base58
    chain = Chain({"org.x402.origins": SITE}, {501: key})
    assert check(chain, network=SOL, pay_to=_base58(key)).outcome == BOUND
    assert check(chain, network=SOL, pay_to=_base58(key).lower()).outcome == EXCLUDED


def test_origin_not_listed_says_nothing_about_this_site():
    binding = check(records(origins="https://other.example"), pay_to=THEIRS)
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "origin-not-listed")


@pytest.mark.parametrize("contacted, listed, same", [
    ("https://API.weather.example/pay", "https://api.weather.example", True),
    ("https://api.weather.example:443", "https://api.weather.example", True),
    ("https://api.weather.example:8443", "https://api.weather.example", False),
    ("https://shop.weather.example", "https://weather.example", False),     # no wildcards
    ("http://api.weather.example", "https://api.weather.example", False),
])
def test_origins_match_exactly(contacted, listed, same):
    binding = check(records(origins=listed), origin=contacted)
    assert (binding.outcome == BOUND) is same


def test_expired_and_unregistered_names():
    expired = check(records(expiry=NOW - 100 * 86400, grace=90 * 86400))
    assert (expired.outcome, expired.reason) == (INCONCLUSIVE, "name-expired")
    unregistered = check(records(expiry=0, grace=0))
    assert unregistered.reason == "name-expired" and "isn't registered" in unregistered.detail


def test_name_in_grace_is_inconclusive_even_if_records_match():
    binding = check(records(expiry=NOW - 86400, grace=28 * 86400))
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "name-in-grace")


def test_no_records():
    binding = check(Chain())
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "no-records")


def test_failed_read_is_never_unset():
    binding = check(records(down=True), pay_to=THEIRS)
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, "resolution-failed")


@pytest.mark.parametrize("name, reason", [
    ("Pay.weather.eth", "name-not-normalized"),
    ("pay..eth", "name-not-normalized"),
    ("pay.weather.com", "unsupported-name"),
    ("eth", "unsupported-name"),
    ("pаy.eth", "unsupported-name"),         # Cyrillic а
    ("xn--pay-1sa.eth", "unsupported-name"),
    ("pay_me.eth", "unsupported-name"),
])
def test_names_this_check_wont_read(name, reason):
    binding = check(records(), name=name)
    assert (binding.outcome, binding.reason) == (INCONCLUSIVE, reason)


def test_wrapped_subname_ends_at_its_own_expiry_only_with_the_fuse_burned():
    owner = "0x" + "33" * 20
    soon = NOW + 86400
    burned = records(wrapped={NAME: (owner, PARENT_CANNOT_CONTROL, NOW - 1)})
    # Past its expiry NameWrapper zeroes the owner; we read the zero.
    burned.wrapped[NAME] = ("0x" + "00" * 20, 0, NOW - 1)
    assert check(burned).reason == "name-expired"
    alive = records(wrapped={NAME: (owner, PARENT_CANNOT_CONTROL, soon)})
    binding = check(alive)
    assert binding.outcome == BOUND and "parent" not in binding.detail
    controlled = records(wrapped={NAME: (owner, 0, NOW - 1)})
    binding = check(controlled)
    assert binding.outcome == BOUND and "parent name can still change" in binding.detail


def test_unwrapped_subname_notes_the_parent_can_change_it():
    assert "parent name can still change" in check(records()).detail


def test_declared_name_from_a_dict_or_an_object():
    assert declared_name({"extensions": {"payee-name": {"info": {"name": NAME}}}}) == NAME
    assert declared_name({"extensions": {"payee-name": {"info": {}}}}) is None
    assert declared_name({}) is None

    class Required:
        extensions = {"payee-name": {"info": {"name": NAME}}}
    assert declared_name(Required()) == NAME


def no_manifest(url):
    return 404, b""


def test_check_payee_tries_the_name_first_then_the_manifest():
    excluded = check_payee(SITE, BASE, THEIRS, name=NAME, reader=records(), get=no_manifest)
    assert excluded.outcome == EXCLUDED
    unlisted = check_payee(SITE, BASE, OURS, name=NAME, reader=records(origins="https://x.example"),
                           get=no_manifest)
    assert unlisted.reason == "origin-not-listed" and "no-manifest" in unlisted.detail
    assert check_payee(SITE, BASE, OURS, get=no_manifest).method == "x402-signed-manifest"


def test_checker_keeps_ens_answers_no_longer_than_the_402_lives(monkeypatch):
    reads = []

    class Counting(Chain):
        def now(self):
            reads.append(1)
            return NOW

    chain = Counting({"org.x402.origins": SITE}, {coin_type(BASE): bytes.fromhex(OURS[2:])})
    checker = PayeeChecker(reader=chain, get=no_manifest)
    clock = [1000.0]
    monkeypatch.setattr("asasked.payee_binding.time.monotonic", lambda: clock[0])
    checker(SITE, BASE, OURS, name=NAME, max_age=60)
    checker(SITE, BASE, OURS, name=NAME, max_age=60)
    assert len(reads) == 1
    clock[0] += 61
    checker(SITE, BASE, OURS, name=NAME, max_age=60)
    assert len(reads) == 2
    assert checker(SITE, BASE, OURS, name=None).method == "x402-signed-manifest"


def rpc(answers):
    """A JSON-RPC endpoint answering eth_call by (to, selector)."""
    def post(body):
        if body["method"] == "eth_getBlockByNumber":
            return {"result": {"timestamp": hex(NOW)}}
        call = body["params"][0]
        answer = answers(call["to"].lower(), bytes.fromhex(call["data"][2:]))
        if isinstance(answer, Exception):
            return {"error": {"code": 3, "message": "execution reverted", "data": "0x" + answer.args[0]}}
        return {"result": "0x" + answer.hex()}
    return post


def test_rpc_reader_treats_resolver_not_found_as_unset_and_offchain_as_failed():
    def not_found(to, data):
        return Exception("77209fe8" + "00" * 32)
    reader = RpcReader(post=rpc(not_found))
    assert reader.text(NAME, "org.x402.origins") is None
    assert reader.addr(NAME, 60) is None

    def offchain(to, data):
        return Exception("556f1830" + "00" * 32)
    with pytest.raises(_Unavailable):
        RpcReader(post=rpc(offchain)).text(NAME, "org.x402.origins")


def test_rpc_reader_decodes_the_universal_resolvers_answer():
    def word(n):
        return n.to_bytes(32, "big")

    def dyn(b):
        return word(len(b)) + b + b"\x00" * (-len(b) % 32)

    def answer(to, data):
        inner = dyn(SITE.encode())                       # text() returns (string)
        inner = word(32) + inner
        return word(64) + word(0) + dyn(inner)          # (bytes result, address resolver)
    assert RpcReader(post=rpc(answer)).text(NAME, "org.x402.origins") == SITE


def test_rpc_failure_is_unavailable():
    def down(body):
        raise _Unavailable("timed out")
    binding = check_payee_name(NAME, SITE, BASE, OURS, reader=RpcReader(post=down))
    assert binding.reason == "resolution-failed"
