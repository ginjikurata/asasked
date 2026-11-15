"""The payee binding from an ENS name the 402 declares (x402 payee-name).

A 402 may name the operator behind its payTo with an ENS name:
extensions["payee-name"].info.name. Only the name's owner can set its
records, on Ethereum, so they say, apart from the 402, which origins may
declare the name and which addresses it pays to (wg-identity/issues/36, spec
github.com/RWA-ID/x402-Identity/blob/main/specs/extensions/payee-name.md):

    org.x402.origins   text: space-separated origins allowed to declare it
    addr(coinType)     the payout address on that chain (ENSIP-9/11), with
                       the ENSIP-19 default EVM address for any EVM chain
                       without one of its own
    org.x402.payto     text: space-separated CAIP-10 accounts, more payees

The check: the name is a plain lowercase .eth name, it hasn't expired (an
expired name still resolves), the origin the agent contacted is listed
exactly, and the payTo is listed for the network. Mapped onto the outcomes
of wg-identity/issues/42 as the spec does:

    bound         origin and payTo both listed by an unexpired name;
    excluded      the origin is listed and the name lists payees for this
                  network, but not this payTo. The one way a site can say
                  "that address isn't mine", so the guard refuses;
    inconclusive  everything else, including an origin the name doesn't list
                  (the server declared a name that never authorized it: the
                  name says nothing about this site) and a read that didn't
                  finish. A failed read is never an unset record.

The limit of bound: the 402 picks the name, and a name's owner may list any
origin. So someone who can change the 402 can declare a name of their own
that lists this site and their address. bound says who vouches (the name is
in the detail); it is weaker than a list the person approved (Guard(payees=)),
which always wins, and the guard only drops the "address unchecked" note for
it. excluded has no such gap: an attacker gains nothing by declaring a name
that excludes their own address.

Names are taken as declared and only when already plain: lowercase a-z, 0-9
and hyphens, under .eth. A name with capitals is not normalized (refused as
evidence, inconclusive); anything else non-ASCII is inconclusive, since
checking ENSIP-15 normalization would need its tables. CCIP-Read (records
served off-chain) isn't followed: inconclusive.

This module reads Ethereum mainnet over JSON-RPC: the ENS Universal
Resolver for the records, and the ETH registry (ENSv2), BaseRegistrar,
ENS registry and NameWrapper for the expiry. By default through a public
node (DEFAULT_RPC), which then sees the name; pass rpc= for your own.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .payee_binding import BOUND, EXCLUDED, INCONCLUSIVE, Binding, _Unavailable

METHOD = "x402-payee-name"
EXTENSION = "payee-name"
ORIGINS_KEY = "org.x402.origins"
PAYTO_KEY = "org.x402.payto"
DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
TIMEOUT = 10

UNIVERSAL_RESOLVER = "0xeEeEEEeE14D718C2B47D9923Deab1335E144EeEe"
ENS_REGISTRY = "0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e"
NAME_WRAPPER = "0xD4416b13d2b3a9aBae7AcD5D6C2BbDBE25686401"
BASE_REGISTRAR = "0x57f1887a8BF19b14fC0dF6Fd9B2acc9Af147eA85"
ETH_REGISTRY_V2 = "0xf60aba43E1f7F3DAB1186Ff03B561401C9Df85E2"

DAY = 24 * 60 * 60
V1_GRACE, V2_GRACE = 90 * DAY, 28 * DAY
V2_AVAILABLE, V2_REGISTERED = 0, 2
PARENT_CANNOT_CONTROL = 0x10000
SOLANA_MAINNET = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
DEFAULT_EVM_COIN = 0x80000000


# --- Keccak-256 (Ethereum's, not NIST SHA3-256) ---------------------------------

_RC = (0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
       0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008)
_ROT = ((0, 36, 3, 41, 18), (1, 44, 10, 45, 2), (62, 6, 43, 15, 61), (28, 55, 25, 21, 56),
        (27, 20, 39, 8, 14))
_M = (1 << 64) - 1


def _rol(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _M


def _permute(a: list[int]) -> None:
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for i in range(25):
            a[i] ^= d[i % 5]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(a[x + 5 * y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x + 5 * y] = b[x + 5 * y] ^ (~b[(x + 1) % 5 + 5 * y] & b[(x + 2) % 5 + 5 * y])
        a[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data) + b"\x01"
    padded += b"\x00" * (-len(padded) % rate)
    padded[-1] |= 0x80
    state = [0] * 25
    for off in range(0, len(padded), rate):
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(padded[off + 8 * i:off + 8 * i + 8], "little")
        _permute(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


def namehash(name: str) -> bytes:
    node = b"\x00" * 32
    for label in reversed(name.split(".")):
        node = keccak256(node + keccak256(label.encode()))
    return node


def _selector(signature: str) -> bytes:
    return keccak256(signature.encode())[:4]


# --- ABI, as much as these calls need -----------------------------------------------

def _word(n: int) -> bytes:
    return n.to_bytes(32, "big")


def _dyn(b: bytes) -> bytes:
    return _word(len(b)) + b + b"\x00" * (-len(b) % 32)


def _read_dyn(data: bytes, at: int) -> bytes:
    start = int.from_bytes(data[at:at + 32], "big")
    length = int.from_bytes(data[start:start + 32], "big")
    out = data[start + 32:start + 32 + length]
    if len(out) != length:
        raise _Unavailable("A malformed answer from Ethereum.")
    return out


def _dns_encode(name: str) -> bytes:
    return b"".join(bytes([len(label)]) + label.encode() for label in name.split(".")) + b"\x00"


_RESOLVE = _selector("resolve(bytes,bytes)")
_TEXT = _selector("text(bytes32,string)")
_ADDR = _selector("addr(bytes32,uint256)")
# Universal Resolver errors that mean "no such record", not "the read failed".
_UNSET = {_selector("ResolverNotFound(bytes)"), _selector("ResolverNotContract(bytes,address)"),
          _selector("UnsupportedResolverProfile(bytes4)")}
_OFFCHAIN = _selector("OffchainLookup(address,string[],bytes,bytes4,bytes)")


class Reverted(Exception):
    """The call reverted; .data is the revert data."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data.hex())
        self.data = data


