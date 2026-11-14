"""Paying the sandbox store in crypto, with the guard before the signature.

The pieces a real agent payment has, small enough to read in one go:

- the shop issues an invoice for the cart (Invoice): who receives the money,
  which token, how much, a reference. Its shape follows a Solana Pay transfer
  request; invoice.url(mint) is that request as a solana: link;
- the agent's wallet (AgentWallet) pays an invoice: a token transfer with the
  reference as a memo, optionally after swapping another token into it;
- the chain the money moves on: SimulatedChain, an in-memory ledger that
  needs no network, or DevnetChain, real transactions on Solana devnet with
  a test token we mint ourselves (worthless; not Circle's USDC);
- guarded(wallet, guard, checkout): the wallet's pay with the AsAsked guard
  in front of it (Guard.gate, as guard.protect does).

What the guard is given matters more than the guard. The cart it checks and
the shop's address it compares the recipient with come from the shop's
invoice, looked up by reference; the swap figures come from the swap pool's
quote. The agent only chooses what it controls: where it sends the money,
how much, in which token, through which swap and with what slippage. A
hijacked agent can change all of those, and none of them can change what it
is checked against.

Prices are fixed demo prices (DEMO_PRICES_USD), not market data.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass

from . import solana
from .solana import Keypair

TOKEN_DECIMALS = {"USDC": 6, "SOL": 9}
# Fixed prices for the demo, in dollars: the guard's arithmetic needs a rate,
# and a demo must give the same result every time it runs.
DEMO_PRICES_USD = {"USDC": 1.0, "SOL": 150.0}
SWAP_FEE_BPS = 30


def to_units(amount: float, token: str) -> int:
    return round(amount * 10 ** TOKEN_DECIMALS[token])


def from_units(units: int, token: str) -> float:
    return units / 10 ** TOKEN_DECIMALS[token]


class PaymentFailed(Exception):
    """The chain refused the transfer: not enough funds, unknown token."""


class PaymentUnknown(Exception):
    """The transfer was sent and may still land. Look it up; never send it again."""

    def __init__(self, message: str, signature: str):
        super().__init__(message)
        self.signature = signature

# ---------------------------------------------------------------------------
# The shop's side
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Invoice:
    reference: str
    merchant: str                  # the shop's name
    recipient: str                 # the shop's address: where the money must go
    token: str
    network: str
    amount: float                  # in token units
    total_cents: int
    purchase: tuple                # ((sku, quantity), ...)

    def url(self, mint: str) -> str:
        """The invoice as a Solana Pay transfer request link for the token's mint.

        Without spl-token such a link asks for native SOL, so the mint is required.
        """
        amount = f"{self.amount:.{TOKEN_DECIMALS[self.token]}f}".rstrip("0").rstrip(".")
        query = {"amount": amount, "spl-token": mint, "label": self.merchant,
                 "memo": self.reference}
        return f"solana:{self.recipient}?{urllib.parse.urlencode(query)}"


class CryptoCheckout:
    """The store's crypto checkout: invoices for carts, addressed to each merchant."""

    def __init__(self, store, addresses: dict[str, str], token: str = "USDC",
                 network: str = "solana"):
        missing = set(store.merchants) - set(addresses)
        if missing:
            raise ValueError(f"no payment address for merchants {sorted(missing)}")
        self.store, self.addresses = store, dict(addresses)
        self.token, self.network = token, network
        self.invoices: dict[str, Invoice] = {}
        self.payments: dict[str, dict] = {}     # reference -> the payment that went out
        self._ids = itertools.count(1)

    def invoice(self, session) -> Invoice:
        if not session.cart:
            raise ValueError("the cart is empty")
        purchase = tuple(session.cart.items())
        merchants = {self.store.find(sku)["merchant_id"] for sku, _ in purchase}
        if len(merchants) > 1:
            raise ValueError("all items in one order must come from the same merchant")
        merchant_id = merchants.pop()
        total = sum(self.store.find(sku)["price_cents"] * q for sku, q in purchase)
        invoice = Invoice(
            reference=f"asasked-demo-{session.session_id}-{next(self._ids)}",
            merchant=self.store.merchants[merchant_id]["name"],
            recipient=self.addresses[merchant_id], token=self.token, network=self.network,
            amount=round(total / 100 / DEMO_PRICES_USD[self.token],
                         TOKEN_DECIMALS[self.token]),
            total_cents=total, purchase=purchase)
        self.invoices[invoice.reference] = invoice
        return invoice

    def lookup(self, reference: str) -> Invoice:
        if reference not in self.invoices:
            raise KeyError(f"no invoice {reference!r}")
        return self.invoices[reference]

    def record(self, reference: str, result: dict) -> None:
        """Notes a payment that went out, or may have ("paid" or "unknown")."""
        if result["status"] in ("paid", "unknown"):
            self.payments[reference] = result

    def cart(self, reference: str) -> list[dict]:
        """The invoiced cart in the guard's form (see asasked.guard)."""
        lines = []
        for sku, quantity in self.lookup(reference).purchase:
            p = self.store.find(sku)
            lines.append({"name": p["name"], "brand": p["brand"], "color": p["color"],
                          "size": p["size_label"] or None, "category": p["category"],
                          "level": None if p["level"] == "any" else p["level"],
                          "units": p["units"],
                          "price": p["price_cents"] / 100, "quantity": quantity,
                          "returnable": p["refundable"], "delivery_days": p["ships_in_days"]})
        return lines

