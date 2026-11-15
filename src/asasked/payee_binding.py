"""Is the address a 402 names really the payee of the site the agent contacted?

A server names its own payTo, so whoever can change the 402 (a hijacked
endpoint, a man in the middle, a compromised deploy) can name their own
address. Guard(payees=...) catches that when the person approved addresses in
advance. An agent that finds sellers itself has no such list; then the site
has to say, in a way checkable apart from the 402, which addresses are its own.

The x402 identity working group states the requirement and its outcomes
(github.com/x402-foundation/wg-identity/issues/42); this module uses them:

    bound         a valid authorization binds this payTo to this origin and
                  network;
    excluded      a valid, current authorization that is complete for this
                  origin and network does not list this payTo;
    inconclusive  anything else: nothing published, a signature that doesn't
                  verify, an unauthorized signer, a lookup that didn't finish.
                  A failed lookup is never excluded.

bound says the site's key holder authorized the address. It does not say the
seller is honest or will deliver.

The mechanism checked here is the signed discovery manifest
(wg-identity/issues/16, reference kit github.com/magentixai/
x402-signed-manifest-ref): the manifest at https://<host>/.well-known/x402, a
detached signature next to it (.sig), Ed25519 over the RFC 8785 canonical
bytes, and the key in DNS at <selector>._x402key.<host>, which the
signature's kid names. The key comes from DNS, not from the site's files, so
someone who can change what the site serves can't sign for it. The kid must
sit under the contacted host itself: a key from another domain authorizes
nothing for this origin. The manifest lists addresses per CAIP-2 network
(payTo and host.settlementAddresses). It doesn't declare the list complete,
so an address it doesn't list is inconclusive, not excluded.

Two verifier rules from that issue are kept. A failed signature is called
invalid only when our canonical digest matches the content digest the
publisher published; otherwise the canonicalizations may differ, and the
fault may be ours (canon-mismatch). And a 200 at the signature path counts as
a signature only if it carries one and a kid.

The guard itself does no network calls. This module does: check_payee()
fetches two files and one DNS record and returns a Binding, which goes into
the payment as payment["binding"] (asasked.payment). X402Guard does that for
you with check_payee=True and origin=. DNS goes through dnspython if it is
installed, otherwise through Cloudflare's DNS-over-HTTPS (the shop's host
name is then sent to Cloudflare); pass txt= to use your own resolver.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

BOUND, EXCLUDED, INCONCLUSIVE = "bound", "excluded", "inconclusive"
OUTCOMES = (BOUND, EXCLUDED, INCONCLUSIVE)

METHOD = "x402-signed-manifest"
MANIFEST_PATH = "/.well-known/x402"
DOH_URL = "https://cloudflare-dns.com/dns-query"
TIMEOUT = 10
# Bigger than any manifest; a server can't make the check read without end.
MAX_BYTES = 256 * 1024
_USER_AGENT = "asasked-payee-check/1"


@dataclass(frozen=True)
class Binding:
    """The answer for one (origin, network, payTo).

    outcome is bound, excluded or inconclusive. reason is the mechanism's own
    word for why (payee-bound, unsigned, canon-mismatch, ...); detail is a
    sentence for a log or for the person.
    """

    outcome: str
    reason: str
    origin: str
    network: str
    pay_to: str
    method: str = METHOD
    detail: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ"))

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"binding outcome must be one of {', '.join(OUTCOMES)}")

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "reason": self.reason, "origin": self.origin,
                "network": self.network, "pay_to": self.pay_to, "method": self.method,
                "detail": self.detail, "checked_at": self.checked_at}


class _Unavailable(Exception):
    """The lookup didn't finish: inconclusive, resolution-failed."""


# --- RFC 8785 (JSON Canonicalization Scheme) ------------------------------------

