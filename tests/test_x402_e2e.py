"""End to end over HTTP: x402's own httpx client and EVM signer (a throwaway key,
Base Sepolia, nothing settled) against a local server that answers 402.
Needs x402[httpx,evm]; skipped without it."""

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("x402")
pytest.importorskip("eth_account")
pytest.importorskip("httpx")

from eth_account import Account  # noqa: E402
from x402 import x402Client  # noqa: E402
from x402.http.clients import x402HttpxClient  # noqa: E402
from x402.http.clients.httpx import PaymentError  # noqa: E402
from x402.http.utils import (decode_payment_signature_header,  # noqa: E402
                             encode_payment_required_header)
from x402.mechanisms.evm.exact.register import register_exact_evm_client  # noqa: E402
from x402.mechanisms.evm.signers import EthAccountSigner  # noqa: E402
from x402.schemas import PaymentRequired, PaymentRequirements, ResourceInfo  # noqa: E402

from asasked.coherence import IntentFacts  # noqa: E402
from asasked.guard import Guard  # noqa: E402
from asasked.integrations.x402 import X402Guard, refusal  # noqa: E402

NET = "eip155:84532"
USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
API = "0x8cbEEe7CD026F1CaAA041FB35d9fdE705dB503C2"
THIEF = "0x1111111111111111111111111111111111111111"
ROUTES = {"/weather": (API, "10000"), "/forged": (THIEF, "10000"), "/pricey": (API, "200000")}


@pytest.fixture
def server():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            pay_to, amount = ROUTES[self.path]
            signed = self.headers.get("PAYMENT-SIGNATURE")
            if signed:
                received.append((self.path, decode_payment_signature_header(signed)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"lisbon": "sunny"}')
                return
            required = PaymentRequired(
                x402_version=2,
                resource=ResourceInfo(url=f"http://127.0.0.1{self.path}",
                                      description="Lisbon forecast"),
                accepts=[PaymentRequirements(scheme="exact", network=NET, asset=USDC,
                                             amount=amount, pay_to=pay_to, max_timeout_seconds=60,
                                             extra={"name": "USDC", "version": "2"})])
            self.send_response(402)
            self.send_header("PAYMENT-REQUIRED", encode_payment_required_header(required))
            self.end_headers()

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", received
    httpd.shutdown()


def facts(request):
    return IntentFacts(raw=request, pay_with="USDC", pay_network="base", explicit_max_cents=10)


def test_signs_the_right_payment_and_stops_the_wrong_ones(server):
    base, received = server
    client = x402Client()
    register_exact_evm_client(client, EthAccountSigner(Account.create()))
    guard = Guard("Weather for Lisbon, pay in USDC on Base, no more than 10 cents in total",
                  today="Sunday, 15 November 2026", extract=facts, payees=[f"{NET}:{API}"])
    hook = X402Guard(guard)
    hook.install(client)

    async def run():
        async with x402HttpxClient(client) as http:
            response = await http.get(base + "/weather")
            stopped = {}
            for path in ("/forged", "/pricey"):
                with pytest.raises(PaymentError) as e:
                    await http.get(base + path)
                stopped[path] = refusal(e.value)
            return response, stopped

    response, stopped = asyncio.run(run())
    assert response.status_code == 200
    assert [path for path, _ in received] == ["/weather"]      # nothing else was signed
    authorization = received[0][1].payload["authorization"]
    assert authorization["to"].lower() == API.lower() and authorization["value"] == "10000"
    assert hook.spent == pytest.approx(0.01)
    assert "not an address the person approved" in stopped["/forged"]
    assert stopped["/pricey"] and "NOT PAID" in stopped["/pricey"]
