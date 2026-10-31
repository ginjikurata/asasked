"""Conformance vectors for the Verifiable Intent standard.

The standard itself has no such set today: a second implementation cannot
show that it agrees with the first. This script fills that gap, though not in
the way "test vectors" usually do.

Why not a static file of frozen bytes: L3 mandates in this version of the
standard live 5 minutes (exp = iat + 300). A chain serialised once and
committed would be "expired" five minutes later, and every correct
implementation would have to reject it. A frozen vector would turn into a
vector for "we can reject an expired mandate", not what is actually needed.

So a vector here is not bytes but a recipe plus an expectation: this script
takes the eight scenarios from scenarios.py (a person's real request ->
constraints -> purchase), builds a real signed VI chain for each one afresh
(the keys are deterministic, from helpers.py in the SDK itself, not a secret)
and writes it together with what the validator's answer should be: whether
the chain is valid, whether the constraints hold, and which violations exactly.

A second implementation of the standard takes the resulting JSON, validates
the artifacts with its own code and compares its answer with the "expected"
field. A match is the proof of conformance that nobody has today.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from asasked.catalog import find
from asasked.scenarios import SCENARIOS
from asasked.vi_runner import run_vi

OUT_PATH = Path(__file__).resolve().parents[1] / "conformance_vectors.json"


def build_vector(scn) -> dict:
    result = run_vi(scn)
    purchase = [
        {"sku": sku, "name": find(sku)["name"], "quantity": qty}
        for sku, qty in scn.purchase
    ]
    return {
        "id": scn.id,
        "title": scn.title,
        "request": scn.request,
        "prompt_summary": scn.prompt_summary,
        "input": {
            "allowed_merchants": "see catalog.MERCHANTS (2 merchants, both allowed)",
            "allowlist": scn.allowlist,
            "quantity_cap": scn.quantity_cap,
            "amount_min_cents": scn.amount_min_cents,
            "amount_max_cents": scn.amount_max_cents,
            "purchase": purchase,
        },
        "keys": result["keys"],
        "artifacts": result["artifacts"],
        "expected": {
            "chain_valid": result["chain_valid"],
            "chain_errors": result["chain_errors"],
            "constraints_satisfied": result["constraints_ok"],
            "violations": result["violations"],
            "total_cents": result["total_cents"],
        },
    }


def main() -> int:
    vectors = [build_vector(scn) for scn in SCENARIOS]

    doc = {
        "$comment": (
            "Conformance vectors for Verifiable Intent v0.1. "
            "The artifacts (artifacts.*) are real signed SD-JWT chains, "
            "generated with the deterministic demo keys from "
            "verifiable-intent/examples/helpers.py (see keys.*). L3 "
            "mandates live 5 minutes from generation (generated_at): "
            "validate right after generating, do not keep as a static "
            "fixture. How to use: validate "
            "artifacts.layer1/layer2/layer3_payment/layer3_checkout "
            "with your implementation (layer2_payment_presentation is "
            "the selective disclosure already applied for the payment "
            "network) and compare your answer with the expected field. "
            "A match on every vector is evidence of conformance with "
            "this implementation."
        ),
        "generated_at": int(time.time()),
        "valid_for_seconds": 300,
        "vectors": vectors,
    }

    OUT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(vectors)} vectors to {OUT_PATH.name}")
    print(f"Valid for {doc['valid_for_seconds']} seconds from generation "
          f"({time.strftime('%H:%M:%S', time.localtime(doc['generated_at']))}).")
    for v in vectors:
        exp = v["expected"]
        print(f"  [{v['id']:<12}] chain_valid={exp['chain_valid']!s:<5} "
              f"constraints_satisfied={exp['constraints_satisfied']!s:<5} "
              f"violations={len(exp['violations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
