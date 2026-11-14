"""The crypto checkout, the agent's wallet and the guard in front of it; no network."""

import importlib.util
import json
import os
import pathlib
import stat
import struct
import sys
import urllib.parse

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from asasked.coherence import IntentFacts
from asasked.guard import Guard
from asasked.store import solana
from asasked.store.crypto import (AgentWallet, CryptoCheckout, DevnetChain, PaymentFailed,
                                  SimulatedChain, SimulatedPool, from_units, guarded, to_units)
from asasked.store.solana import Keypair
from asasked.store.store import Mandate, Store

COURT = "ASI-GELRESOLUTION9-42-BLA-COU"     # $148.99, returnable
OUTLET = "ASI-GELRESOLUTION9-42-BLA-OUT"    # $126.99, final sale
KEYS = {name: Keypair.from_seed_phrase(f"test {name}")
        for name in ("agent", "thief", "m-court", "m-outlet", "m-baseline", "m-ace")}
ADDRESSES = {m: k.address for m, k in KEYS.items() if m.startswith("m-")}
FACTS = IntentFacts(raw="x", brand="ASICS", color="black", size_label="42",
                    needs_refundable=True, explicit_max_cents=16000,
                    pay_with="USDC", pay_network="solana")


def checkout_with(*skus):
    store = Store()
    checkout = CryptoCheckout(store, ADDRESSES)
    session = store.new_session(Mandate("x", tuple(skus), 1, 100, 100000))
    for sku in skus:
        session.call("add_to_cart", {"sku": sku})
    return checkout, session


def setup(sku=COURT, facts=FACTS, fund=None, fill="quote"):
    checkout, session = checkout_with(sku)
    invoice = checkout.invoice(session)
    chain = SimulatedChain()
    for token, amount in (fund or {"USDC": 500}).items():
        chain.fund(KEYS["agent"].address, token, amount)
    wallet = AgentWallet(chain, KEYS["agent"], SimulatedPool(fill=fill))
    guard = Guard("x", today="Thursday, 12 November 2026", extract=lambda request: facts)
    return invoice, chain, guarded(wallet, guard, checkout)


# ---------------------------------------------------------------------------
# The shop's invoice
# ---------------------------------------------------------------------------


def test_the_invoice_comes_from_the_cart():
    checkout, session = checkout_with(COURT)
    invoice = checkout.invoice(session)
    assert (invoice.recipient, invoice.token, invoice.network) == \
        (ADDRESSES["m-court"], "USDC", "solana")
    assert (invoice.amount, invoice.total_cents) == (148.99, 14899)
    assert invoice.purchase == ((COURT, 1),)
    assert checkout.lookup(invoice.reference) is invoice
    # each invoice has its own reference
    assert checkout.invoice(session).reference != invoice.reference
    line, = checkout.cart(invoice.reference)
    assert (line["brand"], line["color"], line["size"], line["price"], line["returnable"]) \
        == ("ASICS", "black", "42", 148.99, True)
    assert line["level"] is None                 # "any" in the catalog is no level at all


def test_the_invoice_refuses_what_it_cannot_bill():
    checkout, session = checkout_with()
    with pytest.raises(ValueError, match="empty"):
        checkout.invoice(session)
    checkout, session = checkout_with(COURT, OUTLET)
    with pytest.raises(ValueError, match="same merchant"):
        checkout.invoice(session)
    with pytest.raises(ValueError, match="no payment address"):
        CryptoCheckout(Store(), {"m-court": ADDRESSES["m-court"]})
    with pytest.raises(KeyError):
        checkout.lookup("asasked-demo-nope")


def test_the_invoice_is_a_solana_pay_link():
    checkout, session = checkout_with(COURT)
    invoice = checkout.invoice(session)
    mint = KEYS["m-ace"].address
    scheme, rest = invoice.url(mint).split(":", 1)
    recipient, query = rest.split("?", 1)
    fields = dict(urllib.parse.parse_qsl(query))
    assert (scheme, recipient) == ("solana", invoice.recipient)
    assert fields == {"amount": "148.99", "spl-token": mint, "label": "Court Supply",
                      "memo": invoice.reference}