# ---------------------------------------------------------------------------
# Chains
# ---------------------------------------------------------------------------


class SimulatedChain:
    """An in-memory ledger: balances in base units and a log of transfers."""

    network = "solana"
    simulated = True

    def __init__(self):
        self.balances: dict[tuple[str, str], int] = defaultdict(int)
        self.log: list[dict] = []

    def fund(self, owner: str, token: str, amount: float) -> None:
        self.balances[owner, token] += to_units(amount, token)

    def balance(self, owner: str, token: str) -> float:
        return from_units(self.balances[owner, token], token)

    def _move(self, owner: str, token: str, units: int) -> None:
        if token not in TOKEN_DECIMALS:
            raise PaymentFailed(f"unknown token {token}")
        if self.balances[owner, token] + units < 0:
            raise PaymentFailed(f"insufficient {token}: has "
                                f"{self.balance(owner, token)}, needs {from_units(-units, token)}")
        self.balances[owner, token] += units

    def transfer(self, sender: Keypair, token: str, to: str, amount: float,
                 memo: str) -> str:
        if token not in TOKEN_DECIMALS:
            raise PaymentFailed(f"unknown token {token}")
        units = to_units(amount, token)
        self._move(sender.address, token, -units)
        self._move(to, token, units)
        entry = {"from": sender.address, "to": to, "token": token, "units": units,
                 "memo": memo, "n": len(self.log)}
        # A stand-in for a signature: 64 bytes, like a real one, but not a signature.
        entry["signature"] = solana.b58encode(
            hashlib.sha512(json.dumps(entry, sort_keys=True).encode()).digest())
        self.log.append(entry)
        return entry["signature"]

    def explorer(self, signature: str) -> str | None:
        return None


