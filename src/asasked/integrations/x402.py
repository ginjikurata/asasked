"""The guard for x402: an API's payment request is checked before the agent signs it.

With x402 an agent pays an API on its own: the server answers 402 with what
it wants (token, amount, address), the client signs and sends the request
again. X402Guard goes into the client as a hook, so every such payment is
first checked against the person's words:

    from x402 import x402Client
    from x402.http.clients import x402HttpxClient
    from x402.mechanisms.svm.exact.register import register_exact_svm_client
    from x402.http.clients.httpx import PaymentError
    from asasked import Guard
    from asasked.integrations.x402 import X402Guard, refusal

    client = x402Client()
    register_exact_svm_client(client, signer)
    guard = Guard("Get me Lisbon weather for the week, pay with USDC on Solana, "
                  "no more than $1 in total", payees=[api_address])
    X402Guard(guard).install(client)

    async with x402HttpxClient(client) as http:
        try:
            response = await http.get(url)
        except PaymentError as e:
            if refusal(e) is None:
                raise                      # failed for another reason
            show_the_person(refusal(e))    # nothing was signed or paid

    guard.answer(their_reply)              # your code, not the agent; then try again

The sync client (x402ClientSync, x402_requests) takes the same install().
x402's HTTP clients wrap the refusal in their own PaymentError; refusal(e)
finds the guard's text in it (or in x402's PaymentAbortedError, raised when
you call the client's create_payment_payload yourself).

What is checked is what the guard checks for any on-chain payment (see
asasked.payment): the token, the network, the amount against the person's
limit and the address. The amount is read with the decimals from the x402
library's own table of known tokens, never from the server's 402: a server
could otherwise claim a token has more decimals and take more than it shows.
A token missing from that table is paid only if you describe it, assets=
{address: {"token": "XYZ", "decimals": 6, "rate": 0.5}}; rate is its price
in dollars (stablecoins are 1). Otherwise the payment is stopped: an amount
that can't be read can't be checked.

The person's limit is for all the payments of their request, not each one:
"no more than $1" is broken by a thousand calls at $0.001 just as by one at
$1.01. X402Guard keeps count of what it let through (spent) and gives it to
the guard with every check. A payment counts once it is signed, even if the
server never settles it: the count errs on the side of the person. If your
agent spends on the same request in other ways, pass spent= with that.

The address: a server names its own, so a forged 402 (a hijacked endpoint, a
man in the middle) names someone else's. Pass payees= to the Guard, the
addresses the person approved, and a payment anywhere else is refused, not
asked about. Without payees the guard notes that the address is unchecked.

Each payment is one cart line, the resource's description at its price.
cart=callable(payment_required, requirements) -> list of cart dicts replaces
it when your agent knows more (what the call returns, whether it renews).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from x402 import x402Client, x402ClientSync
from x402.schemas import AbortResult, PaymentAbortedError

from ..guard import Guard

# Tokens worth a dollar each: their amount is their price. Others need a rate.
USD_STABLECOINS = frozenset({"USDC", "USDT", "USDG", "PYUSD", "CASH"})

# EVM chain ids in CAIP-2 ("eip155:8453") under the names people use; test
# networks under the name of their main one, as the person would say it.
EVM_NETWORKS = {
    1: "ethereum", 11155111: "ethereum",
    8453: "base", 84532: "base",
    137: "polygon", 80002: "polygon",
    42161: "arbitrum", 421614: "arbitrum",
    10: "optimism", 11155420: "optimism",
    43114: "avalanche", 43113: "avalanche",
}

# Version 1 of x402 names networks in words.
V1_NETWORKS = {
    "base-sepolia": "base", "polygon-amoy": "polygon", "avalanche-fuji": "avalanche",
    "arbitrum-sepolia": "arbitrum", "optimism-sepolia": "optimism", "sepolia": "ethereum",
}

# What the agent's code sees when the 402 can't be checked at all.
UNKNOWN_ASSET = ("NOT PAID. The API asks to be paid in a token I can't read amounts of "
                 "({asset} on {network}), so I couldn't check the payment against the "
                 "person's request. Pay it only if the developer describes this token "
                 "(X402Guard(assets=...)).")
NO_RATE = ("NOT PAID. The API asks for {amount} {token}, and I don't know what {token} "
           "is worth in dollars, so I couldn't check it against the person's limit. "
           "Pay it only if the developer gives its rate (X402Guard(assets=...)).")


def network_name(network: str) -> str:
    """An x402 network as the person would name it: "solana", "base", ...

    CAIP-2 ids ("solana:5eykt4...", "eip155:8453") and version 1 names
    ("solana-devnet", "base-sepolia") alike. An unknown one comes back as it
    is: a person who named a network is then asked rather than assumed.
    """
    text = (network or "").strip().lower()
    if text.startswith("solana"):
        return "solana"
    if text.startswith("eip155:"):
        try:
            return EVM_NETWORKS.get(int(text.split(":", 1)[1]), text)
        except ValueError:
            return text
    return V1_NETWORKS.get(text, text)


def _known_asset(asset: str, network: str) -> dict | None:
    """The x402 library's own entry for a token: symbol and decimals, or None."""
    text = (network or "").lower()
    try:
        # Each table's package needs that chain's libraries (solders, eth-account),
        # which any client able to pay on the chain already has.
        if text.startswith("solana"):
            from x402.mechanisms.svm.default_assets import find_default_asset
        elif text.startswith("eip155:") or network_name(text) in set(EVM_NETWORKS.values()):
            from x402.mechanisms.evm.default_assets import find_default_asset
        else:
            return None
        return find_default_asset(asset, network)
    except (ImportError, ValueError, KeyError):
        return None


