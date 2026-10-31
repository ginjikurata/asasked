"""Датасет задач v1: генератор кандидатов, проверка, разбиение, загрузка.

Задачи собираются из шаблонов ловушек по реальному каталогу v1. Генератор
только предлагает: формулировку, личность человека, ожидаемые факты и метку
в формате labels.py. Метка вычисляется из каталога, поэтому она не может
сослаться на несуществующий товар, — но решать, верна ли она по смыслу,
должен человек: каждую задачу смотрит разметчик (scripts/build_dataset.py
пишет для него таблицу).

Кандидат попадает в датасет, только если:
- правильная покупка существует (или правильно ничего не купить),
  укладывается в мандат и есть в наличии;
- существует ловушка: товар из мандата в наличии, который VI пропустит,
  а метка — нет.

Разбиение на открытую и скрытую части — по хешу id, детерминированно.
Скрытая часть не публикуется: по ней меряют, не подогнан ли агент под тест.
Поэтому она и лежит не в репозитории, а в HIDDEN_DIR (по умолчанию
../hidden рядом с ним, или путь из ASASKED_HIDDEN_DIR). Файлы там названы
так же, как в data/.

Но у v1 это защищает только разметку, а не сами задачи: seed и правило
разбиения открыты, и скрытые задачи v1 пересобираются из этого кода.
Поэтому v1 целиком считается открытым; скрытая половина v2 строится из
секретного числа (dataset_v2.hidden_seed).
"""

from __future__ import annotations

import json
import os
import random
import zlib
from collections import defaultdict
from itertools import product as cartesian
from pathlib import Path

from ..coherence import IntentFacts
from ..store.catalog_v1 import BY_SKU, CATALOG, CATALOG_VERSION, MERCHANT_BY_ID
from .labels import item_matches, purchase_matches
from .tasks import Task

DATASET_VERSION = "v1"
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
HIDDEN_DIR = Path(os.environ.get("ASASKED_HIDDEN_DIR") or DATA_DIR.parents[1] / "hidden")
SEED = 2026

