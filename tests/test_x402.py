"""The x402 hook: real x402 clients and 402 models, a stub scheme instead of a wallet."""

import asyncio

import pytest

pytest.importorskip("x402")

from x402 import x402Client, x402ClientSync  # noqa: E402
from x402.mechanisms.svm.constants import USDC_DEVNET_ADDRESS  # noqa: E402
from x402.mechanisms.svm.default_assets import find_default_asset  # noqa: E402
from x402.schemas import (PaymentAbortedError, PaymentRequired,  # noqa: E402
                          PaymentRequiredV1, PaymentRequirements, PaymentRequirementsV1,
                          ResourceInfo)

from asasked.coherence import IntentFacts  # noqa: E402
from asasked.guard import Guard  # noqa: E402
from asasked.integrations.x402 import X402Guard, guard_x402, network_name, refusal  # noqa: E402

DEVNET = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"
API = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
THIEF = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
UNKNOWN_MINT = "So11111111111111111111111111111111111111112"
TODAY = "Sunday, 15 November 2026"


class StubScheme:
    """Signs nothing: the payload says what it would have paid."""
    scheme = "exact"

    def __init__(self, fail=False):
        self.paid, self.fail = [], fail

    def find_default_asset(self, asset, network):
        # As the real Solana scheme does: the SDK's spend controls ask it.
        return find_default_asset(asset, network)

    def create_payment_payload(self, requirements):
        if self.fail:
            raise RuntimeError("no blockhash")
        self.paid.append(requirements.get_amount())
        return {"transaction": "stub"}


def facts_for(request):
    """Facts as the models would extract them; going over is allowed once the person says so."""
    over = "go over" in request
    return IntentFacts(raw=request, pay_with="USDC", pay_network="solana",
                       explicit_max_cents=None if over else 100)


def make_guard(**kwargs):
    return Guard("Weather for Lisbon, pay in USDC on Solana, no more than $1 in total",
                 today=TODAY, extract=facts_for, **kwargs)


def required(amount, asset=USDC_DEVNET_ADDRESS, pay_to=API, network=DEVNET):
    return PaymentRequired(
        x402_version=2,
        resource=ResourceInfo(url="https://api.example/weather", description="Lisbon forecast"),
        accepts=[PaymentRequirements(scheme="exact", network=network, asset=asset,
                                     amount=str(amount), pay_to=pay_to,
                                     max_timeout_seconds=60, extra={})])


def sync_client(guard, scheme=None, **kwargs):
    client = x402ClientSync()
    client.register(DEVNET, scheme or StubScheme())
    return client, guard_x402(client, guard, **kwargs)


def test_payment_within_the_request_is_signed_and_counted():
    scheme = StubScheme()
    client, x = sync_client(make_guard(payees=[API]), scheme)
    client.create_payment_payload(required(10_000))         # 0.01 USDC
    assert scheme.paid == ["10000"] and x.spent == pytest.approx(0.01)
    assert x.blocked == []


def test_sub_cent_payments_add_up_to_the_limit():
    # 0.005 USDC a call, limit $1: two hundred calls fit, the next one asks.
    scheme = StubScheme()
    client, x = sync_client(make_guard(payees=[API]), scheme)
    for _ in range(200):
        client.create_payment_payload(required(5_000))
    assert x.spent == pytest.approx(1.00)
    with pytest.raises(PaymentAbortedError) as e:
        client.create_payment_payload(required(5_000))
    assert "NOT PAID" in e.value.reason and "$1.00" in e.value.reason
    assert "already paid for this request" in e.value.reason
    assert len(scheme.paid) == 200 and x.spent == pytest.approx(1.00)


def test_the_persons_answer_lets_it_go_on():
    guard = make_guard(payees=[API])
    client, x = sync_client(guard, spent=0.999)
    with pytest.raises(PaymentAbortedError):
        client.create_payment_payload(required(5_000))
    guard.answer("Yes, go over the limit for this one")    # the developer's code
    client.create_payment_payload(required(5_000))
    assert x.spent == pytest.approx(1.004)


def test_a_forged_402_to_another_address_is_refused():
    scheme = StubScheme()
    client, x = sync_client(make_guard(payees=[API]), scheme)
    with pytest.raises(PaymentAbortedError) as e:
        client.create_payment_payload(required(10_000, pay_to=THIEF))
    assert "no answer from the person can approve it" in e.value.reason
    assert scheme.paid == [] and x.spent == 0


def test_without_payees_the_servers_address_is_taken():
    client, x = sync_client(make_guard())
    client.create_payment_payload(required(10_000, pay_to=THIEF))
    assert x.spent == pytest.approx(0.01)
    assert any("pay-unpinned" in str(c) or "address" in " ".join(c.get("notes", []))
               for c in x.guard.checks)