# --- Reading Ethereum ---------------------------------------------------------------

class RpcReader:
    """The reads the check needs, over JSON-RPC. call(to, data) -> bytes
    raises Reverted on a revert and _Unavailable when the read didn't finish."""

    def __init__(self, rpc: str = DEFAULT_RPC, timeout: float = TIMEOUT,
                 post: Callable[[dict], dict] | None = None) -> None:
        self.rpc, self.timeout = rpc, timeout
        self._post = post or self._http

    def _http(self, body: dict) -> dict:
        request = urllib.request.Request(self.rpc, json.dumps(body).encode(), {
            "Content-Type": "application/json", "User-Agent": "asasked-payee-check/1"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read(1024 * 1024))
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise _Unavailable(f"Ethereum RPC didn't answer: {e}") from None

    def _request(self, method: str, params: list):
        answer = self._post({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if not isinstance(answer, dict):
            raise _Unavailable("Ethereum RPC gave a malformed answer.")
        error = answer.get("error")
        if error is not None:
            data = error.get("data") if isinstance(error, dict) else None
            if isinstance(data, str) and data.startswith("0x") and "revert" in str(
                    error.get("message", "")).lower():
                raise Reverted(bytes.fromhex(data[2:]))
            raise _Unavailable(f"Ethereum RPC refused the read: {error}")
        return answer.get("result")

    def call(self, to: str, data: bytes) -> bytes:
        result = self._request("eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise _Unavailable("Ethereum RPC gave a malformed answer.")
        return bytes.fromhex(result[2:])

    def now(self) -> int:
        block = self._request("eth_getBlockByNumber", ["latest", False])
        try:
            return int(block["timestamp"], 16)
        except (TypeError, KeyError, ValueError):
            raise _Unavailable("Ethereum RPC gave a malformed block.") from None

    def _uint(self, to: str, data: bytes) -> int:
        out = self.call(to, data)
        if len(out) < 32:
            raise _Unavailable("A malformed answer from Ethereum.")
        return int.from_bytes(out[:32], "big")

    def _resolve(self, name: str, inner: bytes) -> bytes | None:
        """The resolver's answer through the Universal Resolver, or None when
        the name has no resolver or the resolver has no such record kind."""
        encoded = _dns_encode(name)
        data = _RESOLVE + _word(64) + _word(64 + len(_dyn(encoded))) + _dyn(encoded) + _dyn(inner)
        try:
            out = self.call(UNIVERSAL_RESOLVER, data)
        except Reverted as e:
            if e.data[:4] in _UNSET:
                return None
            if e.data[:4] == _OFFCHAIN:
                raise _Unavailable("The name's records are served off-chain (CCIP-Read), "
                                   "which this check doesn't follow.") from None
            raise _Unavailable(f"The name's resolver failed ({e.data[:4].hex() or 'no data'}).") from None
        return _read_dyn(out, 0)

    def text(self, name: str, key: str) -> str | None:
        out = self._resolve(name, _TEXT + namehash(name) + _word(64) + _dyn(key.encode()))
        if out is None:
            return None
        value = _read_dyn(out, 0).decode("utf-8", "replace")
        return value or None

    def addr(self, name: str, coin_type: int) -> bytes | None:
        out = self._resolve(name, _ADDR + namehash(name) + _word(coin_type))
        if out is None:
            return None
        value = _read_dyn(out, 0)
        return value if value.strip(b"\x00") else None

    def registry_owner(self, name: str) -> str:
        out = self.call(ENS_REGISTRY, _selector("owner(bytes32)") + namehash(name))
        return "0x" + out[12:32].hex()

    def wrapper_data(self, name: str) -> tuple[str, int, int]:
        out = self.call(NAME_WRAPPER, _selector("getData(uint256)") + namehash(name))
        if len(out) < 96:
            raise _Unavailable("A malformed answer from Ethereum.")
        return ("0x" + out[12:32].hex(), int.from_bytes(out[32:64], "big"),
                int.from_bytes(out[64:96], "big"))

    def second_level(self, label: str) -> tuple[int, int]:
        """(expiry, grace) of a .eth second-level name, ENSv2-aware."""
        labelhash = keccak256(label.encode())
        status = self._uint(ETH_REGISTRY_V2, _selector("getStatus(uint256)") + labelhash)
        if status == V2_REGISTERED:
            return self._uint(ETH_REGISTRY_V2, _selector("getExpiry(uint256)") + labelhash), V2_GRACE
        expiry = self._uint(BASE_REGISTRAR, _selector("nameExpires(uint256)") + labelhash)
        # Available in ENSv2 means released: no grace left, whatever v1 says.
        return expiry, 0 if status == V2_AVAILABLE else V1_GRACE


# --- The check ----------------------------------------------------------------------

_LABEL = re.compile(r"[a-z0-9-]+")
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def declared_name(payment_required) -> str | None:
    """extensions["payee-name"].info.name of a 402 (a dict or x402's object)."""
    extensions = (payment_required.get("extensions") if isinstance(payment_required, dict)
                  else getattr(payment_required, "extensions", None))
    if not isinstance(extensions, dict):
        return None
    info = (extensions.get(EXTENSION) or {})
    info = info.get("info") if isinstance(info, dict) else None
    name = info.get("name") if isinstance(info, dict) else None
    return name if isinstance(name, str) else None


def _name_problem(name: str) -> tuple[str, str] | None:
    if not name.isascii():
        return "unsupported-name", f"{name!r} isn't plain ASCII; this check reads only plain .eth names."
    labels = name.split(".")
    if name != name.lower() or any(not label for label in labels):
        return "name-not-normalized", f"{name!r} isn't in normalized form."
    if len(labels) < 2 or labels[-1] != "eth":
        return "unsupported-name", f"{name} isn't under .eth."
    for label in labels:
        if not _LABEL.fullmatch(label) or label[2:4] == "--":
            return "unsupported-name", f"{name!r} isn't a plain name this check can read."
    return None


def web_origin(value: str) -> str | None:
    """RFC 6454 serialization of an http(s) URL or origin, or None."""
    try:
        parts = urllib.parse.urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("https", "http") or not parts.hostname:
        return None
    default = 443 if parts.scheme == "https" else 80
    host = parts.hostname.lower()
    return f"{parts.scheme}://{host}" + (f":{port}" if port and port != default else "")


def coin_type(network: str) -> int | None:
    if network == SOLANA_MAINNET:
        return 501
    m = re.fullmatch(r"eip155:(\d+)", network)
    if not m:
        return None
    chain = int(m.group(1))
    return 60 if chain == 1 else (DEFAULT_EVM_COIN | chain)


def _base58(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def _record_account(network: str, raw: bytes) -> str | None:
    if network == SOLANA_MAINNET:
        return _base58(raw) if len(raw) == 32 else None
    if network.startswith("eip155:"):
        return "0x" + raw.hex() if len(raw) == 20 else None
    return None


def _same(network: str, a: str, b: str) -> bool:
    if network.startswith("eip155:"):
        return a.lower() == b.lower()
    return a == b


@dataclass(frozen=True)
class _Records:
    now: int
    origins: list[str]
    payto: list[str]
    primary: str | None        # the address record for this network, as payTo would read
    expiry: int
    grace: int
    registered: bool
    parent_can_control: bool


def _read(reader, name: str, network: str) -> _Records:
    labels = name.split(".")
    path = [".".join(labels[i:]) for i in range(len(labels) - 1)]   # name .. second level
    now = reader.now()
    origins = (reader.text(name, ORIGINS_KEY) or "").split()
    payto = (reader.text(name, PAYTO_KEY) or "").split()
    coin = coin_type(network)
    raw = reader.addr(name, coin) if coin is not None else None
    if raw is None and network.startswith("eip155:"):
        # ENSIP-19's default EVM address, which most resolvers don't apply themselves.
        raw = reader.addr(name, DEFAULT_EVM_COIN)
    primary = _record_account(network, raw) if raw is not None else None
    expiry, grace = reader.second_level(labels[-2])
    registered = expiry != 0
    parent_can_control = False
    for node in path[:-1]:
        if reader.registry_owner(node).lower() != NAME_WRAPPER.lower():
            parent_can_control = True
            continue
        owner, fuses, ends_at = reader.wrapper_data(node)
        burned = bool(fuses & PARENT_CANNOT_CONTROL)
        parent_can_control = parent_can_control or not burned
        # A wrapped subname's own expiry ends it only with the fuse burned; past
        # it, NameWrapper zeroes fuses, and the zeroed owner shows it ended.
        ended = burned if ends_at > now else int(owner, 16) == 0
        if ended and ends_at < expiry + grace:
            expiry, grace = ends_at, 0
    return _Records(now, origins, payto, primary, expiry, grace, registered, parent_can_control)


def check_payee_name(name: str, origin: str, network: str, pay_to: str, *,
                     reader=None, rpc: str = DEFAULT_RPC, timeout: float = TIMEOUT) -> Binding:
    """Checks pay_to against the ENS name a 402 declared (see the module).

    origin is the site the agent contacted, never the resource URL the 402
    names. reader replaces the Ethereum reads (tests, your own client); it
    needs now(), text(), addr(), second_level(), registry_owner() and
    wrapper_data() as RpcReader has them.
    """
    contacted = web_origin(origin)
    if contacted is None:
        raise ValueError(f"origin must be an http(s) site, got {origin!r}")

    def answer(outcome: str, reason: str, detail: str) -> Binding:
        return Binding(outcome, reason, contacted, network, pay_to, method=METHOD, detail=detail)

    problem = _name_problem(name)
    if problem:
        return answer(INCONCLUSIVE, *problem)
    reader = reader or RpcReader(rpc, timeout)
    try:
        r = _read(reader, name, network)
    except (_Unavailable, Reverted) as e:
        why = str(e) if isinstance(e, _Unavailable) else "An ENS contract refused the read."
        return answer(INCONCLUSIVE, "resolution-failed", f"{name}: {why}")

    until = datetime.fromtimestamp(r.expiry, timezone.utc).strftime("%Y-%m-%d")
    if r.now >= r.expiry + r.grace:
        if not r.registered:
            return answer(INCONCLUSIVE, "name-expired", f"{name} isn't registered.")
        return answer(INCONCLUSIVE, "name-expired", f"{name} expired on {until}.")
    if r.now >= r.expiry:
        return answer(INCONCLUSIVE, "name-in-grace", f"{name} expired on {until} and is in its grace period.")
    if not r.origins and not r.payto and r.primary is None:
        return answer(INCONCLUSIVE, "no-records", f"{name} sets none of the payee records.")
    if contacted not in {web_origin(o) for o in r.origins}:
        # The server declared a name that never authorized it: no statement
        # about this site, so no exclusion either; and the name isn't its.
        return answer(INCONCLUSIVE, "origin-not-listed",
                      f"{name} doesn't list {contacted}, so the name isn't this site's.")

    note = f" Valid until {until}."
    if r.parent_can_control:
        note += " Its parent name can still change these records."
    if r.primary is not None and _same(network, r.primary, pay_to):
        return answer(BOUND, "payee-bound", f"{name} lists {contacted} and {pay_to} for {network}.{note}")
    listed = [e.rsplit(":", 1) for e in r.payto if ":" in e]
    if any(net == network and _same(network, account, pay_to) for net, account in listed):
        return answer(BOUND, "payee-bound",
                      f"{name} lists {contacted} and {pay_to} for {network} ({PAYTO_KEY}).{note}")
    if r.primary is not None or any(net == network for net, _ in listed):
        return answer(EXCLUDED, "payto-not-listed",
                      f"{name} lists {contacted} and other addresses for {network}, not {pay_to}.{note}")
    return answer(INCONCLUSIVE, "payto-not-listed", f"{name} lists no payee for {network}.{note}")


__all__ = ["DEFAULT_RPC", "RpcReader", "check_payee_name", "coin_type", "declared_name",
           "keccak256", "namehash", "web_origin"]
