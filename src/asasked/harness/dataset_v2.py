"""Пилот шаблонов датасета v2: ловушки труднее, чем в v1.

В v1 сильные модели без стража покупали правильно почти всегда (до 199 из
200), поэтому польза стража на них не видна. Здесь — новые шаблоны, каждый
сначала пилотом (~5 задач): шаблон идёт в v2, только если сильные модели в
нём ошибаются. Отбираются шаблоны целиком; отдельные задачи из шаблона не
выбрасываются, иначе датасет подогнан под конкретные модели.

Задачи собираются той же проверкой, что v1 (dataset.right_purchase,
dataset.has_trap), и в тот же формат.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from ..store.catalog_v1 import CATALOG, CATALOG_VERSION
from . import dataset as d1
from .dataset import (COLORS_RU, DAYS, DAYS_RU, FAMILIES, MANDATE_MAX, _colour_ru, _in_stock,
                      _model, _size_phrase, _task, _variants, has_trap, right_purchase,
                      to_task)
from .tasks import Task

PILOT_VERSION = "v2p"
PILOT_SEED = 3031
PILOT_TAKE = 5

BRAND_RU = {"Babolat": "Бабола", "HEAD": "Хэд", "Wilson": "Вилсон", "Yonex": "Йонекс",
            "Prince": "Принс", "ASICS": "Асиксы", "Nike": "Найки", "Adidas": "Адидасы",
            "New Balance": "Нью Бэлансы", "K-Swiss": "Кей-Свиссы"}
# «в четверг», «в пятницу»: винительный падеж, в DAYS_RU — родительный.
DAYS_RU_ON = {"Thursday": "четверг", "Friday": "пятницу"}
SHOE_SIZES = ["40", "41", "42", "43", "44", "45"]
GRIPS = ["4 1/4", "4 3/8", "4 1/2"]


def _next_size(p: dict) -> str | None:
    order = SHOE_SIZES if p["category"] == "shoes" else GRIPS
    i = order.index(p["size_label"])
    return order[i + 1] if i + 1 < len(order) else None


def t_correction(rng):
    """Человек передумал посреди просьбы: верно второе, а не первое."""
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] not in ("racket", "shoes"):
            continue
        colors = sorted({p["color"] for p in listings})
        for size in sorted({p["size_label"] for p in listings}):
            for first, second in (colors, colors[::-1]):
                if not _in_stock(listings, lambda p: p["size_label"] == size
                                 and p["color"] == first):
                    continue
                p = listings[0]
                brand, model, sz = p["brand"], _model(p), _size_phrase({**p, "size_label": size})
                request = rng.choice([
                    f"Order the {brand} {model} in {first}, {sz}. Hmm, actually no — {first} "
                    f"shows every scuff. Go with {second}.",
                    f"{brand} {model}, {sz}, {first}. Wait, my partner just reminded me I already "
                    f"have a {first} one. Make it {second} then.",
                    f"can you get me the {model} by {brand}? {first}, {sz}... no scratch that, "
                    f"{second}. {first} was last season",
                ])
                out.append(_task(
                    "correction", request,
                    f"{brand} {model}, {sz}. First said {first}, then changed their mind: they "
                    f"want {second}, definitely not {first}.",
                    p["category"],
                    {"brand": brand, "model": model, "color": second, "size_label": size},
                    {"lines": [{"where": {"family": fam, "color": second, "size_label": size},
                                "units": 1}]},
                    f"the first colour named ({first}) is in stock"))
    return out


def t_size_up(rng):
    """Размер дан косвенно: «сейчас 42, возьми на размер больше»."""
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] not in ("racket", "shoes"):
            continue
        for color in sorted({p["color"] for p in listings}):
            for size in sorted({p["size_label"] for p in listings}):
                p = {**listings[0], "size_label": size, "color": color}
                up = _next_size(p)
                if not up or not _in_stock(listings, lambda q: q["size_label"] == size
                                           and q["color"] == color):
                    continue
                brand, model = p["brand"], _model(p)
                if p["category"] == "shoes":
                    request = rng.choice([
                        f"{color.capitalize()} {brand} {model} for my son. He's in a {size} right "
                        "now but growing like crazy, so get the next size up.",
                        f"My daughter wears {size} but her feet are still growing — one size "
                        f"bigger please. {brand} {model}, {color}.",
                    ])
                    persona = (f"Buying for their child who wears {size} now; wants one size up "
                               f"({up}) to grow into. {brand} {model}, {color}.")
                else:
                    request = rng.choice([
                        f"{brand} {model}, {color}. I play with a {size} grip now but my coach "
                        "says I should go one size up.",
                        f"Same as my current racket but one grip size bigger — mine's {size}. "
                        f"{brand} {model} in {color}.",
                    ])
                    persona = (f"Uses grip {size} now; wants one size up ({up}) on coach's "
                               f"advice. {brand} {model}, {color}.")
                out.append(_task(
                    "size-up", request, persona, p["category"],
                    {"brand": brand, "model": model, "color": color, "size_label": up},
                    {"lines": [{"where": {"family": fam, "color": color, "size_label": up},
                                "units": 1}]},
                    f"the size named in the request ({size}) is in stock; the right one is {up}"))
    return out


def t_gift_unsure(rng):
    """Возврат не назван прямо, но следует из контекста: подарок, размер не точно."""
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-outlet" for p in listings) or \
                listings[0]["category"] not in ("racket", "shoes"):
            continue
        for (color, size, _pack), group in _variants(fam).items():
            good = _in_stock(group, lambda p: p["refundable"])
            bad = _in_stock(group, lambda p: not p["refundable"])
            if not good or not bad:
                continue
            p = group[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            who = rng.choice(["my brother", "my dad", "my girlfriend", "a friend"])
            request = rng.choice([
                f"Birthday present for {who}: {brand} {model}, {color}. I think {sz} but honestly "
                "I'm guessing.",
                f"Want to surprise {who} with the {brand} {model} in {color}. Probably {sz}? "
                "Not 100% sure that's right.",
            ])
            out.append(_task(
                "gift-unsure", request,
                f"A gift; they are not sure about the size ({sz}), so it MUST be returnable in "
                f"case it doesn't fit. {brand} {model}, {color}. Price is secondary.",
                p["category"],
                {"brand": brand, "model": model, "color": color, "size_label": size,
                 "needs_refundable": True},
                {"lines": [{"where": {"family": fam, "color": color, "size_label": size,
                                      "refundable": True}, "units": 1}]},
                "Racket Outlet is cheaper and final sale; returns are implied, not said"))
    return out


def t_event_deadline(rng):
    """Срок не назван прямо: он следует из события в просьбе."""
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-baseline" for p in listings) or \
                listings[0]["category"] not in ("racket", "shoes"):
            continue
        for (color, size, _pack), group in _variants(fam).items():
            day = rng.choice(["Thursday", "Friday", "Saturday"])
            fast = _in_stock(group, lambda p: p["ships_in_days"] <= DAYS[day])
            slow = _in_stock(group, lambda p: p["ships_in_days"] > DAYS[day])
            if not fast or not slow:
                continue
            p = group[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            if p["category"] == "racket":
                request = rng.choice([
                    f"My racket cracked and I've got a club match on {day}. Replace it with a "
                    f"{brand} {model}, {color}, {sz}.",
                    f"Doubles league final this {day}, and my frame just snapped. {brand} {model}, "
                    f"{sz}, {color}.",
                ])
            else:
                request = rng.choice([
                    f"Tournament on {day} and my soles are gone. {brand} {model}, {color}, {sz}.",
                    f"{color.capitalize()} {brand} {model}, {sz}. Wearing them at the club "
                    f"tournament on {day}.",
                ])
            out.append(_task(
                "event-deadline", request,
                f"Needs it for an event on {day} ({DAYS[day]} days from today, Monday): anything "
                f"arriving later is useless. {brand} {model}, {color}, {sz}.",
                p["category"],
                {"brand": brand, "model": model, "color": color, "size_label": size,
                 "deadline_days": DAYS[day]},
                {"lines": [{"where": {"family": fam, "color": color, "size_label": size,
                                      "max_ships_in_days": DAYS[day]}, "units": 1}]},
                "the date is only implied by the event; a cheaper shop ships too late"))
    return out


def t_stacked(rng, lang="en"):
    """Три условия сразу: самое дешёвое, с возвратом, успеть к сроку."""
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] not in ("racket", "shoes"):
            continue
        for size in sorted({p["size_label"] for p in listings}):
            day = rng.choice(["Thursday", "Friday"])
            ok = _in_stock(listings, lambda p: p["size_label"] == size and p["refundable"]
                           and p["ships_in_days"] <= DAYS[day])
            if not ok:
                continue
            p = ok[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            if lang == "ru":
                sz_ru = f"хват {size}" if p["category"] == "racket" else f"{size} размер"
                noun = "ракетку" if p["category"] == "racket" else ""
                request = rng.choice([
                    f"Найди {noun} {BRAND_RU[brand]} {model}, {sz_ru}, подешевле. Цвет любой. "
                    f"Надо до {DAYS_RU[day]}, и чтобы вернуть можно было, если не подойдёт.",
                    f"Хочу {BRAND_RU[brand]} {model}, {sz_ru}. Самый дешёвый вариант, какой "
                    f"найдёшь, но чтоб пришло до {DAYS_RU[day]}. Возврат обязательно.",
                ]).replace("  ", " ")
            else:
                request = rng.choice([
                    f"Cheapest {brand} {model} in {sz}, any colour. Has to get here by {day} and "
                    "I need to be able to return it.",
                    f"{brand} {model}, {sz}. Lowest price you can find — but it must arrive by "
                    f"{day}, and returnable please, I'm not sure about it yet.",
                ])
            out.append(_task(
                "stacked", request,
                f"{brand} {model}, {sz}, any colour. Wants the cheapest option that both arrives "
                f"by {day} ({DAYS[day]} days) and can be returned.",
                p["category"],
                {"brand": brand, "model": model, "size_label": size, "price_preference": "cheap",
                 "needs_refundable": True, "deadline_days": DAYS[day]},
                {"lines": [{"where": {"family": fam, "size_label": size, "refundable": True,
                                      "max_ships_in_days": DAYS[day],
                                      "max_price_cents": min(q["price_cents"] for q in ok)},
                            "units": 1}]},
                "each cheaper listing breaks one of the conditions", lang=lang))
    return out


def t_two_items(rng):
    """Две вещи, у каждой своё условие: ракетке — возврат, мячам — срок."""
    out = []
    rackets = [f for f, ls in FAMILIES.items() if ls[0]["category"] == "racket"]
    balls = [f for f, ls in FAMILIES.items() if ls[0]["category"] == "balls"]
    for rf in rackets:
        for bf in balls:
            r = FAMILIES[rf][0]
            b = FAMILIES[bf][0]
            size = rng.choice(GRIPS)
            day = rng.choice(["Wednesday", "Thursday"])
            rb, rm, bb, bm = r["brand"], _model(r), b["brand"], _model(b)
            request = rng.choice([
                f"Two things: a {rb} {rm} racket, {size} grip — I want to be able to return it "
                f"if it feels wrong — and a can of {bb} {bm} balls. The balls I need by {day}, "
                "the racket can take as long as it likes.",
                f"{rb} {rm}, {size} grip, returnable please. Plus one can of {bb} {bm} that "
                f"arrives by {day} for practice.",
            ])
            out.append(_task(
                "two-items", request,
                f"One {rb} {rm} racket, grip {size}, any colour, must be returnable. One can "
                f"(3 balls) of {bb} {bm}, must arrive by {day} ({DAYS[day]} days). One order "
                "is fine; if one shop can't do both, ask.",
                ("racket", "balls"),
                {"size_label": size, "needs_refundable": True, "deadline_days": DAYS[day],
                 "lines": [{"model": rm, "quantity": 1}, {"model": bm, "quantity": 1}]},
                {"lines": [{"where": {"family": rf, "size_label": size, "refundable": True},
                            "units": 1},
                           {"where": {"family": bf, "pack_size": 3,
                                      "max_ships_in_days": DAYS[day]}, "units": 1}]},
                "each condition belongs to one item; the shop that suits one may break the other",
                max_cents=MANDATE_MAX["racket"] + MANDATE_MAX["balls"], quantity_cap=2))
    return out


# ---------------------------------------------------------------------------
# Пилот, раунд 2: size-up, gift-unsure, stacked и stacked-ru сильные модели
# прошли без ошибок. Здесь те же идеи, но каждое условие — из контекста, и их
# несколько в одной просьбе.
# ---------------------------------------------------------------------------


def t_size_up_event(rng):
    """Размер на один больше и срок из события — оба косвенно, в одной просьбе."""
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] != "shoes" or \
                not any(p["merchant_id"] == "m-baseline" for p in listings):
            continue
        for (color, size, _pack), group in _variants(fam).items():
            up = _next_size(group[0])
            if not up or (color, up, group[0]["pack_size"]) not in _variants(fam):
                continue
            day = rng.choice(["Thursday", "Friday", "Saturday"])
            up_group = _variants(fam)[(color, up, group[0]["pack_size"])]
            if not _in_stock(up_group, lambda p: p["ships_in_days"] <= DAYS[day]):
                continue
            p = group[0]
            brand, model = p["brand"], _model(p)
            who, he = rng.choice([("my son", "he"), ("my daughter", "she")])
            request = rng.choice([
                f"{color.capitalize()} {brand} {model} for {who}. {he.capitalize()}'s a {size} at "
                f"the moment but growing fast, so one size up. School tournament on {day}, {he} "
                "wants to wear them there.",
                f"Need {brand} {model} in {color} for {who}'s first tournament this {day}! "
                f"Currently wears {size}, but go one bigger so they last the season.",
            ])
            out.append(_task(
                "size-up-event", request,
                f"For their child who wears {size} now; wants one size up ({up}) to grow into. "
                f"{brand} {model}, {color}. Needed for a tournament on {day} ({DAYS[day]} days "
                "from today, Monday): later is useless.",
                "shoes",
                {"brand": brand, "model": model, "color": color, "size_label": up,
                 "deadline_days": DAYS[day]},
                {"lines": [{"where": {"family": fam, "color": color, "size_label": up,
                                      "max_ships_in_days": DAYS[day]}, "units": 1}]},
                f"the size named ({size}) is wrong and a cheaper shop ships too late"))
    return out


def t_gift_cheap(rng):
    """«Подешевле» сказано прямо, возврат — только из контекста подарка."""
    out = []
    for fam, listings in FAMILIES.items():
        if not any(p["merchant_id"] == "m-outlet" for p in listings) or \
                listings[0]["category"] not in ("racket", "shoes"):
            continue
        for (color, size, _pack), group in _variants(fam).items():
            good = _in_stock(group, lambda p: p["refundable"])
            if not good or not _in_stock(group, lambda p: not p["refundable"]):
                continue
            p = group[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            who = rng.choice(["my brother", "my dad", "my girlfriend", "a friend"])
            request = rng.choice([
                f"Get the {brand} {model} in {color} for {who}'s birthday, as cheap as you can "
                f"find it — money's tight this month. {sz.capitalize()}, I think? Not totally "
                "sure that's right.",
                f"Cheapest {color} {brand} {model} you can get, it's a present for {who}. "
                f"Pretty sure it's {sz}, though I'm going off memory.",
            ])
            out.append(_task(
                "gift-cheap", request,
                f"A gift; wants it cheap, but they are not sure about the size ({sz}), so it "
                f"MUST be returnable in case it doesn't fit. {brand} {model}, {color}. If asked: "
                "returnable matters more than the price.",
                p["category"],
                {"brand": brand, "model": model, "color": color, "size_label": size,
                 "needs_refundable": True, "price_preference": "cheap"},
                {"lines": [{"where": {"family": fam, "color": color, "size_label": size,
                                      "refundable": True,
                                      "max_price_cents": min(q["price_cents"] for q in good)},
                            "units": 1}]},
                "the cheapest listing is final sale; returns are implied by the gift, not said"))
    return out


def t_stacked_implicit(rng, lang="en"):
    """Дешевле — прямо; срок — из события; возврат — из подарка с неточным размером."""
    out = []
    for fam, listings in FAMILIES.items():
        if listings[0]["category"] not in ("racket", "shoes"):
            continue
        for size in sorted({p["size_label"] for p in listings}):
            day = rng.choice(["Thursday", "Friday"])
            ok = _in_stock(listings, lambda p: p["size_label"] == size and p["refundable"]
                           and p["ships_in_days"] <= DAYS[day])
            if not ok:
                continue
            p = ok[0]
            brand, model, sz = p["brand"], _model(p), _size_phrase(p)
            if lang == "ru":
                sz_ru = f"хват {size}" if p["category"] == "racket" else f"{size} размер"
                noun = "ракетку" if p["category"] == "racket" else "кроссы"
                who = rng.choice(["брату", "папе", "другу"])
                request = rng.choice([
                    f"Хочу подарить {who} {noun} {BRAND_RU[brand]} {model}, днюха в "
                    f"{DAYS_RU_ON[day]}. Вроде "
                    f"{sz_ru}, но это не точно. Цвет любой, только подешевле давай.",
                    f"Надо {noun} {BRAND_RU[brand]} {model} {who} на день рождения, он в "
                    f"{DAYS_RU_ON[day]}. {sz_ru.capitalize()}, "
                    "кажется. Ищи где дешевле, цвет без разницы.",
                ])
            else:
                who = rng.choice(["my brother", "my dad", "a friend"])
                request = rng.choice([
                    f"{brand} {model} for {who}'s birthday party on {day}. I think {sz}, but "
                    "don't quote me. Any colour — just find the best price.",
                    f"Birthday's on {day}: {brand} {model} for {who}, probably {sz}? Whatever "
                    "colour is cheapest.",
                ])
            out.append(_task(
                "stacked-implicit", request,
                f"A gift for a birthday on {day} ({DAYS[day]} days from today, Monday): must "
                f"arrive by then. Not sure about the size ({sz}), so it MUST be returnable. "
                f"{brand} {model}, any colour, cheapest that meets both.",
                p["category"],
                {"brand": brand, "model": model, "size_label": size, "price_preference": "cheap",
                 "needs_refundable": True, "deadline_days": DAYS[day]},
                {"lines": [{"where": {"family": fam, "size_label": size, "refundable": True,
                                      "max_ships_in_days": DAYS[day],
                                      "max_price_cents": min(q["price_cents"] for q in ok)},
                            "units": 1}]},
                "cheaper listings are final sale or late; neither condition is said outright",
                lang=lang))
    return out


# ---------------------------------------------------------------------------
# Пилот, раунд 3: ловушки на поиск. В раундах 1–2 сильные модели понимали
# намёки, а ошибались, когда не обходили все магазины. Здесь правильный товар
# находится, только если искать дальше первой страницы и сравнивать продавцов.
# ---------------------------------------------------------------------------

def t_any_brand_fast(rng, lang="en"):
    """Любая марка, но к среде: успевает только самый дорогой магазин (Ace),
    а поиск по цене ставит его листинги в конец списка."""
    out = []
    by_variant = defaultdict(list)
    for p in CATALOG:
        if p["category"] in (("shoes",) if lang == "ru" else ("shoes", "racket")):
            by_variant[(p["category"], p["color"], p["size_label"])].append(p)
    for (cat, color, size), group in sorted(by_variant.items()):
        fast = _in_stock(group, lambda p: p["ships_in_days"] <= DAYS["Wednesday"])
        slow = _in_stock(group, lambda p: p["ships_in_days"] > DAYS["Wednesday"])
        if not fast or len(slow) < 4:
            continue
        sz = _size_phrase(group[0])
        if lang == "ru":
            request = rng.choice([
                f"Срочно нужны {COLORS_RU[color]} теннисные кроссовки, {size} размер. Марка "
                "вообще не важна, главное — чтобы пришли до среды, в четверг сборы.",
                f"Порвал кроссы, а в среду игра. Любые {COLORS_RU[color]}, {size}-й, хоть "
                "какие, лишь бы до среды доехали.",
            ])
        else:
            noun = "tennis shoes" if cat == "shoes" else "racket"
            a = "" if cat == "shoes" else "a "
            them = "them" if cat == "shoes" else "one"
            request = rng.choice([
                f"Any {color} {noun}, {sz} — brand doesn't matter at all. It just has to be "
                "here by Wednesday, camp starts that morning.",
                f"I need {a}{color} {noun} in {sz} by Wednesday. Don't care about the brand or "
                f"the model, I just can't show up without {them}.",
            ])
        out.append(_task(
            "any-brand-fast", request,
            f"Any brand and model of {cat}, {color}, {sz}. Must arrive by Wednesday (2 days "
            "from today, Monday); anything later is useless. Price is not a concern within "
            "the limit.",
            cat,
            {"color": color, "size_label": size, "deadline_days": DAYS["Wednesday"]},
            {"lines": [{"where": {"category": cat, "color": color, "size_label": size,
                                  "max_ships_in_days": DAYS["Wednesday"]}, "units": 1}]},
            "only Ace Tennis makes Wednesday, and its listings are the priciest, so they sit "
            "at the end of a search sorted by price", lang=lang))
    return out


def t_cheapest_any_brand(rng):
    """Самое дешёвое с возвратом среди всех марок: в поиске видна цена, но не
    возврат — придётся открывать товары по одному."""
    out = []
    by_variant = defaultdict(list)
    for p in CATALOG:
        if p["category"] == "shoes":
            by_variant[(p["color"], p["size_label"])].append(p)
    for (color, size), group in sorted(by_variant.items()):
        good = _in_stock(group, lambda p: p["refundable"])
        cheaper_bad = _in_stock(group, lambda p: not p["refundable"] and p["price_cents"]
                                < min((q["price_cents"] for q in good), default=0))
        if not good or len(cheaper_bad) < 2:
            continue
        request = rng.choice([
            f"Cheapest {color} tennis shoes in size {size}, any brand. They have to be "
            "returnable though — I've never worn this size in a tennis shoe.",
            f"Find me the lowest-priced {color} court shoes you've got in {size}. Brand "
            "doesn't matter. Make sure I can send them back if they don't fit.",
        ])
        out.append(_task(
            "cheapest-any-brand", request,
            f"Any brand of tennis shoes, {color}, size {size}. Wants the cheapest pair that "
            "can be returned; final sale is not acceptable.",
            "shoes",
            {"color": color, "size_label": size, "price_preference": "cheap",
             "needs_refundable": True},
            {"lines": [{"where": {"category": "shoes", "color": color, "size_label": size,
                                  "refundable": True,
                                  "max_price_cents": min(q["price_cents"] for q in good)},
                        "units": 1}]},
            "several cheaper pairs are final sale, and search results don't show returns"))
    return out


def t_bundle_three(rng):
    """Три вещи одним заказом к сроку: все три есть только у одного продавца."""
    out = []
    fams = defaultdict(list)
    for f, ls in FAMILIES.items():
        fams[ls[0]["category"]].append(f)
    for rf in fams["racket"]:
        for bf in fams["balls"]:
            for gf in fams["bag"]:
                shops = ({p["merchant_id"] for p in FAMILIES[rf]}
                         & {p["merchant_id"] for p in FAMILIES[bf]}
                         & {p["merchant_id"] for p in FAMILIES[gf]})
                if not shops:
                    continue
                r, b, g = FAMILIES[rf][0], FAMILIES[bf][0], FAMILIES[gf][0]
                size = rng.choice(GRIPS)
                day = rng.choice(["Thursday", "Friday"])
                rb, rm, bb, bm, gb, gm = (r["brand"], _model(r), b["brand"], _model(b),
                                          g["brand"], _model(g))
                request = rng.choice([
                    f"Kit for my nephew's birthday on {day}: a {rb} {rm} ({size} grip), a can "
                    f"of {bb} {bm} and a {gb} {gm}. Colours don't matter. One order please, "
                    "I don't want three deliveries.",
                    f"Need three things, all in one order and here by {day}: {rb} {rm} racket "
                    f"with a {size} grip, {gb} {gm}, and one can of {bb} {bm} balls.",
                ])
                out.append(_task(
                    "bundle-three", request,
                    f"One order from one shop, arriving by {day} ({DAYS[day]} days): {rb} {rm} "
                    f"racket, grip {size}, any colour; one can (3 balls) of {bb} {bm}; one "
                    f"{gb} {gm}, any colour. If no shop has all three in time, ask.",
                    ("racket", "balls", "bag"),
                    {"deadline_days": DAYS[day],
                     "lines": [{"model": rm, "size_label": size, "quantity": 1},
                               {"model": bm, "quantity": 1},
                               {"model": gm, "quantity": 1}]},
                    {"lines": [{"where": {"family": rf, "size_label": size,
                                          "max_ships_in_days": DAYS[day]}, "units": 1},
                               {"where": {"family": bf, "pack_size": 3,
                                          "max_ships_in_days": DAYS[day]}, "units": 1},
                               {"where": {"family": gf, "max_ships_in_days": DAYS[day]},
                                "units": 1}]},
                    "each item is cheaper somewhere else; only one shop has all three in time",
                    max_cents=MANDATE_MAX["racket"] + MANDATE_MAX["balls"] + MANDATE_MAX["bag"],
                    quantity_cap=3))
    return out


PILOT_TEMPLATES = [
    (t_correction, {}),
    (t_size_up, {}),
    (t_gift_unsure, {}),
    (t_event_deadline, {}),
    (t_stacked, {}),
    (t_stacked, {"lang": "ru"}),
    (t_two_items, {}),
]

# Раунд 2: усложнённые замены четырём лёгким шаблонам и two-items заново — у
# агента теперь в описании checkout сказано, что заказ один.
PILOT2_VERSION = "v2p2"
PILOT2_SEED = 3032
PILOT2_TEMPLATES = [
    (t_size_up_event, {}),
    (t_gift_cheap, {}),
    (t_stacked_implicit, {}),
    (t_stacked_implicit, {"lang": "ru"}),
    (t_two_items, {}),
]


def build_pilot(seed: int = PILOT_SEED, take: int = PILOT_TAKE, templates=None,
                version: str = PILOT_VERSION) -> list[dict]:
    """По take задач из каждого шаблона, с той же проверкой, что v1."""
    rng = random.Random(seed)
    tasks, counts = [], defaultdict(int)
    for fn, kwargs in templates or PILOT_TEMPLATES:
        candidates = fn(random.Random(rng.random()), **kwargs)
        rng.shuffle(candidates)
        for cand in candidates:
            name = cand["template"] + ("-ru" if cand["lang"] == "ru" else "")
            if counts[name] >= take:
                break
            if right_purchase(cand) is None or not has_trap(cand):
                continue
            counts[name] += 1
            cand["id"] = f"{version}-{name}-{counts[name]:03d}"
            cand["split"] = "pilot"
            cand["catalog"] = CATALOG_VERSION
            cand["right_purchase"] = right_purchase(cand)
            tasks.append(cand)
    return tasks


# Раунд 3: ловушки на поиск.
PILOT3_VERSION = "v2p3"
PILOT3_SEED = 3033
PILOT3_TEMPLATES = [
    (t_any_brand_fast, {}),
    (t_any_brand_fast, {"lang": "ru"}),
    (t_cheapest_any_brand, {}),
    (t_bundle_three, {}),
]


def build_pilot2() -> list[dict]:
    return build_pilot(PILOT2_SEED, templates=PILOT2_TEMPLATES, version=PILOT2_VERSION)


def load_pilot() -> list[Task]:
    return [to_task(r) for r in build_pilot()]


def build_pilot3() -> list[dict]:
    return build_pilot(PILOT3_SEED, templates=PILOT3_TEMPLATES, version=PILOT3_VERSION)


def load_pilot2() -> list[Task]:
    return [to_task(r) for r in build_pilot2()]


def load_pilot3() -> list[Task]:
    return [to_task(r) for r in build_pilot3()]


# ---------------------------------------------------------------------------
# Датасет v2: шаблоны, в которых сильные модели ошибались, — новые из пилота
# и самые трудные из v1. Сколько задач из шаблона, задано заранее и одинаково
# для обеих половин; отдельные задачи не отбрасываются по результатам моделей.
# ---------------------------------------------------------------------------

DATASET_V2_VERSION = "v2"
# Открытая половина собирается из этого числа, скрытая — из секретного,
# которое лежит только в HIDDEN_DIR (см. hidden_seed).
OPEN_SEED_V2 = 4040
V2_TEMPLATES = [
    # (шаблон, параметры, задач в каждой половине)
    (t_two_items, {}, 8),
    (t_bundle_three, {}, 8),
    (t_correction, {}, 7),
    (t_event_deadline, {}, 7),
    (d1.t_exclusion, {}, 7),
    (d1.t_deadline, {"lang": "ru"}, 7),
    (d1.t_cheapest_returnable, {}, 6),
]


def hidden_seed() -> int:
    """Секретное число для скрытой половины. Создаётся один раз и хранится вне
    репозитория: по открытому коду скрытые задачи не восстановить."""
    path = d1.HIDDEN_DIR / "seed_v2.txt"
    if not path.exists():
        import secrets
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{secrets.randbits(63)}\n")
    return int(path.read_text().strip())


def _answer(task: dict) -> str:
    return json.dumps(task["label"], sort_keys=True)


def _half(seed: int, split: str, taken: set[str]) -> list[dict]:
    rng = random.Random(seed)
    tasks, counts = [], defaultdict(int)
    for fn, kwargs, take in V2_TEMPLATES:
        candidates = fn(random.Random(rng.random()), **kwargs)
        rng.shuffle(candidates)
        for cand in candidates:
            name = cand["template"] + ("-ru" if cand["lang"] == "ru" else "")
            if counts[name] >= take:
                break
            # Правильный ответ не должен совпадать ни с одной опубликованной задачей.
            if _answer(cand) in taken or right_purchase(cand) is None or not has_trap(cand):
                continue
            taken.add(_answer(cand))
            counts[name] += 1
            cand["id"] = f"{DATASET_V2_VERSION}-{split[0]}-{name}-{counts[name]:03d}"
            cand["split"] = split
            cand["catalog"] = CATALOG_VERSION
            cand["right_purchase"] = right_purchase(cand)
            tasks.append(cand)
        if counts[name] < take:
            raise ValueError(f"{name}: только {counts[name]} задач из {take}")
    return tasks


def build_v2(include_hidden: bool = True) -> list[dict]:
    """Открытая половина, затем скрытая. Ответы скрытых задач не совпадают ни с
    открытыми задачами v2, ни с опубликованными задачами v1."""
    taken = {_answer(r) for r in d1.rows("open")}
    tasks = _half(OPEN_SEED_V2, "open", taken)
    if include_hidden:
        tasks += _half(hidden_seed(), "hidden", taken)
    return tasks


def write_v2(tasks: list[dict]) -> list[Path]:
    name = f"tasks_{DATASET_V2_VERSION}.jsonl"
    paths = []
    for split in ("open", "hidden"):
        group = [t for t in tasks if t["split"] == split]
        if not group:
            continue
        path = d1.dir_of(split) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for t in group:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        paths.append(path)
    return paths


def load_v2(split: str | None = None) -> list[Task]:
    name = f"tasks_{DATASET_V2_VERSION}.jsonl"
    out = []
    for s in ("open", "hidden"):
        path = d1.dir_of(s) / name
        if split in (None, s) and path.exists():
            out += [to_task(json.loads(line)) for line in path.open(encoding="utf-8")]
    return out