def test_another_network_than_asked_asks():
    guard = Guard("Weather for Lisbon, pay in USDC on Base", today=TODAY,
                  extract=lambda r: IntentFacts(raw=r, pay_with="USDC", pay_network="base"))
    client, _ = sync_client(guard)
    with pytest.raises(PaymentAbortedError) as e:
        client.create_payment_payload(required(10_000))
    assert "Asked to pay on Base" in e.value.reason


def test_a_failed_signature_is_not_counted():
    client, x = sync_client(make_guard(), StubScheme(fail=True))
    with pytest.raises(RuntimeError):
        client.create_payment_payload(required(10_000))
    assert x.spent == 0


def test_async_client():
    scheme = StubScheme()
    client = x402Client()
    client.register(DEVNET, scheme)
    x = X402Guard(make_guard(payees=[API]))
    x.install(client)
    asyncio.run(client.create_payment_payload(required(250_000)))
    assert x.spent == pytest.approx(0.25)
    with pytest.raises(PaymentAbortedError):
        asyncio.run(client.create_payment_payload(required(800_000)))
    assert x.spent == pytest.approx(0.25)


def test_version_1_requests():
    scheme = StubScheme()
    client = x402ClientSync()
    client.register_v1("solana-devnet", scheme)
    x = guard_x402(client, make_guard(payees=[API]))
    req = PaymentRequirementsV1(scheme="exact", network="solana-devnet",
                                max_amount_required="20000", resource="https://api.example/w",
                                description="Lisbon forecast", pay_to=API,
                                max_timeout_seconds=60, asset=USDC_DEVNET_ADDRESS)
    client.create_payment_payload(PaymentRequiredV1(x402_version=1, accepts=[req]))
    assert x.spent == pytest.approx(0.02)
    assert x.guard.checks[-1]["payment"]["network"] == "solana"


def test_amounts_use_the_librarys_decimals_not_the_servers():
    req = required(10_000).accepts[0].model_copy(update={"extra": {"decimals": 2}})
    payment = X402Guard(make_guard()).payment(None, req)
    assert payment["amount"] == 0.01 and payment["token"] == "USDC" and payment["rate"] == 1.0


def test_an_unknown_token_is_not_paid_unless_described():
    req = required(10_000, asset=UNKNOWN_MINT).accepts[0]
    assert X402Guard(make_guard()).payment(None, req).startswith("NOT PAID")
    no_rate = X402Guard(make_guard(), assets={UNKNOWN_MINT: {"token": "wsol", "decimals": 9}})
    assert "worth in dollars" in no_rate.payment(None, req)
    described = X402Guard(make_guard(), assets={
        UNKNOWN_MINT: {"token": "wSOL", "decimals": 9, "rate": 150}})
    payment = described.payment(None, req)
    assert payment["token"] == "WSOL" and payment["amount"] == 0.00001
    assert payment["rate"] == 150.0


def test_network_names():
    assert network_name(DEVNET) == "solana"
    assert network_name("solana-devnet") == "solana"
    assert network_name("eip155:8453") == "base"
    assert network_name("eip155:84532") == "base"
    assert network_name("base-sepolia") == "base"
    assert network_name("eip155:999999") == "eip155:999999"


def test_install_takes_only_x402_clients():
    with pytest.raises(TypeError):
        X402Guard(make_guard()).install(object())


def test_refusal_finds_the_text_inside_the_http_clients_error():
    client, _ = sync_client(make_guard(payees=[API]))
    with pytest.raises(PaymentAbortedError) as caught:
        client.create_payment_payload(required(5_000, pay_to=THIEF))
    try:
        try:
            raise caught.value
        except PaymentAbortedError as e:
            raise RuntimeError("Failed to handle payment") from e   # as x402's clients do
    except RuntimeError as wrapped:
        assert refusal(wrapped) == caught.value.reason
    assert refusal(caught.value).startswith("NOT PAID")
    assert refusal(ValueError("timeout")) is None


def test_base_usdc_is_read_from_the_evm_table():
    pytest.importorskip("eth_abi")                 # x402[evm]
    from x402.mechanisms.evm.default_assets import find_default_asset as evm_asset

    class EvmStub(StubScheme):
        def find_default_asset(self, asset, network):
            return evm_asset(asset, network)

    base_sepolia, usdc = "eip155:84532", "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    guard = Guard("Weather for Lisbon, pay in USDC on Base, no more than $1",
                  today=TODAY, payees=[API.lower()],
                  extract=lambda r: IntentFacts(raw=r, pay_with="USDC", pay_network="base",
                                                explicit_max_cents=100))
    client = x402ClientSync()
    scheme = EvmStub()
    client.register(base_sepolia, scheme)
    x = guard_x402(client, guard)
    client.create_payment_payload(required(250_000, asset=usdc, pay_to=API.lower(),
                                           network=base_sepolia))
    assert scheme.paid == ["250000"] and x.spent == pytest.approx(0.25)
    with pytest.raises(PaymentAbortedError) as e:
        client.create_payment_payload(required(800_000, asset=usdc, pay_to=API.lower(),
                                               network=base_sepolia))
    assert "$0.25 was already paid" in e.value.reason