# ---------------------------------------------------------------------------
# The chain, the pool and the wallet
# ---------------------------------------------------------------------------


def test_units_round_trip():
    assert to_units(148.99, "USDC") == 148_990_000
    assert to_units(0.1 + 0.2, "SOL") == 300_000_000
    assert from_units(to_units(1489.9, "USDC"), "USDC") == 1489.9


def test_the_simulated_chain_moves_only_what_there_is():
    chain = SimulatedChain()
    agent, shop = KEYS["agent"], ADDRESSES["m-court"]
    chain.fund(agent.address, "USDC", 10)
    signature = chain.transfer(agent, "USDC", shop, 4.5, "ref-1")
    assert (chain.balance(agent.address, "USDC"), chain.balance(shop, "USDC")) == (5.5, 4.5)
    assert len(solana.b58decode(signature)) == 64 and chain.log[0]["memo"] == "ref-1"
    with pytest.raises(PaymentFailed, match="insufficient"):
        chain.transfer(agent, "USDC", shop, 6, "ref-2")
    with pytest.raises(PaymentFailed, match="unknown token"):
        chain.transfer(agent, "DOGE", shop, 1, "ref-3")
    assert chain.balance(agent.address, "USDC") == 5.5 and len(chain.log) == 1


def test_a_swap_quote_and_its_fills():
    pool = SimulatedPool(fill="worst")
    quote = pool.quote("SOL", "USDC", 148.99, slippage_bps=50)
    # aimed so that its minimum, after the allowed 0.5%, is still the amount
    assert quote["quote_out"] == pytest.approx(148.99 / 0.995, abs=1e-6)
    assert 148.99 <= quote["min_out"] <= 148.990001
    assert quote["rate"] == 150.0
    # 0.3% fee on top of the quoted amount, at $150 a SOL
    assert quote["amount_in"] == pytest.approx(quote["quote_out"] / 150 / 0.997, abs=1e-9)
    chain = SimulatedChain()
    chain.fund(KEYS["agent"].address, "SOL", 3)
    assert pool.swap(chain, KEYS["agent"], "USDC", quote) == quote["min_out"]
    assert SimulatedPool().swap(chain, KEYS["agent"], "USDC", quote) == quote["quote_out"]
    with pytest.raises(PaymentFailed, match="no market"):
        pool.quote("BONK", "USDC", 1, 50)
    with pytest.raises(PaymentFailed, match="slippage"):
        pool.quote("SOL", "USDC", 1, 10000)


@pytest.mark.parametrize("amount", [148.99, 0.000001, 1, 33.333333, 9999.999999])
@pytest.mark.parametrize("bps", [0, 1, 50, 100, 1500, 9999])
def test_a_swap_within_its_own_tolerance_always_covers_the_payment(amount, bps):
    quote = SimulatedPool().quote("SOL", "USDC", amount, bps)
    assert quote["min_out"] >= amount
    assert (quote["quote_out"] - quote["min_out"]) / quote["quote_out"] * 10000 <= bps + 1e-6
    with pytest.raises(ValueError):
        SimulatedPool(fill="best")


def test_the_unguarded_wallet_pays_whatever_it_is_told():
    chain = SimulatedChain()
    chain.fund(KEYS["agent"].address, "USDC", 500)
    wallet = AgentWallet(chain, KEYS["agent"])
    result = wallet.pay("ref", KEYS["thief"].address, 148.99)
    assert result["status"] == "paid" and result["explorer"] is None
    assert chain.balance(KEYS["thief"].address, "USDC") == 148.99
    assert wallet.pay("ref", KEYS["thief"].address, 1000)["status"] == "failed"
    assert wallet.pay("ref", KEYS["thief"].address, 1, swap_from="SOL") == \
        {"status": "failed", "error": "this wallet has no swap"}