class DevnetChain:
    """Real transfers on Solana devnet. USDC here is a test mint of our own (see setup)."""

    network = "solana"
    simulated = False

    def __init__(self, rpc: solana.Rpc, mints: dict[str, str], fee_payer: Keypair):
        self.rpc, self.mints, self.fee_payer = rpc, dict(mints), fee_payer

    def _mint(self, token: str) -> str:
        if token not in self.mints:
            raise PaymentFailed(f"no {token} on devnet in this demo")
        return self.mints[token]

    def balance(self, owner: str, token: str) -> float:
        return from_units(self.rpc.token_balance(owner, self._mint(token)), token)

    def transfer(self, sender: Keypair, token: str, to: str, amount: float,
                 memo: str) -> str:
        mint, units = self._mint(token), to_units(amount, token)
        if self.rpc.token_balance(sender.address, mint) < units:
            raise PaymentFailed(f"insufficient {token}")
        # The recipient's token account is created if missing (paid by the
        # fee payer), as wallets do; then the transfer and the reference as a memo.
        signers = (sender,) if sender.address != self.fee_payer.address else ()
        try:
            return self.rpc.send(self.fee_payer, [
                solana.create_token_account(self.fee_payer.address, to, mint),
                solana.transfer_checked(mint, sender.address, to, units,
                                        TOKEN_DECIMALS[token]),
                solana.memo(memo)], signers)
        except solana.OutcomeUnknown as e:
            raise PaymentUnknown(str(e), e.signature) from e
        except solana.RpcError as e:
            raise PaymentFailed(str(e)) from e

    def explorer(self, signature: str) -> str:
        return solana.EXPLORER_TX.format(signature)

# ---------------------------------------------------------------------------
# Swaps
# ---------------------------------------------------------------------------