def _es_number(x) -> str:
    """A JSON number as ECMAScript's Number.prototype.toString writes it."""
    if isinstance(x, bool):
        raise TypeError("not a number")
    if isinstance(x, int):
        if abs(x) > 2 ** 53:
            # JCS numbers are IEEE doubles; a bigger integer is rounded as one.
            x = float(x)
        else:
            return str(x)
    if not math.isfinite(x):
        raise ValueError("JCS has no NaN or Infinity")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    # repr gives the shortest digits that round-trip, as ECMAScript does;
    # only the layout differs.
    digits, exponent = _shortest(abs(x))
    n = exponent + 1          # the decimal point sits after n digits
    k = len(digits)
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    e = n - 1
    head = digits[0] + ("." + digits[1:] if k > 1 else "")
    return f"{sign}{head}e{'+' if e > 0 else '-'}{abs(e)}"


def _shortest(x: float) -> tuple[str, int]:
    """(digits, exponent) of the shortest round-trip form: x = d.ddd × 10^exponent."""
    text = repr(x)
    if "e" in text:
        mantissa, exp = text.split("e")
        exponent = int(exp)
    else:
        mantissa, exponent = text, 0
    whole, _, frac = mantissa.partition(".")
    frac = frac.rstrip("0")
    digits = (whole + frac).lstrip("0")
    # Position of the first significant digit relative to the decimal point.
    if whole.strip("0"):
        exponent += len(whole.lstrip("0")) - 1
    else:
        exponent -= len(frac) - len(frac.lstrip("0")) + 1
    return digits.rstrip("0") or "0", exponent


def canonical_bytes(value) -> bytes:
    """RFC 8785 canonical UTF-8 bytes of a parsed JSON value."""
    return _canonical(value).encode("utf-8")


def _canonical(value) -> str:
    if value is None or value is True or value is False:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return _es_number(value)
    if isinstance(value, str):
        # json.dumps escapes exactly what JCS escapes: " \ and control
        # characters, with the short forms and lowercase \u00xx.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    if isinstance(value, dict):
        # Keys in UTF-16 code unit order.
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + _canonical(value[k])
                              for k in keys) + "}"
    raise TypeError(f"not a JSON value: {type(value).__name__}")


# --- Network -------------------------------------------------------------------

def _get(url: str, timeout: float) -> tuple[int, bytes]:
    """(status, body); a 4xx comes back as its status, anything else raises _Unavailable."""
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            return e.code, b""
        raise _Unavailable(f"{url} answered {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _Unavailable(f"{url}: {e}") from e


def dns_txt(name: str, timeout: float = TIMEOUT) -> list[str]:
    """TXT records of name, each joined from its strings. [] when there are none.

    dnspython if installed, otherwise DNS-over-HTTPS. A lookup that fails
    (not one that finds nothing) raises OSError.
    """
    try:
        import dns.exception
        import dns.resolver
    except ImportError:
        return _doh_txt(name, timeout)
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=timeout)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as e:
        raise OSError(f"DNS lookup of {name} failed: {e}") from e
    return [b"".join(r.strings).decode("utf-8", "replace") for r in answers]