# ---------------------------------------------------------------------------
# The guard before the signature
# ---------------------------------------------------------------------------


def test_the_right_payment_goes_through():
    invoice, chain, pay = setup()
    result = pay(invoice.reference, invoice.recipient, invoice.amount)
    assert result["status"] == "paid"
    assert chain.balance(invoice.recipient, "USDC") == 148.99
    assert chain.log[-1]["memo"] == invoice.reference


@pytest.mark.parametrize("change, said", [
    ({"to": KEYS["thief"].address}, "not to the shop's address"),
    ({"amount": 1489.9}, "the order total is $148.99"),
    ({"token": "SOL", "amount": 0.993267}, "Asked to pay with USDC, the payment uses SOL"),
])
def test_a_wrong_payment_moves_nothing(change, said):
    invoice, chain, pay = setup(fund={"USDC": 2000, "SOL": 3})
    before = dict(chain.balances)
    args = {"reference": invoice.reference, "to": invoice.recipient,
            "amount": invoice.amount, **change}
    result = pay(**args)
    assert result["status"] == "not_paid"
    assert result["message"].startswith("NOT PAID") and said in result["message"]
    assert dict(chain.balances) == before and chain.log == []


def test_the_shop_address_comes_from_the_invoice_not_the_agent():
    # An agent that "knows" the shop moved can't make the thief the merchant:
    # the guard compares with the invoice the reference names.
    invoice, chain, pay = setup()
    thief = KEYS["thief"].address
    result = pay(invoice.reference, thief, invoice.amount)
    assert result["status"] == "not_paid" and result["decision"] == "refuse"
    assert f"goes to {thief}, not to the shop's address {invoice.recipient}" in result["message"]


def test_the_cart_is_checked_too():
    invoice, chain, pay = setup(sku=OUTLET)
    result = pay(invoice.reference, invoice.recipient, invoice.amount)
    assert result["status"] == "not_paid" and result["decision"] == "ask"
    assert "return" in result["message"]
    assert chain.log == []


def test_an_unknown_invoice_is_not_paid():
    invoice, chain, pay = setup()
    result = pay("asasked-demo-forged", KEYS["thief"].address, 1)
    assert result == {"status": "failed", "error": "no invoice 'asasked-demo-forged'"}
    assert chain.log == []


def test_a_loose_swap_is_stopped_before_it_loses_anything():
    facts = IntentFacts(raw="x", brand="ASICS", color="black", size_label="42",
                        needs_refundable=True, explicit_max_cents=16000, pay_with="SOL")
    invoice, chain, pay = setup(facts=facts, fund={"SOL": 3}, fill="worst")
    loose = pay(invoice.reference, invoice.recipient, invoice.amount,
                swap_from="SOL", slippage_bps=1500)
    assert loose["status"] == "not_paid" and "15.00% less than quoted" in loose["message"]
    assert chain.balance(KEYS["agent"].address, "SOL") == 3
    # Lowered to exactly the 1% the refusal names, filled at its worst: paid,
    # and the minimum still covers the invoice.
    tight = pay(invoice.reference, invoice.recipient, invoice.amount,
                swap_from="SOL", slippage_bps=100)
    assert tight["status"] == "paid"
    assert chain.balance(invoice.recipient, "USDC") == 148.99


def test_the_wallet_executes_the_quote_the_guard_checked(monkeypatch):
    # A pool that would quote differently on a second call: the guard's quote must be the one used.
    facts = IntentFacts(raw="x", explicit_max_cents=16000, pay_with="SOL")
    invoice, chain, pay = setup(facts=facts, fund={"SOL": 3})
    checked, executed = [], []
    real_quote, real_swap = SimulatedPool.quote, SimulatedPool.swap

    def quote(self, *args, **kwargs):
        q = real_quote(self, *args, **kwargs)
        q["amount_in"] += len(checked)                # a different quote every call
        checked.append(q)
        return q

    def swap(self, chain, owner, to_token, q):
        executed.append(q)
        return real_swap(self, chain, owner, to_token, q)

    monkeypatch.setattr(SimulatedPool, "quote", quote)
    monkeypatch.setattr(SimulatedPool, "swap", swap)
    assert pay(invoice.reference, invoice.recipient, invoice.amount,
               swap_from="SOL", slippage_bps=50)["status"] == "paid"
    assert len(checked) == 1 and executed == checked