class SimulatedPool:
    """A swap market at DEMO_PRICES_USD with a fee.

    fill="quote" fills at the quoted amount; fill="worst" at the minimum the
    swap allows, as a sandwich attack or a fast market would: a slippage
    tolerance is the amount a swap may lose, and here it does.
    """

    def __init__(self, fill: str = "quote", fee_bps: int = SWAP_FEE_BPS):
        if fill not in ("quote", "worst"):
            raise ValueError("fill: quote or worst")
        self.fill, self.fee_bps = fill, fee_bps

    def quote(self, from_token: str, to_token: str, want_out: float,
              slippage_bps: int) -> dict:
        """What to put in to get want_out, and the least it may give.

        The quote aims high enough that its minimum is still want_out: a swap
        within its own tolerance always covers the payment. The tolerance is
        then paid for up front, in what goes in (as an exact-out swap does).
        """
        for token in (from_token, to_token):
            if token not in DEMO_PRICES_USD:
                raise PaymentFailed(f"no market for {token}")
        if not 0 <= slippage_bps < 10000:
            raise PaymentFailed("slippage must be from 0 to under 100%")
        keep = 10000 - int(slippage_bps)
        want_units = to_units(want_out, to_token)
        # Both rounded up: the minimum stays at or above want_out, and the
        # quote loses no more than the tolerance down to it.
        quote_units = -(-want_units * 10000 // keep)
        min_units = -(-quote_units * keep // 10000)
        quote_out, min_out = from_units(quote_units, to_token), from_units(min_units, to_token)
        amount_in = round(quote_out * DEMO_PRICES_USD[to_token] / DEMO_PRICES_USD[from_token]
                          / (1 - self.fee_bps / 10000), TOKEN_DECIMALS[from_token])
        return {"from_token": from_token, "amount_in": amount_in,
                "rate": DEMO_PRICES_USD[from_token], "quote_out": quote_out, "min_out": min_out}

    def swap(self, chain: SimulatedChain, owner: Keypair, to_token: str, quote: dict) -> float:
        if not getattr(chain, "simulated", False):
            raise PaymentFailed("this pool only swaps on the simulated chain")
        out = quote["quote_out"] if self.fill == "quote" else quote["min_out"]
        chain._move(owner.address, quote["from_token"],
                    -to_units(quote["amount_in"], quote["from_token"]))
        chain._move(owner.address, to_token, to_units(out, to_token))
        return out

# ---------------------------------------------------------------------------
# The agent's wallet
# ---------------------------------------------------------------------------


class AgentWallet:
    """The wallet an agent pays from. It holds the key; the agent calls pay()."""

    def __init__(self, chain, key: Keypair, pool: SimulatedPool | None = None):
        self.chain, self.key, self.pool = chain, key, pool

    @property
    def address(self) -> str:
        return self.key.address

    def quote(self, token: str, amount: float, swap_from: str | None = None,
              slippage_bps: int | None = None) -> dict | None:
        """The pool's quote for swapping swap_from into amount of token; None without a swap."""
        if swap_from is None:
            return None
        if self.pool is None:
            raise PaymentFailed("this wallet has no swap")
        return self.pool.quote(swap_from, token, amount,
                               100 if slippage_bps is None else slippage_bps)

    def pay(self, reference: str, to: str, amount: float, token: str = "USDC",
            swap_from: str | None = None, slippage_bps: int | None = None) -> dict:
        """Pays: swaps swap_from into token first if asked, then transfers.

        The memo carries the invoice reference, so the shop can match the payment.
        """
        try:
            quote = self.quote(token, amount, swap_from, slippage_bps)
        except PaymentFailed as e:
            return {"status": "failed", "error": str(e)}
        return self.execute(reference, to, amount, token, quote)

    def execute(self, reference: str, to: str, amount: float, token: str,
                quote: dict | None) -> dict:
        """Swaps by this quote, if any, then transfers. pay() without the quoting."""
        try:
            if quote:
                self.pool.swap(self.chain, self.key, token, quote)
            signature = self.chain.transfer(self.key, token, to, amount, reference)
        except PaymentFailed as e:
            return {"status": "failed", "error": str(e)}
        except PaymentUnknown as e:
            return {"status": "unknown", "error": str(e), "signature": e.signature,
                    "explorer": self.chain.explorer(e.signature)}
        return {"status": "paid", "signature": signature,
                "explorer": self.chain.explorer(signature)}


def guarded(wallet: AgentWallet, guard, checkout: CryptoCheckout):
    """wallet.pay with the AsAsked guard in front of it.

    The same arguments as wallet.pay. The guard gets the cart and the shop's
    address from the invoice the reference names, and the swap figures from
    the pool's quote; the agent's arguments say only what it is about to do.
    The quote the guard checked is the one the wallet then executes.

    Returns wallet.pay's result, or {"status": "not_paid", "decision": ...,
    "message": ...} with the guard's text for the agent (Guard.gate). On
    "ask" it carries a question for the person, whose answer goes back
    through guard.answer, by your code, not by the agent. On "refuse" the
    payment itself must change: no answer of the person's approves it.

    An invoice is paid once: after a payment that went out, or may have
    ("unknown": sent, but its confirmation never came), another pay of the
    same reference fails without sending anything. Retrying on a timeout
    is how agents pay twice.
    """
    def pay(reference: str, to: str, amount: float, token: str = "USDC",
            swap_from: str | None = None, slippage_bps: int | None = None) -> dict:
        try:
            invoice = checkout.lookup(reference)
        except KeyError as e:
            return {"status": "failed", "error": e.args[0]}
        earlier = checkout.payments.get(reference)
        if earlier:
            what = "paid" if earlier["status"] == "paid" else "may already be paid"
            return {"status": "failed",
                    "error": f"invoice {reference} {what}: {earlier['signature']}; "
                             "not paying it again"}
        try:
            quote = wallet.quote(token, amount, swap_from, slippage_bps)
        except PaymentFailed as e:
            return {"status": "failed", "error": str(e)}
        payment = {"token": token, "network": wallet.chain.network, "amount": amount,
                   "to": to, "merchant": invoice.recipient,
                   "rate": DEMO_PRICES_USD.get(token), "swap": quote}
        blocked = guard.gate(checkout.cart(reference), payment)
        if blocked:
            return {"status": "not_paid", "decision": guard.checks[-1]["decision"],
                    "message": blocked}
        result = wallet.execute(reference, to, amount, token, quote)
        checkout.record(reference, result)
        return result

    return pay


__all__ = ["AgentWallet", "CryptoCheckout", "DEMO_PRICES_USD", "DevnetChain", "Invoice",
           "PaymentFailed", "PaymentUnknown", "SimulatedChain", "SimulatedPool",
           "TOKEN_DECIMALS", "from_units", "guarded", "to_units"]
