"""Демонстрация песочницы-магазина без языковой модели.

«Наивный» агент делает то, что делают многие: ищет, берёт первый результат
и оформляет заказ. Мандат формально разрешает покупку, Verifiable Intent её
пропускает — а проверка намерения находит, где агент не сделал того, о чём
просили. Факты просьбы заданы вручную, чтобы демо работало без ключей.
"""

from __future__ import annotations

from asasked.coherence import BLOCK, IntentFacts, check_coherence
from asasked.store.catalog_v1 import CATALOG
from asasked.store.store import Mandate, Store

G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"

TASKS = [
    {
        "request": "Black ASICS in size 42, and I need to be able to return them if they don't fit.",
        "facts": IntentFacts(brand="ASICS", color="black", size_label="42", needs_refundable=True),
        "query": "asics shoes 42",
        "category": "shoes", "max_cents": 20000,
    },
    {
        "request": "A cheap beginner racket from HEAD, it has to arrive within 5 days.",
        "facts": IntentFacts(brand="HEAD", level="beginner", price_preference="cheap",
                             deadline_days=5),
        "query": "head racket",
        "category": "racket", "max_cents": 30000,
    },
    {
        "request": "A couple of cans of Penn balls.",
        "facts": IntentFacts(brand="Penn", quantity=2),
        "query": "penn balls",
        "category": "balls", "max_cents": 6000, "qty": 4,
    },
]


def main() -> int:
    store = Store()
    gaps = 0
    for task in TASKS:
        allow = tuple(p["sku"] for p in CATALOG
                      if p["category"] == task["category"] and p["price_cents"] <= task["max_cents"])
        mandate = Mandate(f"A {task['category']}", allow, task.get("qty", 1), 100, task["max_cents"])
        session = store.new_session(mandate)

        # первый результат, который удалось положить в корзину
        qty = task.get("qty", 1)
        for first in session.call("search_products", {"query": task["query"]})["results"]:
            if "error" not in session.call("add_to_cart", {"sku": first["sku"], "quantity": qty}):
                break
        result = session.call("checkout", {"confirm": True})

        print(f"\n{B}Человек:{X} «{task['request']}»")
        print(f"{D}Агент купил:{X} {first['name']} ×{qty}, {first['merchant']}")
        vi_ok = result["status"] == "placed"
        print(f"  Verifiable Intent: {G + 'пропускает' if vi_ok else R + 'отклоняет'}{X}")
        verdict = check_coherence(task["facts"], session.order.purchase,
                                  (mandate.amount_min_cents, mandate.amount_max_cents),
                                  mandate.allowlist, find=store.find)
        print(f"  Сверка намерения:  {G + 'совпадает' if verdict.coherent else Y + 'расходится'}{X}")
        for f in verdict.findings:
            mark = Y if f.severity == BLOCK else D
            print(f"    {mark}·{X} {f.text}")
        gaps += vi_ok and not verdict.coherent

    print(f"\n{B}Итог:{X} VI пропустил и при этом куплено не то: {gaps} из {len(TASKS)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