def test_an_invoice_is_paid_once():
    invoice, chain, pay = setup()
    assert pay(invoice.reference, invoice.recipient, invoice.amount)["status"] == "paid"
    again = pay(invoice.reference, invoice.recipient, invoice.amount)
    assert again["status"] == "failed" and "not paying it again" in again["error"]
    assert len(chain.log) == 1 and chain.balance(invoice.recipient, "USDC") == 148.99


def test_a_failed_payment_can_be_tried_again():
    invoice, chain, pay = setup(fund={"USDC": 100})
    assert pay(invoice.reference, invoice.recipient, invoice.amount)["status"] == "failed"
    chain.fund(KEYS["agent"].address, "USDC", 100)
    assert pay(invoice.reference, invoice.recipient, invoice.amount)["status"] == "paid"


class FakeRpc:
    """An RPC that answers from a script: {method: [answer, ...]} or a callable."""

    def __init__(self, answers, genesis="EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"):
        self.answers = {"getGenesisHash": [genesis] * 100, **answers}
        self.calls = []

    def __call__(self, method, *params):
        self.calls.append(method)
        answer = self.answers[method]
        answer = answer(*params) if callable(answer) else answer.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def rpc_with(answers, **kwargs):
    rpc = solana.Rpc()
    rpc.call = FakeRpc(answers, **kwargs)
    return rpc


def status(confirmation="confirmed", err=None):
    return {"value": [{"confirmationStatus": confirmation, "err": err}]}


NONE = {"value": [None]}
BLOCKHASH = {"value": {"blockhash": KEYS["m-ace"].address, "lastValidBlockHeight": 1000}}


def test_the_client_refuses_a_mainnet_rpc_by_its_genesis_hash():
    rpc = rpc_with({}, genesis=solana.MAINNET_GENESIS)
    with pytest.raises(ValueError, match="devnet only"):
        rpc.send(KEYS["agent"], [solana.memo("x")])
    with pytest.raises(ValueError, match="devnet only"):
        rpc.airdrop(KEYS["agent"].address, 1)
    assert "sendTransaction" not in rpc.call.calls


def test_a_send_cut_off_is_unknown_not_failed():
    def cut_off(*params):
        raise solana.RpcError("sendTransaction: timed out") from OSError("timed out")
    rpc = rpc_with({"getLatestBlockhash": [BLOCKHASH], "sendTransaction": cut_off})
    with pytest.raises(solana.OutcomeUnknown) as e:
        rpc.send(KEYS["agent"], [solana.memo("x")])
    # the signature is known before the answer: it is the payer's signature
    message = solana.compile_message(KEYS["agent"].address, [solana.memo("x")],
                                     KEYS["m-ace"].address)
    assert e.value.signature == solana.b58encode(KEYS["agent"].sign(message))
    # an error the node answered with means it was refused
    rpc = rpc_with({"getLatestBlockhash": [BLOCKHASH],
                    "sendTransaction": [solana.RpcError("sendTransaction: simulation failed")]})
    with pytest.raises(solana.RpcError) as e:
        rpc.send(KEYS["agent"], [solana.memo("x")])
    assert not isinstance(e.value, solana.OutcomeUnknown)