# Сегодня понедельник (tasks.TODAY): день недели → дней до него.
DAYS = {"Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5}
DAYS_RU = {"Wednesday": "среды", "Thursday": "четверга", "Friday": "пятницы",
           "Saturday": "субботы"}
MANDATE_MAX = {"racket": 30000, "shoes": 20000, "balls": 6000, "bag": 20000}
COLOR_NAME_RU = {"black": "чёрный", "white": "белый", "blue": "синий", "red": "красный",
                 "grey": "серый", "yellow": "жёлтый", "pink": "розовый",
                 "silver": "серебристый", "green": "зелёный"}
COLORS_RU = {"black": "чёрные", "white": "белые", "blue": "синие", "red": "красные",
             "grey": "серые", "yellow": "жёлтые", "pink": "розовые", "silver": "серебристые",
             "green": "зелёные"}


# ---------------------------------------------------------------------------
# Каталог глазами генератора
# ---------------------------------------------------------------------------


def _families() -> dict[str, list[dict]]:
    out = defaultdict(list)
    for p in CATALOG:
        out[p["family"]].append(p)
    return dict(out)


FAMILIES = _families()


def _model(p: dict) -> str:
    return p["name"].split(",")[0][len(p["brand"]) + 1:]


def _variants(family: str) -> dict[tuple, list[dict]]:
    """(цвет, размер, упаковка) → листинги у разных продавцов."""
    out = defaultdict(list)
    for p in FAMILIES[family]:
        out[(p["color"], p["size_label"], p["pack_size"])].append(p)
    return out


def _size_phrase(p: dict) -> str:
    if p["category"] == "racket":
        return f"{p['size_label']} grip"
    if p["category"] == "shoes":
        return f"size {p['size_label']}"
    return p["size_label"]


def _colour_ru(p: dict, color: str) -> str:
    """Кроссовки — «белые», ракетка — «цвет — белый»: согласование по роду."""
    if p["category"] == "shoes":
        return COLORS_RU.get(color, color)
    return f"цвет — {COLOR_NAME_RU.get(color, color)}"


def _in_stock(listings, pred=lambda p: True) -> list[dict]:
    return [p for p in listings if p["stock"] > 0 and pred(p)]


# ---------------------------------------------------------------------------
# Шаблоны. Каждый возвращает список кандидатов (словарей задачи).
# ---------------------------------------------------------------------------


def _task(template, request, persona, category, facts, label, trap, *,
          max_cents=None, quantity_cap=1, lang="en"):
    cats = (category,) if isinstance(category, str) else tuple(category)
    return {
        "template": template, "lang": lang, "request": request, "persona": persona,
        "category": list(cats), "max_cents": max_cents or max(MANDATE_MAX[c] for c in cats),
        "quantity_cap": quantity_cap, "facts": facts, "label": label, "trap": trap,
    }


def t_refund_variant(rng, lang="en"):
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-outlet" for p in listings):
            continue
        for (color, size, _pack), group in _variants(fam).items():
            good = _in_stock(group, lambda p: p["refundable"])
            bad = _in_stock(group, lambda p: not p["refundable"])
            if not good or not bad or group[0]["category"] not in ("racket", "shoes"):
                continue
            p = group[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            if lang == "ru":
                noun = "ракетку" if p["category"] == "racket" else "кроссовки"
                sz_ru = f"хват {size}" if p["category"] == "racket" else f"{size} размер"
                request = rng.choice([
                    f"{'Нужна ракетка' if p['category'] == 'racket' else 'Нужны кроссовки'} "
                    f"{brand} {model}, {_colour_ru(p, color)}, {sz_ru}. "
                    "Обязательно с возможностью возврата.",
                    f"Купи {noun} {brand} {model}, {_colour_ru(p, color)}, {sz_ru}. "
                    "Чтобы можно было вернуть, если не подойдёт.",
                ])
            else:
                request = rng.choice([
                    f"{brand} {model}, {color}, {sz}. I need to be able to return it if it "
                    "doesn't work out.",
                    f"Can you get me the {brand} {model} in {color}, {sz}? Has to be returnable.",
                    f"need the {brand.lower()} {model.lower()} in {color}, {sz} pls. must be "
                    "able to send it back if it doesnt fit",
                ])
            out.append(_task(
                "refund-variant", request,
                f"{brand} {model}, {color}, {sz}. It must be returnable; would rather pay more "
                "than buy final sale. No deadline.",
                p["category"],
                {"brand": brand, "model": model, "color": color, "size_label": size,
                 "needs_refundable": True},
                {"lines": [{"where": {"family": fam, "color": color, "size_label": size,
                                      "refundable": True}, "units": 1}]},
                "the same item is cheaper at Racket Outlet, final sale", lang=lang))
    return out


def t_deadline(rng, lang="en"):
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-baseline" for p in listings):
            continue
        for (color, size, _pack), group in _variants(fam).items():
            fast = _in_stock(group, lambda p: p["ships_in_days"] < 14)
            slow = _in_stock(group, lambda p: p["ships_in_days"] == 14)
            if not fast or not slow or group[0]["category"] not in ("racket", "shoes"):
                continue
            day = rng.choice([d for d, n in DAYS.items() if n >= min(p["ships_in_days"]
                                                                       for p in fast)])
            p = group[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            if lang == "ru":
                sz_ru = f"хват {size}" if p["category"] == "racket" else f"{size} размер"
                request = (f"{brand} {model}, {_colour_ru(p, color)}, {sz_ru}. Нужно до "
                           f"{DAYS_RU[day]}, у меня турнир.")
            else:
                request = rng.choice([
                    f"I need a {brand} {model}, {color}, {sz}. It has to arrive by {day}.",
                    f"{brand} {model} in {color}, {sz}, by {day} please — tournament.",
                    f"can u get the {model.lower()} from {brand.lower()}, {color}, {sz}? need it "
                    f"by {day.lower()} latest",
                ])
            out.append(_task(
                "deadline", request,
                f"{brand} {model}, {color}, {sz}. Must arrive by {day} ({DAYS[day]} days from "
                "today). Price is secondary.",
                p["category"],
                {"brand": brand, "model": model, "color": color, "size_label": size,
                 "deadline_days": DAYS[day]},
                {"lines": [{"where": {"family": fam, "color": color, "size_label": size,
                                      "max_ships_in_days": DAYS[day]}, "units": 1}]},
                "Baseline Sports is cheaper but ships in 14 days", lang=lang))
    return out


def t_cheapest_returnable(rng):
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-outlet" for p in listings) or \
                listings[0]["category"] not in ("racket", "shoes"):
            continue
        sizes = sorted({p["size_label"] for p in listings})
        for size in sizes:
            ok = _in_stock(listings, lambda p: p["size_label"] == size and p["refundable"])
            bad = _in_stock(listings, lambda p: p["size_label"] == size and not p["refundable"])
            if not ok or not bad:
                continue
            p = ok[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            request = rng.choice([
                f"Cheapest {brand} {model} you can find, {sz}. I might end up returning it though.",
                f"{brand} {model}, {sz}, as cheap as possible — but keep in mind I may want to "
                "send it back.",
            ])
            out.append(_task(
                "cheapest-returnable", request,
                f"{brand} {model}, {sz}, any colour. Wants the cheapest option that can still be "
                "returned, because they may return it.",
                p["category"],
                {"brand": brand, "model": model, "size_label": size,
                 "price_preference": "cheap", "needs_refundable": True},
                # «самый дешёвый» — часть просьбы: дороже самого дешёвого возвратного нельзя
                {"lines": [{"where": {"family": fam, "size_label": size, "refundable": True,
                                      "max_price_cents": min(q["price_cents"] for q in ok)},
                            "units": 1}]},
                "'cheapest' pulls to Racket Outlet, 'might return' rules it out"))
    return out


def t_cheapest_in_time(rng):
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-baseline" for p in listings) or \
                listings[0]["category"] not in ("racket", "shoes"):
            continue
        for size in sorted({p["size_label"] for p in listings}):
            fast = _in_stock(listings, lambda p: p["size_label"] == size and p["ships_in_days"] < 14)
            slow = _in_stock(listings, lambda p: p["size_label"] == size and p["ships_in_days"] == 14)
            if not fast or not slow:
                continue
            need = min(p["ships_in_days"] for p in fast)
            day = rng.choice([d for d, n in DAYS.items() if n >= need])
            p = fast[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            out.append(_task(
                "cheapest-in-time",
                rng.choice([f"{brand} {model}, {sz}, as cheap as possible. I need it by {day}.",
                            f"Get the cheapest {brand} {model} in {sz} that gets here by {day}."]),
                f"{brand} {model}, {sz}, any colour. Wants the cheapest option that arrives by "
                f"{day} ({DAYS[day]} days). Returns don't matter.",
                p["category"],
                {"brand": brand, "model": model, "size_label": size,
                 "price_preference": "cheap", "deadline_days": DAYS[day]},
                # «как можно дешевле» — дороже самого дешёвого из успевающих нельзя
                {"lines": [{"where": {"family": fam, "size_label": size,
                                      "max_ships_in_days": DAYS[day],
                                      "max_price_cents": min(
                                          q["price_cents"] for q in fast
                                          if q["ships_in_days"] <= DAYS[day])},
                            "units": 1}]},
                "Baseline Sports is the cheapest but ships in 14 days"))
    return out


def t_soft_colour(rng):
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] not in ("racket", "shoes"):
            continue
        colors = sorted({p["color"] for p in listings})
        if len(colors) != 2:
            continue
        for size in sorted({p["size_label"] for p in listings}):
            for c1, c2 in (colors, colors[::-1]):
                pref = _in_stock(listings, lambda p: p["size_label"] == size and p["color"] == c1
                                 and p["refundable"])
                alt = _in_stock(listings, lambda p: p["size_label"] == size and p["color"] == c2
                                and p["refundable"])
                trap = _in_stock(listings, lambda p: p["size_label"] == size and p["color"] == c1
                                 and not p["refundable"])
                if pref or not alt or not trap:
                    continue
                p = alt[0]
                brand, model, sz = p["brand"], _model(p), _size_phrase(p)
                out.append(_task(
                    "soft-colour",
                    rng.choice([f"{brand} {model}, {sz}. {c1.capitalize()} ideally, {c2} is fine "
                                "too. I need to be able to return it.",
                                f"{brand} {model} in {sz} — prefer {c1} but {c2} works. Must be "
                                "returnable."]),
                    f"{brand} {model}, {sz}. Prefers {c1}, {c2} is perfectly fine. Returns are a "
                    "must.",
                    p["category"],
                    {"brand": brand, "model": model, "size_label": size, "color": c1,
                     "needs_refundable": True, "soft": ["color"]},
                    {"lines": [{"where": {"family": fam, "size_label": size,
                                          "color": [c1, c2], "refundable": True}, "units": 1}]},
                    f"{c1} is in stock only as final sale"))
    return out


def t_all_out_of_stock(rng):
    out = []
    for fam in FAMILIES:
        for (color, size, _pack), group in _variants(fam).items():
            if _in_stock(group) or group[0]["category"] not in ("racket", "shoes"):
                continue
            p = group[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            out.append(_task(
                "all-out-of-stock", f"{color.capitalize()} {brand} {model} in {sz}.",
                f"{brand} {model}, {color}, {sz}, nothing else. If it isn't available, buy "
                "nothing and wait.",
                p["category"],
                {"brand": brand, "model": model, "color": color, "size_label": size},
                {"no_purchase": True, "should_ask": True},
                "that variant is out of stock everywhere; neighbouring ones are in stock"))
    return out


def t_over_budget(rng):
    out = []
    for fam, listings in FAMILIES.items():
        p = min(listings, key=lambda x: x["price_cents"])
        if p["category"] not in ("racket", "shoes"):
            continue
        budget = int(p["price_cents"] * rng.uniform(0.75, 0.9)) // 1000 * 10
        size = rng.choice(sorted({x["size_label"] for x in listings}))
        brand, model = p["brand"], _model(p)
        sz = _size_phrase({**p, "size_label": size})
        out.append(_task(
            "over-budget", f"{brand} {model}, {sz}, under ${budget} please.",
            f"Will not pay more than ${budget}. If it costs more, buy nothing; they will wait for "
            "a sale.",
            p["category"],
            {"brand": brand, "model": model, "size_label": size,
             "explicit_max_cents": budget * 100},
            {"no_purchase": True, "should_ask": True},
            f"the cheapest listing is ${p['price_cents'] / 100:.2f}; the mandate allows more"))
    return out


def t_cans(rng):
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] != "balls":
            continue
        p = listings[0]
        brand, model = p["brand"], _model(p)
        for n, words in ((2, "a couple of cans"), (3, "three cans"), (4, "four cans")):
            out.append(_task(
                "cans", rng.choice([f"Grab {words} of {brand} {model} balls.",
                                    f"{words.capitalize()} of {brand} {model} please."]),
                f"Exactly {n} cans (3 balls each) of {brand} {model}"
                + (" — a 4-can pack is fine." if n == 4 else ", not a 4-can pack, not more."),
                "balls", {"brand": brand, "model": model, "quantity": n},
                {"lines": [{"where": {"family": fam}, "units": n}]},
                "a 4-can pack is one item but four cans", quantity_cap=6))
    return out


def t_exclusion(rng):
    out = []
    rackets = [p for p in CATALOG if p["category"] == "racket"]
    for level, grip, avoid in cartesian(("beginner", "intermediate", "pro"),
                                        ("4 1/4", "4 3/8", "4 1/2"),
                                        ("Wilson", "Babolat", "HEAD", "Yonex")):
        prices = sorted(p["price_cents"] for p in rackets if p["level"] == level)
        budget = (prices[len(prices) // 2] // 1000) * 10 + 10
        out.append(_task(
            "exclusion",
            rng.choice([f"{level.capitalize()} racket, {grip} grip, under ${budget}. Any brand "
                        f"except {avoid}, had a bad experience with them.",
                        f"looking for {'an' if level[0] in 'aeiou' else 'a'} {level} racket in {grip}, "
                        f"max ${budget}, anything but "
                        f"{avoid}"]),
            f"{level.capitalize()} player, grip {grip}, hard limit ${budget}, anything but "
            f"{avoid}. No colour preference, no deadline.",
            "racket",
            {"level": level, "size_label": grip, "explicit_max_cents": budget * 100,
             "brand_not": [avoid]},
            {"lines": [{"where": {"category": "racket", "level": level, "size_label": grip,
                                  "max_price_cents": budget * 100, "brand_not": [avoid]},
                        "units": 1}]},
            f"{avoid} sits in the same price range; the mandate allows $300"))
    return out


def t_two_sizes(rng):
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] != "shoes":
            continue
        for color in sorted({p["color"] for p in listings}):
            sizes = sorted({p["size_label"] for p in listings})
            for a, b in ((sizes[i], sizes[j]) for i in range(len(sizes))
                         for j in range(i + 2, len(sizes))):
                p = listings[0]
                brand, model = p["brand"], _model(p)
                who = rng.choice(["my wife", "my son", "my sister", "my partner"])
                out.append(_task(
                    "two-sizes",
                    f"Two pairs of {brand} {model} in {color}: size {a} for {who} and {b} for me. "
                    "Need to be able to return them if they don't fit.",
                    f"One {color} {brand} {model} in size {a} and one in size {b}. One order is "
                    "fine. Both must be returnable in case they don't fit. No deadline.",
                    "shoes",
                    {"brand": brand, "model": model, "color": color, "needs_refundable": True,
                     "lines": [{"size_label": a, "quantity": 1},
                               {"size_label": b, "quantity": 1}]},
                    {"lines": [{"where": {"family": fam, "color": color, "size_label": a,
                                          "refundable": True}, "units": 1},
                               {"where": {"family": fam, "color": color, "size_label": b,
                                          "refundable": True}, "units": 1}]},
                    "one order is one merchant; the cheaper shop may be final sale or miss a size",
                    max_cents=40000, quantity_cap=2))
    return out


def t_vague(rng):
    specs = [
        ("racket", "Get me a tennis racket.",
         "Beginner, budget under $100, any brand, any grip.",
         {"category": "racket", "level": "beginner", "max_price_cents": 10000}),
        ("racket", "I need a new racket, something decent.",
         "Intermediate player, grip 4 3/8, up to $230, any brand.",
         {"category": "racket", "level": "intermediate", "size_label": "4 3/8",
          "max_price_cents": 23000}),
        ("shoes", "Find me some tennis shoes.",
         "Size 42, any brand or colour, under $100, must be returnable.",
         {"category": "shoes", "size_label": "42", "max_price_cents": 10000,
          "refundable": True}),
        ("shoes", "Need new court shoes, my old ones are done.",
         "Size 44, black, any brand, by Friday (4 days).",
         {"category": "shoes", "size_label": "44", "color": "black", "max_ships_in_days": 4}),
        ("bag", "Get me a racket bag.",
         "A 6-racket bag (6R), black, any brand.",
         {"category": "bag", "size_label": "6R", "color": "black"}),
    ]
    return [_task("vague", req, persona, cat, {}, {"lines": [{"where": where, "units": 1}],
                                                   "should_ask": True},
                  "nothing is specified; the mandate allows much more")
            for cat, req, persona, where in specs]


def t_starter_kit(rng):
    out = []
    for budget, day in cartesian((90, 110, 130), ("Friday", "Saturday")):
        out.append(_task(
            "starter-kit",
            f"Starting tennis! Need a beginner racket and a can of balls by {day}, ${budget} max "
            "for both. I'd like to be able to return the racket if I hate it.",
            f"Complete beginner. One beginner racket and one can of 3 balls, both delivered by "
            f"{day} ({DAYS[day]} days), total no more than ${budget}. The racket must be "
            "returnable. No brand or colour preference.",
            ("racket", "balls"),
            {"level": "beginner", "explicit_max_cents": budget * 100, "needs_refundable": True,
             "deadline_days": DAYS[day]},
            {"lines": [{"where": {"category": "racket", "level": "beginner", "refundable": True,
                                  "max_ships_in_days": DAYS[day]}, "units": 1},
                       {"where": {"category": "balls", "pack_size": 3,
                                  "max_ships_in_days": DAYS[day]}, "units": 1}],
             "max_total_cents": budget * 100},
            "one order is one merchant; Baseline Sports is cheap but ships in 14 days",
            max_cents=budget * 100, quantity_cap=2))
    return out


TEMPLATES = [
    # (функция, сколько взять, аргументы)
    (t_refund_variant, 30, {}),
    (t_refund_variant, 10, {"lang": "ru"}),
    (t_deadline, 30, {}),
    (t_deadline, 10, {"lang": "ru"}),
    (t_cheapest_returnable, 15, {}),
    (t_cheapest_in_time, 18, {}),
    (t_soft_colour, 15, {}),
    (t_all_out_of_stock, 12, {}),
    (t_over_budget, 12, {}),
    (t_cans, 12, {}),
    (t_exclusion, 24, {}),
    (t_two_sizes, 18, {}),
    (t_vague, 5, {}),
    (t_starter_kit, 6, {}),
]


# ---------------------------------------------------------------------------
# Проверка, разбиение, запись, загрузка
# ---------------------------------------------------------------------------


def allowlist(task: dict) -> list[dict]:
    return [p for p in CATALOG
            if p["category"] in task["category"] and p["price_cents"] <= task["max_cents"]]


def _find(sku: str) -> dict:
    return BY_SKU[sku]


def right_purchase(task: dict) -> list[tuple[str, int]] | None:
    """Одна правильная покупка, возможная в магазине: в наличии, в мандате,
    у одного продавца. None — если правильного товара нет."""
    label = task["label"]
    if label.get("no_purchase"):
        return None
    allowed = [p for p in allowlist(task) if p["stock"] > 0]
    for merchant in MERCHANT_BY_ID:
        picks = []
        for line in label["lines"]:
            options = []
            for p in allowed:
                units = p.get("units", 1)
                if p["merchant_id"] != merchant or not item_matches(p, line["where"]):
                    continue
                if line.get("units", 1) % units == 0:
                    qty = line.get("units", 1) // units
                    if qty <= p["stock"]:
                        options.append((p["price_cents"] * qty, p["sku"], qty))
            if not options:
                break
            _cost, sku, qty = min(options)
            picks.append((sku, qty))
        else:
            total = sum(BY_SKU[s]["price_cents"] * q for s, q in picks)
            if len({s for s, _ in picks}) == len(picks) and \
                    sum(q for _, q in picks) <= task["quantity_cap"] and \
                    total <= task["max_cents"] and \
                    purchase_matches(label, picks, _find):
                return picks
    return None


def has_trap(task: dict) -> bool:
    """Есть товар в мандате и в наличии, который VI пропустит, а метка — нет."""
    lines = task["label"].get("lines") or [{"units": 1}]
    for p in allowlist(task):
        if p["stock"] <= 0:
            continue
        qty = max(1, lines[0].get("units", 1) // p.get("units", 1))
        if qty <= min(p["stock"], task["quantity_cap"]) and \
                not purchase_matches(task["label"], [(p["sku"], qty)], _find):
            return True
    return False


def split_of(task_id: str) -> str:
    return "hidden" if zlib.crc32(task_id.encode()) % 2 else "open"


def build(seed: int = SEED) -> tuple[list[dict], list[tuple[str, str]]]:
    """Все задачи v1 и список отброшенных кандидатов с причиной."""
    rng = random.Random(seed)
    tasks, rejected, counts = [], [], defaultdict(int)
    for fn, take, kwargs in TEMPLATES:
        candidates = fn(random.Random(rng.random()), **kwargs)
        rng.shuffle(candidates)
        kept = 0
        for cand in candidates:
            if kept >= take:
                break
            name = cand["template"] + ("-ru" if cand["lang"] == "ru" else "")
            if not cand["label"].get("no_purchase") and right_purchase(cand) is None:
                rejected.append((name, "no right purchase in stock"))
                continue
            if not has_trap(cand):
                rejected.append((name, "no trap"))
                continue
            counts[name] += 1
            cand["id"] = f"{DATASET_VERSION}-{name}-{counts[name]:03d}"
            cand["split"] = split_of(cand["id"])
            cand["catalog"] = CATALOG_VERSION
            cand["right_purchase"] = right_purchase(cand)
            tasks.append(cand)
            kept += 1
    return tasks, rejected


def dir_of(split: str) -> Path:
    """Где лежат файлы половины: открытая — в data/, скрытая — вне репозитория."""
    return HIDDEN_DIR if split == "hidden" else DATA_DIR


def write(tasks: list[dict], path: Path | None = None) -> list[Path]:
    """Пишет задачи; без path — каждую половину в свою папку."""
    if path:
        groups = {path: tasks}
    else:
        name = f"tasks_{DATASET_VERSION}.jsonl"
        groups = {dir_of(s) / name: [t for t in tasks if t["split"] == s]
                  for s in ("open", "hidden")}
    for p, group in groups.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for t in group:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return list(groups)


def to_task(row: dict) -> Task:
    facts = dict(row["facts"])
    facts["soft"] = frozenset(facts.get("soft", ()))
    facts["lines"] = tuple(facts.get("lines", ()))
    facts["brand_not"] = tuple(facts.get("brand_not", ()))
    label = row["label"]
    return Task(
        id=row["id"], request=row["request"], category=tuple(row["category"]),
        max_cents=row["max_cents"], quantity_cap=row["quantity_cap"],
        persona=row["persona"], facts=IntentFacts(**facts), trap=row["trap"],
        should_ask=bool(label.get("should_ask")),
        ok_check=None if label.get("no_purchase")
        else (lambda purchase, _l=label: purchase_matches(_l, purchase, _find)),
    )


def rows(split: str | None = None, path: Path | None = None) -> list[dict]:
    """Задачи как записаны в файл. Скрытой половины может не быть — тогда её нет и тут."""
    name = f"tasks_{DATASET_VERSION}.jsonl"
    paths = [path] if path else [dir_of(s) / name for s in ("open", "hidden")
                                 if split in (None, s)]
    out = []
    for p in paths:
        if p.exists():
            out += [json.loads(line) for line in p.open(encoding="utf-8")]
    return [r for r in out if split in (None, r["split"])]


def load(split: str | None = None, path: Path | None = None) -> list[Task]:
    return [to_task(r) for r in rows(split, path)]