def _doh_txt(name: str, timeout: float) -> list[str]:
    url = f"{DOH_URL}?{urllib.parse.urlencode({'name': name, 'type': 'TXT'})}"
    request = urllib.request.Request(url, headers={"Accept": "application/dns-json",
                                                   "User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            answer = json.loads(response.read(MAX_BYTES))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise OSError(f"DNS lookup of {name} failed: {e}") from e
    status = answer.get("Status")
    if status == 3:                     # NXDOMAIN
        return []
    if status != 0:
        raise OSError(f"DNS lookup of {name} failed: status {status}")
    records = []
    for record in answer.get("Answer") or []:
        if record.get("type") == 16:
            # "part one" "part two" -> part onepart two
            parts = re.findall(r'"((?:[^"\\]|\\.)*)"', record.get("data", ""))
            records.append("".join(parts) if parts else record.get("data", ""))
    return records


# --- The check -----------------------------------------------------------------

def _b64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _tags(record: str) -> dict[str, str]:
    tags = {}
    for part in record.split(";"):
        key, sep, value = part.partition("=")
        if sep:
            tags[key.strip()] = value.strip()
    return tags


def _same_address(a: str, b: str) -> bool:
    if a.lower().startswith("0x") and b.lower().startswith("0x"):
        return a.lower() == b.lower()
    return a == b


def _origin_host(origin: str) -> str:
    parts = urllib.parse.urlsplit(origin.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"origin must be an https URL, got {origin!r}")
    if parts.port not in (None, 443):
        # The key lives under the host name; DNS has no ports.
        raise ValueError(f"origin must be on the default https port, got {origin!r}")
    return parts.hostname.rstrip(".").lower()


def listed_addresses(manifest: dict, network: str) -> list[str]:
    """The addresses a manifest names for a CAIP-2 network."""
    found: list[str] = []
    pay_to = manifest.get("payTo")
    if isinstance(pay_to, dict):
        pay_to = pay_to.get(network)
    if isinstance(pay_to, str):
        found.append(pay_to)
    host = manifest.get("host")
    settlement = host.get("settlementAddresses") if isinstance(host, dict) else None
    listed = settlement.get(network) if isinstance(settlement, dict) else None
    if isinstance(listed, str):
        listed = [listed]
    if isinstance(listed, list):
        found += [a for a in listed if isinstance(a, str)]
    return found


def verify_manifest(manifest_body: bytes, signature_body: bytes, host: str,
                    txt: Callable[[str], list[str]]) -> tuple[str, str, dict | None]:
    """(reason, detail, manifest): reason "authentic" with the parsed manifest,
    or the reason it can't be trusted. Raises _Unavailable when DNS fails."""
    try:
        signature = json.loads(signature_body)
    except ValueError:
        signature = None
    if not isinstance(signature, dict) or not isinstance(signature.get("sig"), str) \
            or not isinstance(signature.get("kid"), str):
        # Many hosts answer every path under /.well-known with the same JSON.
        return "unsigned", "Nothing at the signature path carries a signature and a kid.", None
    kid = signature["kid"].rstrip(".").lower()
    selector, sep, under = kid.partition("._x402key.")
    if not sep or not selector or under != host:
        return ("unauthorized-signer",
                f"The signature names key {signature['kid']}, which is not under {host}.", None)
    suite = (signature.get("v"), signature.get("canon"), signature.get("sig_input"),
             signature.get("alg"))
    if suite != ("x402sig1", "RFC8785-JCS", "canonical-bytes", "Ed25519"):
        return "unsupported", f"The signature uses a suite this check doesn't know: {suite}.", None
    try:
        manifest = json.loads(manifest_body)
    except ValueError:
        return "manifest-unreadable", "The manifest is not JSON.", None
    if not isinstance(manifest, dict):
        return "manifest-unreadable", "The manifest is not a JSON object.", None

    try:
        records = txt(kid)
    except OSError as e:
        raise _Unavailable(str(e)) from e
    keys = [_tags(r) for r in records]
    keys = [k for k in keys if k.get("v") == "x402key1" and k.get("alg") == "Ed25519"
            and k.get("k")]
    if not keys:
        return "key-not-found", f"No x402key1 Ed25519 key in DNS at {kid}.", None
    try:
        public_key = Ed25519PublicKey.from_public_bytes(_b64url(keys[0]["k"]))
        signed = _b64url(signature["sig"])
    except ValueError:
        return "key-not-found", f"The key at {kid} or the signature is malformed.", None

    try:
        canonical = canonical_bytes(manifest)
    except (TypeError, ValueError):
        return "canon-mismatch", "The manifest has values this check can't canonicalize.", None
    digest = signature.get("content_digest")
    published = digest.get("value") if isinstance(digest, dict) else None
    ours = hashlib.sha256(canonical).hexdigest()
    try:
        public_key.verify(signed, canonical)
    except InvalidSignature:
        if isinstance(published, str) and published.lower() == ours:
            return "signature-invalid", "The signature does not verify under the DNS key.", None
        # Our canonical bytes may differ from the publisher's: the fault may be ours.
        return ("canon-mismatch", "The signature doesn't verify, and our canonical digest "
                "differs from the published one, so it can't be called invalid.", None)
    return "authentic", f"Signed by {kid}.", manifest


def check_payee(origin: str, network: str, pay_to: str, *,
                txt: Callable[[str], list[str]] | None = None,
                get: Callable[[str], tuple[int, bytes]] | None = None,
                timeout: float = TIMEOUT) -> Binding:
    """Checks that pay_to is a payee of origin on network (a CAIP-2 id).

    origin is the site the agent contacted ("https://api.shop.com"), never the
    resource URL the 402 names: that comes from the same server as payTo.
    txt(name) -> TXT records and get(url) -> (status, body) replace the
    network calls (tests, your own resolver or HTTP client).
    """
    host = _origin_host(origin)
    txt = txt or (lambda name: dns_txt(name, timeout))
    get = get or (lambda url: _get(url, timeout))

    def answer(outcome: str, reason: str, detail: str) -> Binding:
        return Binding(outcome, reason, f"https://{host}", network, pay_to, detail=detail)

    url = f"https://{host}{MANIFEST_PATH}"
    try:
        status, manifest_body = get(url)
        if status != 200:
            return answer(INCONCLUSIVE, "no-manifest", f"{url} answered {status}.")
        status, signature_body = get(url + ".sig")
        if status != 200:
            return answer(INCONCLUSIVE, "unsigned", f"{url}.sig answered {status}.")
        if len(manifest_body) > MAX_BYTES or len(signature_body) > MAX_BYTES:
            return answer(INCONCLUSIVE, "manifest-unreadable", "The manifest is too large.")
        reason, detail, manifest = verify_manifest(manifest_body, signature_body, host, txt)
    except _Unavailable as e:
        return answer(INCONCLUSIVE, "resolution-failed", str(e))
    if manifest is None:
        return answer(INCONCLUSIVE, reason, detail)

    listed = listed_addresses(manifest, network)
    if any(_same_address(pay_to, a) for a in listed):
        return answer(BOUND, "payee-bound", f"{host} lists {pay_to} for {network}. {detail}")
    if listed:
        why = f"{host} lists other addresses for {network}, not {pay_to}"
    else:
        why = f"{host} lists no address for {network}"
    # The manifest doesn't say its list is complete, so this is no exclusion.
    return answer(INCONCLUSIVE, "payto-not-listed", f"{why}. {detail}")


class PayeeChecker:
    """check_payee with answers kept for a while: an agent paying the same API
    a thousand times needn't fetch the manifest a thousand times. A lookup
    that didn't finish is not kept, so the next payment tries again."""

    def __init__(self, ttl: float = 300, **kwargs) -> None:
        self.ttl = ttl
        self.kwargs = kwargs
        self._kept: dict[tuple[str, str, str], tuple[float, Binding]] = {}

    def __call__(self, origin: str, network: str, pay_to: str) -> Binding:
        key = (origin, network, pay_to)
        kept = self._kept.get(key)
        if kept and time.monotonic() - kept[0] < self.ttl:
            return kept[1]
        binding = check_payee(origin, network, pay_to, **self.kwargs)
        if binding.reason != "resolution-failed":
            self._kept[key] = (time.monotonic(), binding)
        return binding


__all__ = ["BOUND", "EXCLUDED", "INCONCLUSIVE", "Binding", "PayeeChecker", "canonical_bytes",
           "check_payee", "dns_txt", "listed_addresses", "verify_manifest"]
