"""Run free-form replies to the guard's question (stress_replies.py) through the guard.

For each case: the guard gets the v3 task's request, checks the attacker's cart
(it must ask), hears the person's reply, and checks the carts the case names
again. Only fact extraction calls a model; there is no agent.

    python scripts/run_reply_test.py --out runs/replies.jsonl
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time

from asasked.coherence import extract_intent_agreed
from asasked.guard import ASK, Guard
from asasked.harness import dataset_v3
from asasked.harness.hijacked import _BY_SKU, plan, right_sku
from asasked.harness.tasks import TODAY
from asasked.stress_replies import CASES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="write one JSON line per case here")
    args = parser.parse_args()

    tasks = {t.id: t for t in dataset_v3.load()}
    find = _BY_SKU.__getitem__
    # The four base requests repeat: their facts are extracted once.
    extract = functools.lru_cache(maxsize=None)(
        lambda text: extract_intent_agreed(text, today=TODAY))
    out = open(args.out, "w") if args.out else None
    passed = 0
    for n, case in enumerate(CASES, 1):
        task = tasks[case.task]
        carts = {"attack": plan(task), "right": [(right_sku(task), 1)],
                 "right2": [(right_sku(task), 2)]}
        rec = {"n": n, "task": case.task, "lang": case.lang, "reply": case.reply,
               "expect": case.expect}
        started = time.monotonic()
        try:
            guard = Guard(task.request, today=TODAY, extract=extract)
            first = guard.check(carts["attack"], find=find)
            rec["first"] = first["decision"]
            if first["decision"] != ASK:
                rec["skip"] = "the first check did not ask"
            else:
                guard.hear(first["question"], case.reply)
                rec["got"], rec["reasons"] = {}, {}
                for cart in case.expect:
                    result = guard.check(carts[cart], find=find)
                    rec["got"][cart] = result["decision"]
                    rec["reasons"][cart] = result["reasons"]
                    if result.get("error"):
                        rec["error"] = result["error"]
                facts = guard.facts()
                rec["facts"] = None if facts is None else {
                    k: v for k, v in vars(facts).items() if v not in (None, [], {}, "", ())}
        except Exception as e:  # noqa: BLE001 - one broken case must not end the run
            rec["exception"] = repr(e)
        rec["ok"] = rec.get("got") == case.expect
        rec["seconds"] = round(time.monotonic() - started, 1)
        passed += rec["ok"]
        if out:
            out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            out.flush()
        print(f"{n:2} {'ok ' if rec['ok'] else 'BAD'} {case.task} [{case.lang}] {case.reply!r} "
              f"-> {rec.get('got')} {rec.get('skip', '')}{rec.get('exception', '')}", flush=True)
    print(f"\n{passed} of {len(CASES)} as expected")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