def test_confirm_tells_expired_from_unknown(monkeypatch):
    monkeypatch.setattr(solana.time, "sleep", lambda s: None)
    # landed late, after a while of nothing
    rpc = rpc_with({"getSignatureStatuses": [NONE, NONE, status()],
                    "getBlockHeight": [990, 995]})
    rpc.confirm("sig", last_valid=1000)
    # the blockhash expired and it never landed: a refusal, safe to try again
    rpc = rpc_with({"getSignatureStatuses": [NONE, NONE], "getBlockHeight": [1001]})
    with pytest.raises(solana.RpcError, match="expired") as e:
        rpc.confirm("sig", last_valid=1000)
    assert not isinstance(e.value, solana.OutcomeUnknown)
    # it landed just as the height passed
    rpc = rpc_with({"getSignatureStatuses": [NONE, status(), status()],
                    "getBlockHeight": [1001]})
    rpc.confirm("sig", last_valid=1000)
    # it failed on chain
    rpc = rpc_with({"getSignatureStatuses": [status(err={"InstructionError": [1, 1]})]})
    with pytest.raises(solana.RpcError, match="failed"):
        rpc.confirm("sig", last_valid=1000)
    # the RPC stopped answering: unknown, not failed
    rpc = rpc_with({"getSignatureStatuses": lambda *p: solana.RpcError("down")})
    with pytest.raises(solana.OutcomeUnknown):
        rpc.confirm("sig", last_valid=1000, timeout=0)


def test_an_unknown_outcome_is_not_paid_again():
    checkout, session = checkout_with(COURT)
    invoice = checkout.invoice(session)
    mint = KEYS["m-ace"].address

    class Unanswered:
        sends = 0

        def token_balance(self, owner, mint):
            return 10 ** 12

        def send(self, payer, instructions, signers=()):
            Unanswered.sends += 1
            raise solana.OutcomeUnknown("not confirmed in 90s; it may still land", "SiG")

    chain = DevnetChain(Unanswered(), {"USDC": mint}, fee_payer=KEYS["agent"])
    guard = Guard("x", today="Thursday, 12 November 2026", extract=lambda request: FACTS)
    pay = guarded(AgentWallet(chain, KEYS["agent"]), guard, checkout)
    first = pay(invoice.reference, invoice.recipient, invoice.amount)
    assert first["status"] == "unknown" and first["signature"] == "SiG"
    assert first["explorer"].endswith("SiG?cluster=devnet")
    again = pay(invoice.reference, invoice.recipient, invoice.amount)
    assert again["status"] == "failed" and "may already be paid: SiG" in again["error"]
    assert Unanswered.sends == 1

# ---------------------------------------------------------------------------
# The Solana client: encoding and signing, checked without a network
# ---------------------------------------------------------------------------


def test_base58_round_trip():
    for raw in (b"", b"\0", b"\0\0\1", bytes(range(32)), b"\xff" * 64):
        assert solana.b58decode(solana.b58encode(raw)) == raw
    assert solana.b58encode(bytes(32)) == solana.SYSTEM_PROGRAM
    with pytest.raises(ValueError):
        solana.b58decode("0OIl")
    with pytest.raises(ValueError, match="not a Solana address"):
        solana.pubkey("abc")


def test_shortvec():
    assert [solana.shortvec(n) for n in (0, 5, 127, 128, 16383, 16384)] == \
        [b"\0", b"\5", b"\x7f", b"\x80\x01", b"\xff\x7f", b"\x80\x80\x01"]


def test_keys_sign_and_sit_on_the_curve_program_addresses_do_not():
    key = Keypair.from_seed_phrase("curve")
    assert len(key.public) == 32 and solana.on_curve(key.public)
    message = b"asasked"
    Ed25519PublicKey.from_public_bytes(key.public).verify(key.sign(message), message)
    with pytest.raises(InvalidSignature):
        Ed25519PublicKey.from_public_bytes(key.public).verify(key.sign(message), b"other")
    ata = solana.token_account(key.address, KEYS["m-ace"].address)
    assert not solana.on_curve(solana.pubkey(ata))
    assert ata == solana.token_account(key.address, KEYS["m-ace"].address)
    assert ata != solana.token_account(KEYS["agent"].address, KEYS["m-ace"].address)
    # The ed25519 base point is on the curve.
    assert solana.on_curve(bytes.fromhex("58" + "66" * 31))