def _resource(payment_required, requirements) -> str:
    """What is being paid for, in words, from the 402."""
    info = getattr(payment_required, "resource", None)
    for text in (getattr(info, "description", None), getattr(info, "service_name", None),
                 getattr(requirements, "description", None), getattr(info, "url", None),
                 getattr(requirements, "resource", None)):
        if isinstance(text, str) and text.strip():
            return " ".join(text.split())
    return "API call"


class X402Guard:
    """Checks each x402 payment with a Guard before the client signs it.

    guard is the Guard for the person's request. assets describes tokens
    missing from the x402 library's table: {address: {"token", "decimals",
    "rate"}}. cart(payment_required, requirements) builds the cart for a
    payment instead of the one line by default. spent is what was already
    paid for this request before this X402Guard (in dollars).
    """

    def __init__(self, guard: Guard, *, assets: dict | None = None,
                 cart: Callable | None = None, spent: float = 0) -> None:
        self.guard = guard
        self.assets = {str(k).lower(): v for k, v in (assets or {}).items()}
        self.cart = cart
        self._spent = Decimal(str(spent))
        # Payments let through and not yet signed or failed, by requirements.
        self._pending: dict[int, Decimal] = {}
        self._lock = threading.Lock()
        # Texts given instead of payment, newest last.
        self.blocked: list[str] = []

    @property
    def spent(self) -> float:
        """Dollars paid through this guard, payments under way included."""
        with self._lock:
            return float(self._spent + sum(self._pending.values(), Decimal(0)))

    def install(self, client):
        """Registers the hooks on an x402Client or x402ClientSync; returns the client."""
        if isinstance(client, x402Client):
            async def before(ctx):
                return await asyncio.to_thread(self._before, ctx)
        elif isinstance(client, x402ClientSync):
            before = self._before
        else:
            raise TypeError("install() takes an x402Client or x402ClientSync")
        client.on_before_payment_creation(before)
        client.on_after_payment_creation(self._signed)
        client.on_payment_creation_failure(self._failed)
        return client

    def payment(self, payment_required, requirements) -> dict | str:
        """The payment in asasked's form (see asasked.payment), or the text
        to give instead of paying when its amount can't be known."""
        asset = str(requirements.asset)
        known = self.assets.get(asset.lower()) or _known_asset(asset, requirements.network)
        if not known:
            return UNKNOWN_ASSET.format(asset=asset, network=requirements.network)
        token = str(known.get("token") or known.get("symbol") or "").upper()
        try:
            amount = Decimal(str(requirements.get_amount())) / (10 ** int(known["decimals"]))
        except (InvalidOperation, KeyError, TypeError, ValueError):
            return UNKNOWN_ASSET.format(asset=asset, network=requirements.network)
        rate = known.get("rate")
        if rate is None and token in USD_STABLECOINS:
            rate = 1.0
        if rate is None:
            return NO_RATE.format(amount=amount, token=token or asset)
        return {"token": token or asset, "network": network_name(requirements.network),
                "amount": float(amount), "rate": float(rate),
                "to": requirements.pay_to, "merchant": requirements.pay_to}

    def _cart(self, payment_required, requirements, usd: Decimal) -> list[dict]:
        if self.cart is not None:
            return self.cart(payment_required, requirements)
        return [{"name": _resource(payment_required, requirements), "price": float(usd),
                 "quantity": 1}]

    def _before(self, ctx):
        requirements = ctx.selected_requirements
        payment = self.payment(ctx.payment_required, requirements)
        if isinstance(payment, str):
            self.blocked.append(payment)
            return AbortResult(reason=payment)
        usd = Decimal(str(payment["amount"])) * Decimal(str(payment["rate"]))
        cart = self._cart(ctx.payment_required, requirements, usd)
        with self._lock:
            # Checked one at a time, so two payments at once can't both fit
            # into what is left of the limit.
            earlier = self._spent + sum(self._pending.values(), Decimal(0))
            told = self.guard.gate(cart, payment, spent_before=float(earlier))
            if told is None:
                self._pending[id(requirements)] = usd
                return None
        self.blocked.append(told)
        return AbortResult(reason=told)

    def _signed(self, ctx) -> None:
        with self._lock:
            usd = self._pending.pop(id(ctx.selected_requirements), None)
            if usd is not None:
                self._spent += usd

    def _failed(self, ctx) -> None:
        with self._lock:
            self._pending.pop(id(ctx.selected_requirements), None)


def refusal(error: BaseException) -> str | None:
    """What the guard said instead of paying, if that is why error was raised.

    x402's HTTP clients raise their own PaymentError with x402's
    PaymentAbortedError as its cause; this looks through the chain. None
    means the payment failed for some other reason.
    """
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, PaymentAbortedError):
            return error.reason
        error = error.__cause__ or error.__context__
    return None


def guard_x402(client, guard: Guard, **kwargs) -> X402Guard:
    """X402Guard(guard, **kwargs) installed on client, in one call."""
    x402_guard = X402Guard(guard, **kwargs)
    x402_guard.install(client)
    return x402_guard


__all__ = ["X402Guard", "guard_x402", "network_name", "refusal"]
