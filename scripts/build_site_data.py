"""Site data: the "Try it" examples and the open half of the dataset.

    python scripts/build_site_data.py   # -> site/lib/examples.json, site/lib/dataset-open.json

Examples: for one open task of each template, a naive agent (no model) buys
the first thing search found. That is the tempting wrong cart, and VI lets it
through. Then the deterministic check decides on it and on the right purchase
from the label. The facts come from the task's label (in real use two models
extract them), so the example is reproducible with no network and no keys.

Dataset: open tasks with the label in words, for the /dataset page.

The open half of the dataset only: the hidden one never reaches the site.
"""

from __future__ import annotations

import json
from pathlib import Path

from asasked.coherence import decide_before_purchase
from asasked.harness.agent import AGENTS
from asasked.harness.dataset import load, rows as dataset_rows
from asasked.harness.labels import describe
from asasked.harness.run import run_task
from asasked.store.store import Store

SITE_LIB = Path(__file__).resolve().parent.parent / "site" / "lib"
OUT = SITE_LIB / "examples.json"
DATASET_OUT = SITE_LIB / "dataset-open.json"

# the first open English task of each template, with a trap that is clear at a glance
TEMPLATES = ["refund-variant", "deadline", "cheapest-returnable", "soft-colour", "cans",
             "exclusion", "two-sizes", "over-budget"]


def cart(store: Store, purchase) -> list[dict]:
    out = []
    for sku, qty in purchase:
        p = store.find(sku)
        out.append({"name": p["name"], "qty": qty, "price": f"${p['price_cents'] / 100:.2f}",
                    "merchant": p["merchant_name"],
                    "returns": "returnable" if p["refundable"] else "final sale",
                    "delivery_days": p["ships_in_days"]})
    return out


def decide(store: Store, task, purchase) -> dict:
    mandate = task.mandate()
    d = decide_before_purchase(task.facts, purchase,
                               (mandate.amount_min_cents, mandate.amount_max_cents),
                               mandate.allowlist, find=store.find)
    return {"decision": d.action, "reasons": [f.text for f in d.reasons], "question": d.question}


def main() -> int:
    tasks = {t.id: t for t in load(split="open")}
    rows = {r["id"]: r for r in dataset_rows(split="open")}
    store = Store()
    examples = []
    picks = [next(i for i, r in rows.items() if r["template"] == t and r["lang"] == "en"
                  and r["split"] == "open") for t in TEMPLATES]
    for task_id in picks:
        task = tasks[task_id]  # the open half only: the hidden one is not here
        rec = run_task(AGENTS["naive"], task, store=store)
        order = rec["order"]
        if not (order and order.get("placed")) or rec["score"]["as_asked"]:
            raise SystemExit(f"{task_id}: the naive agent did not buy the trap, the example is unusable")
        # "the right thing is to buy nothing" (over budget, out of stock): no right cart
        right = rows[task_id]["right_purchase"]
        right = [tuple(x) for x in right] if right else None
        examples.append({
            "id": task.id,
            "template": rows[task_id]["template"],
            "request": task.request,
            "trap": task.trap,
            "wrong": {"cart": cart(store, order["purchase"]), "vi": "passed",
                      **decide(store, task, order["purchase"])},
            "right": None if right is None else {"cart": cart(store, right), "vi": "passed",
                                                 **decide(store, task, right)},
        })
        print(task_id, examples[-1]["wrong"]["decision"], (examples[-1]["right"] or {}).get("decision"))
    OUT.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("→", OUT)

    open_rows = [r for r in rows.values() if r["split"] == "open"]
    assert all(r["split"] == "open" for r in open_rows)  # the hidden half never gets here
    dataset = [{
        "id": r["id"], "template": r["template"], "lang": r["lang"], "request": r["request"],
        "label": describe(r["label"]), "should_ask": bool(r["label"].get("should_ask")),
        "buy_nothing": bool(r["label"].get("no_purchase")), "trap": r["trap"],
    } for r in sorted(open_rows, key=lambda r: r["id"])]
    DATASET_OUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("→", DATASET_OUT, len(dataset), "open tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
