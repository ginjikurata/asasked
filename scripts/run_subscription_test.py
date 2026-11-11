"""Run the hidden-subscription cases (stress_subscription.py) through the guard.

For each case: the guard gets the request and checks the cart; if the case
has a reply, the guard hears it as the answer to its question and checks the
same cart again. Only fact extraction calls a model; there is no agent.

    python scripts/run_subscription_test.py --out runs/subscription.jsonl
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time

from asasked.coherence import extract_intent_agreed
from asasked.guard import ASK, Guard
from asasked.harness.tasks import TODAY
from asasked.stress_subscription import CARTS, CASES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="write one JSON line per case here")
    args = parser.parse_args()

    # Requests repeat across cases: their facts are extracted once.
    extract = functools.lru_cache(maxsize=None)(
        lambda text: extract_intent_agreed(text, today=TODAY))
    out = open(args.out, "w") if args.out else None
    passed = 0
    for n, case in enumerate(CASES, 1):
        rec = {"n": n, "request": case.request, "lang": case.lang, "cart": case.cart,
               "expect": case.expect, "reply": case.reply, "after": case.after}
        started = time.monotonic()
        try:
            guard = Guard(case.request, today=TODAY, extract=extract)
            first = guard.check(CARTS[case.cart])
            rec["got"], rec["reasons"] = first["decision"], first["reasons"]
            if first.get("error"):
                rec["error"] = first["error"]
            ok = first["decision"] == case.expect
            if case.reply is not None:
                if first["decision"] != ASK:
                    rec["skip"] = "the first check did not ask"
                    ok = False
                else:
                    guard.hear(first["question"], case.reply)
                    second = guard.check(CARTS[case.cart])
                    rec["got_after"], rec["reasons_after"] = second["decision"], second["reasons"]
                    ok = ok and second["decision"] == case.after
            facts = guard.facts()
            rec["facts"] = None if facts is None else {
                k: v for k, v in vars(facts).items() if v not in (None, [], {}, "", (), False)}
        except Exception as e:  # noqa: BLE001 - one broken case must not end the run
            rec["exception"] = repr(e)
            ok = False
        rec["ok"] = ok
        rec["seconds"] = round(time.monotonic() - started, 1)
        passed += ok
        if out:
            out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            out.flush()
        print(f"{n:2} {'ok ' if ok else 'BAD'} [{case.lang}] {case.request!r} {case.cart} "
              f"-> {rec.get('got')}"
              + (f" | {case.reply!r} -> {rec.get('got_after')}" if case.reply else "")
              + f" {rec.get('skip', '')}{rec.get('exception', '')}", flush=True)
    print(f"\n{passed} of {len(CASES)} as expected")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
