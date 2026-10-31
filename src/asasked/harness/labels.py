"""A task's label without code: which purchase is right, as data.

A label that can be read, fixed by hand and saved to a file is a must for a
dataset that people label. Python functions (Task.ok_check) cannot do that,
so the dataset uses this format:

    {
      "no_purchase": false,            # right: buy nothing
      "should_ask": false,             # right: ask the person first
      "max_total_cents": 12000,        # the limit for the whole cart (optional)
      "lines": [                       # each line gets exactly one cart line
        {"where": {"family": "ASI-GELRESOLUTION9", "color": "black",
                   "size_label": "42", "refundable": true,
                   "max_ships_in_days": 5},
         "units": 1}
      ]
    }

Conditions in where: a value is an exact match, a list is one of; special
keys: max_price_cents, max_ships_in_days, brand_not (a list of excluded
brands). units is how many "pieces" the person means (cans, not packs).
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
    """Whether the purchase is right by the label. purchase is [(sku, quantity)]."""
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
    """The label in words, for the labellers' table."""
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
