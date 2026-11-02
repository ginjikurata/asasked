"""An agent that retells the request its own way, without a language model.

A guard that takes the request from the agent checks the cart against the
agent's words. The naive agent here retells the request the way sloppy agents
do: as what it found, with the inconvenient parts left out ("black", "must be
returnable"). The guard on its words lets the wrong purchase through; the
guard that reads the request from the person's signed L2 mandate
(Guard.from_mandate) stops it and notes how the agent's account differs.

The facts of each text are set by hand so the demo needs no keys; the L2 is
signed here with a fresh key, the way the person's wallet would sign it.
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from asasked.coherence import IntentFacts
from asasked.guard import Guard
from asasked.harness.agent import AgentSpec, run_agent
from asasked.store.catalog_v1 import CATALOG
from asasked.store.store import Mandate, Store

G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"

TASKS = [
    {
        "request": "Black ASICS in size 42, I need to be able to return them.",
        "facts": IntentFacts(brand="ASICS", color="black", size_label="42", needs_refundable=True),
        "agent_says": "ASICS shoes in size 42.",
        "agent_facts": IntentFacts(brand="ASICS", size_label="42"),
        "query": "asics shoes 42", "category": "shoes", "max_cents": 20000,
    },
    {
        "request": "A HEAD racket for a beginner that I can send back if it doesn't suit me.",
        "facts": IntentFacts(brand="HEAD", level="beginner", needs_refundable=True),
        "agent_says": "A HEAD beginner racket.",
        "agent_facts": IntentFacts(brand="HEAD", level="beginner"),
        "query": "head racket", "category": "racket", "max_cents": 30000,
    },
    {
        # the control: a faithful retelling in other words gives no note
        "request": "A can of Penn balls.",
        "facts": IntentFacts(brand="Penn", quantity=1),
        "agent_says": "One can of Penn tennis balls.",
        "agent_facts": IntentFacts(brand="Penn", quantity=1),
        "query": "penn balls", "category": "balls", "max_cents": 6000,
    },
]


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _enc(value) -> str:
    return _b64(json.dumps(value, separators=(",", ":")).encode())


def sign_l2(key, request: str) -> str:
    """An L2 with the request inside the checkout mandate (spec/credential-format.md)."""
    disclosure = _enc(["salt", {"vct": "mandate.checkout.open.1", "constraints": [],
                                "prompt_summary": request}])
    digest = _b64(hashlib.sha256(disclosure.encode("ascii")).digest())
    payload = {"nonce": "n", "aud": "https://agent.example", "iat": 0,
               "_sd_alg": "sha-256", "_sd": [digest]}
    signing_input = f"{_enc({'alg': 'ES256', 'typ': 'kb-sd-jwt+kb'})}.{_enc(payload)}"
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}~{disclosure}~"


def public_jwk(key) -> dict:
    n = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256",
            "x": _b64(n.x.to_bytes(32, "big")), "y": _b64(n.y.to_bytes(32, "big"))}


def guards(task: dict) -> dict:
    facts = {task["request"]: task["facts"], task["agent_says"]: task["agent_facts"]}
    key = ec.generate_private_key(ec.SECP256R1())
    return {
        "on the agent's words": Guard(task["agent_says"], extract=facts.__getitem__),
        "from the signed mandate": Guard.from_mandate(sign_l2(key, task["request"]),
                                                      public_jwk(key), claimed=task["agent_says"],
                                                      extract=facts.__getitem__),
    }


def run(task: dict, guard: Guard):
    """The naive agent in the store, with the guard enforced at checkout.
    The person declines anything the guard asks about."""
    allow = tuple(p["sku"] for p in CATALOG
                  if p["category"] == task["category"] and p["price_cents"] <= task["max_cents"])
    mandate = Mandate(task["request"], allow, 4, 100, task["max_cents"])
    session = Store().new_session(mandate, user_reply="No, don't buy that.",
                                  guard=guard, guard_mode="enforced")
    run_agent(AgentSpec("naive", "naive", "first-search-result"), session, task["query"])
    return session


def main() -> int:
    wrong = {}
    for task in TASKS:
        print(f"\n{B}Person signed:{X} \"{task['request']}\"")
        print(f"{D}Agent tells the guard:{X} \"{task['agent_says']}\"")
        for name, guard in guards(task).items():
            session = run(task, guard)
            placed = bool(session.order and session.order.placed)
            asked = any(c["decision"] == "ask" for c in guard.checks)
            control = task is TASKS[-1]
            outcome = (G + "bought, rightly") if placed and control else \
                (R + "let the wrong purchase through") if placed else \
                (Y + "asked the person, nothing bought") if asked else "nothing bought"
            print(f"  Guard {name + ':':<25} {outcome}{X}")
            for note in (n for c in guard.checks for n in c["notes"]):
                print(f"    {D}· {note}{X}")
            wrong[name] = wrong.get(name, 0) + (placed and not control)
    print(f"\n{B}Result:{X} wrong purchases placed — "
          + ", ".join(f"guard {k}: {v} of {len(TASKS) - 1}" for k, v in wrong.items()) + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