def test_keys_save_and_load_owner_only(tmp_path):
    key = Keypair.generate()
    path = tmp_path / "k.json"
    key.save(str(path))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert Keypair.load(str(path)) == key
    assert len(json.loads(path.read_text())) == 64
    with pytest.raises(FileExistsError):                # never overwrites a key
        key.save(str(path))
    path.write_text(json.dumps(list(key.secret + bytes(32))))
    with pytest.raises(ValueError, match="does not match"):
        Keypair.load(str(path))


def test_a_transfer_message_and_its_signatures():
    payer, agent, mint = Keypair.from_seed_phrase("p"), KEYS["agent"], KEYS["m-ace"].address
    shop = ADDRESSES["m-court"]
    instructions = [solana.create_token_account(payer.address, shop, mint),
                    solana.transfer_checked(mint, agent.address, shop, 148_990_000, 6),
                    solana.memo("ref-1")]
    blockhash = Keypair.from_seed_phrase("bh").address
    message = solana.compile_message(payer.address, instructions, blockhash)
    # two signers: the payer (writable, first) and the agent, whose token
    # account is written but who only signs; read-only unsigned: owner, mint, programs
    signed, readonly_signed, readonly = message[0], message[1], message[2]
    count = message[3]
    keys = [solana.b58encode(message[4 + 32 * i:36 + 32 * i]) for i in range(count)]
    assert (signed, readonly_signed) == (2, 1)
    assert keys[:2] == [payer.address, agent.address]
    assert set(keys[count - readonly:]) == {shop, mint, solana.SYSTEM_PROGRAM,
                                            solana.TOKEN_PROGRAM, solana.ATA_PROGRAM,
                                            solana.MEMO_PROGRAM}
    assert solana.token_account(agent.address, mint) in keys[2:count - readonly]
    assert message[4 + 32 * count:36 + 32 * count] == solana.pubkey(blockhash)
    assert struct.pack("<QB", 148_990_000, 6) in message

    tx = solana.sign_transaction(message, [agent, payer])   # order given doesn't matter
    assert tx[0] == 2 and tx[129:] == message
    for i, key in enumerate((payer, agent)):
        Ed25519PublicKey.from_public_bytes(key.public).verify(tx[1 + 64 * i:65 + 64 * i], message)
    with pytest.raises(ValueError, match="missing signatures"):
        solana.sign_transaction(message, [payer])


def test_the_client_refuses_mainnet():
    with pytest.raises(ValueError, match="devnet only"):
        solana.Rpc("https://api.mainnet-beta.solana.com")

# ---------------------------------------------------------------------------
# The demo script
# ---------------------------------------------------------------------------

DEMO = pathlib.Path(__file__).parent.parent / "scripts" / "demo_crypto_pay.py"


@pytest.mark.skipif(not DEMO.exists(), reason="needs scripts/ from the repository")
def test_the_demo_ends_every_case_as_it_should():
    spec = importlib.util.spec_from_file_location("demo_crypto_pay", DEMO)
    demo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = demo                  # its dataclasses look themselves up here
    try:
        spec.loader.exec_module(demo)
    finally:
        del sys.modules[spec.name]
    network = demo.Simulated()
    for case in demo.CASES:
        plain = demo.run(case, network, guarded_run=False)
        protected = demo.run(case, network, guarded_run=True)
        # without the guard every mistake goes out (or fails on chain, having lost money)
        assert plain["result"]["status"] in ("paid", "failed"), case.title
        assert (protected["result"]["status"] == "paid") == case.should_pay, case.title
        if not case.should_pay:
            assert protected["moved"] == {}, case.title
    # the injected note really did steer the unguarded agent to the thief
    redirect = demo.run(demo.CASES[1], network, guarded_run=False)
    assert redirect["moved"][("thief", "USDC")] == 148.99
