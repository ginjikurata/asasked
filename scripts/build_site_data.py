"""Данные для сайта: примеры для «Try it» и открытая половина датасета.

    python scripts/build_site_data.py   # → site/lib/examples.json, site/lib/dataset-open.json

Примеры: для одной открытой задачи каждого шаблона наивный агент (без модели)
покупает первое, что нашёл поиск, — это соблазнительная неправильная корзина,
и VI её пропускает. Затем детерминированная сверка решает по ней и по
правильной покупке из разметки. Факты берутся из разметки задачи (в жизни их
извлекают две модели) — так пример воспроизводим без сети и без ключей.

Датасет: открытые задачи с меткой словами — для страницы /dataset.

Только открытая половина датасета: скрытая на сайт не попадает.
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

# по первой открытой английской задаче шаблона — с понятной с первого взгляда ловушкой
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
        task = tasks[task_id]  # только открытая половина: скрытой здесь нет
        rec = run_task(AGENTS["naive"], task, store=store)
        order = rec["order"]
        if not (order and order.get("placed")) or rec["score"]["as_asked"]:
            raise SystemExit(f"{task_id}: наивный агент не купил ловушку, пример не годится")
        # «правильно — ничего не покупать» (дороже бюджета, нет в наличии): правой корзины нет
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
    assert all(r["split"] == "open" for r in open_rows)  # скрытая половина сюда не попадает
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
