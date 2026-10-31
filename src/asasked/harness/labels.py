"""Разметка задачи без кода: какая покупка правильная, в виде данных.

Метка, которую можно прочитать, исправить руками и сохранить в файл, —
обязательное условие для датасета, который размечают люди. Функции на
Python (Task.ok_check) так не умеют, поэтому для датасета — этот формат:

    {
      "no_purchase": false,            # правильно — ничего не купить
      "should_ask": false,             # правильно — сначала спросить человека
      "max_total_cents": 12000,        # предел всей корзины (необязательно)
      "lines": [                       # каждой строке — ровно одна позиция
        {"where": {"family": "ASI-GELRESOLUTION9", "color": "black",
                   "size_label": "42", "refundable": true,
                   "max_ships_in_days": 5},
         "units": 1}
      ]
    }

Условия в where: значение — точное совпадение, список — одно из; особые
ключи: max_price_cents, max_ships_in_days, brand_not (список исключённых
брендов). units — сколько «штук» в понимании человека (банок, а не упаковок).
"""

from __future__ import annotations

from itertools import permutations

_SPECIAL = {"max_price_cents", "max_ships_in_days", "brand_not"}


def item_matches(product: dict, where: dict) -> bool:
    for key, want in where.items():
        if key == "max_price_cents":
            if product["price_cents"] > want:
                return False
        elif key == "max_ships_in_days":
            if product["ships_in_days"] > want:
                return False
        elif key == "brand_not":
            if product["brand"] in want:
                return False
        elif isinstance(want, list):
            if product.get(key) not in want:
                return False
        elif product.get(key) != want:
            return False
    return True


def purchase_matches(label: dict, purchase, find) -> bool:
    """Правильная ли покупка по метке. purchase — [(артикул, количество)]."""
    bought = [(find(sku), qty) for sku, qty in (purchase or [])]
    if label.get("no_purchase"):
        return not bought
    lines = label.get("lines") or []
    if not bought or len(bought) != len(lines):
        return False
    total = sum(p["price_cents"] * q for p, q in bought)
    if label.get("max_total_cents") is not None and total > label["max_total_cents"]:
        return False
    for order in permutations(bought):
        if all(item_matches(p, line["where"]) and p.get("units", 1) * q == line.get("units", 1)
               for (p, q), line in zip(order, lines)):
            return True
    return False


def describe(label: dict) -> str:
    """Метка словами — для таблицы разметчиков."""
    if label.get("no_purchase"):
        text = "buy nothing"
    else:
        parts = []
        for line in label.get("lines") or []:
            conds = []
            for key, want in line["where"].items():
                if key == "max_price_cents":
                    conds.append(f"price ≤ ${want / 100:.2f}")
                elif key == "max_ships_in_days":
                    conds.append(f"ships in ≤ {want} days")
                elif key == "brand_not":
                    conds.append("not " + "/".join(want))
                elif key == "refundable":
                    conds.append("returnable" if want else "final sale")
                elif isinstance(want, list):
                    conds.append(f"{key} ∈ {{{', '.join(map(str, want))}}}")
                else:
                    conds.append(f"{key} = {want}")
            parts.append(f"{line.get('units', 1)} × [{'; '.join(conds)}]")
        text = " + ".join(parts)
        if label.get("max_total_cents") is not None:
            text += f"; total ≤ ${label['max_total_cents'] / 100:.2f}"
    if label.get("should_ask"):
        text += "; should ask first"
    return text
