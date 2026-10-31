"""Сверка намерения с корзиной.

Устройство сознательно разделено на две половины:

  1) ИЗВЛЕЧЕНИЕ — превратить слова человека в набор фактов.
     Здесь работает настоящая языковая модель (llm_extract.py).
     Это единственное место, где нужен ИИ.

  2) СВЕРКА — сравнить факты с корзиной и выдать заключение.
     Это обычный детерминированный код. Он воспроизводим, объясним
     и пригоден для приложения к спору: не «так решил ИИ», а
     «человек просил возврат, товар невозвратный».

Разделение важно не для красоты: заключение, которое нельзя перепроверить,
в споре не стоит ничего.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from itertools import permutations

from . import catalog
from .llm_extract import AGREE_PROVIDERS, SOFTENABLE_FIELDS, WEEKDAYS, ExtractionError, call_model

BLOCK = "block"
WARN = "warn"


_SOFTENABLE_FIELDS = frozenset(SOFTENABLE_FIELDS)


@dataclass
class IntentFacts:
    brand: str | None = None
    brand_not: tuple = ()                    # исключённые бренды: «любой, кроме Wilson»
    model: str | None = None                 # модель, как её назвал человек: "EZONE 98"
    color: str | None = None
    size_label: str | None = None
    level: str | None = None
    price_preference: str | None = None      # cheap | premium
    explicit_max_cents: int | None = None
    quantity: int | None = None
    needs_refundable: bool = False
    deadline_days: int | None = None
    raw: str = ""
    # Имена полей выше, которые человек сам обозначил как необязательные
    # или примерные ("не принципиально", "плюс-минус"). Расхождение по
    # такому полю — предупреждение (WARN), а не блокировка (BLOCK).
    soft: frozenset = field(default_factory=frozenset)
    # Поля, в которых независимые модели извлечения разошлись
    # (extract_intent_agreed). Факт спорный — расхождение по нему тоже WARN:
    # блокировать покупку на основании факта, в котором не уверены сами
    # модели, нельзя, но и молча его терять тоже.
    disputed: frozenset = field(default_factory=frozenset)
    # Несколько разных вещей или вариантов в одном заказе: «размер 40 для жены
    # и 43 для меня», «ракетка HEAD и банка мячей Wilson». Каждая строка —
    # словарь с полями из LINE_FIELDS, которые у этой позиции свои; остальное
    # общее и берётся с верхнего уровня.
    lines: tuple = ()
    # Остальные требования человека — те, которым нет поля выше («без
    # глютена», «подарочная упаковка»), его же словами. Сверить их с корзиной
    # код не может, поэтому не молчит, а спрашивает: other — обязательные
    # (BLOCK), other_optional — «по возможности» (WARN). Решать за человека,
    # подходит ли товар, модели не поручается.
    other: tuple = ()
    other_optional: tuple = ()


LINE_FIELDS = ("brand", "model", "color", "size_label", "quantity", "needs_refundable",
               "deadline_days")


@dataclass
class Finding:
    code: str
    severity: str
    text: str


@dataclass
class Verdict:
    coherent: bool
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == BLOCK]


# ---------------------------------------------------------------------------
# 1. Извлечение — настоящая языковая модель (llm_extract.py)
# ---------------------------------------------------------------------------


def _as_int(value, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ExtractionError(f"Поле {field_name}: ожидалось число, получен bool {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    raise ExtractionError(f"Поле {field_name}: ожидалось целое число, получено {value!r}")


def _as_str(value, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ExtractionError(f"Поле {field_name}: ожидалась строка, получено {value!r}")


def _as_str_tuple(value, field_name: str) -> tuple:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ExtractionError(f"Поле {field_name}: ожидался список строк, получено {value!r}")
    return tuple(value)


def _as_lines(value, today: str | None = None) -> tuple:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ExtractionError(f"Поле lines: ожидался список, получено {value!r}")
    lines = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ExtractionError(f"Поле lines: ожидался объект, получено {raw!r}")
        unknown = set(raw) - set(LINE_FIELDS) - {"deadline_weekday"}
        if unknown:
            raise ExtractionError(f"Поле lines: неизвестные поля {sorted(unknown)!r}")
        line = {k: _as_str(raw.get(k), f"lines.{k}") for k in ("brand", "model", "color",
                                                                "size_label")}
        line["quantity"] = _as_int(raw.get("quantity"), "lines.quantity")
        # Только «да»: «нет» у строки — это «не просили», а не запрет возврата.
        line["needs_refundable"] = True if raw.get("needs_refundable") else None
        # Срок строки — как и общий: названный день считает код, а не модель.
        line["deadline_days"] = _as_int(raw.get("deadline_days"), "lines.deadline_days")
        counted = days_until(_as_str(raw.get("deadline_weekday"), "lines.deadline_weekday"), today)
        if counted is not None:
            line["deadline_days"] = counted
        lines.append({k: v for k, v in line.items() if v is not None})
    # одна строка — это не «несколько вариантов», а просто факты
    return tuple(lines) if len(lines) > 1 else ()


def _as_soft_set(value) -> frozenset:
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise ExtractionError(f"Поле soft_fields: ожидался список, получено {value!r}")
    # Мягкость прочих условий задаётся в них самих (optional); модель иногда
    # дублирует её сюда — это не ошибка извлечения.
    value = [v for v in value if v != "other_conditions"]
    unknown = [v for v in value if v not in _SOFTENABLE_FIELDS]
    if unknown:
        raise ExtractionError(f"Поле soft_fields: неизвестные имена полей {unknown!r}")
    return frozenset(value)


def _as_conditions(value) -> tuple[tuple, tuple]:
    """other_conditions модели → (обязательные, по возможности), без повторов."""
    if value is None:
        return (), ()
    if not isinstance(value, list):
        raise ExtractionError(f"Поле other_conditions: ожидался список, получено {value!r}")
    required, optional = [], []
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
            raise ExtractionError(f"Поле other_conditions: ожидался объект с text, "
                                  f"получено {raw!r}")
        text = " ".join(raw["text"].split())
        target = optional if raw.get("optional") else required
        if text and text.lower() not in {t.lower() for t in required + optional}:
            target.append(text)
    return tuple(required), tuple(optional)


def days_until(weekday: str | None, today: str | None) -> int | None:
    """Сколько дней от сегодня до названного дня недели, включая его.

    today — дата словами, начинается с дня недели («Monday, 2 November
    2026»). С понедельника «к пятнице» — 4 дня, «к понедельнику» — 7.
    Если день или сегодняшняя дата неизвестны — None.
    """
    if not weekday or not today:
        return None
    first = today.split(",")[0].strip().lower()
    if first not in WEEKDAYS or weekday.lower() not in WEEKDAYS:
        return None
    return (WEEKDAYS.index(weekday.lower()) - WEEKDAYS.index(first)) % 7 or 7


def extract_intent(request: str, deadline_days: int | None = None,
                   provider: str | None = None, today: str | None = None) -> IntentFacts:
    """Извлекает факты из просьбы человека настоящей языковой моделью.

    Сверка (ниже в этом файле) не знает и не должна знать, что было внутри
    этой функции — только то, что IntentFacts либо получен, либо не получен
    (тогда наружу летит ExtractionError, а не молчаливые null-поля).

    today — сегодняшняя дата словами: без неё «к субботе» модели переводят
    в дни наугад и расходятся между собой.
    """
    data = call_model(request, provider, today=today)

    level = _as_str(data.get("level"), "level")
    if level == "advanced":
        level = "pro"

    price_preference = _as_str(data.get("price_preference"), "price_preference")

    model_deadline = _as_int(data.get("deadline_days"), "deadline_days")
    # «К пятнице» модели переводят в дни по-разному (4 или 5), и строгий
    # из двух ответов останавливал правильные покупки. Названный день модель
    # только называет, а дни до него считает код.
    counted = days_until(_as_str(data.get("deadline_weekday"), "deadline_weekday"), today)
    if counted is not None:
        model_deadline = counted

    other, other_optional = _as_conditions(data.get("other_conditions"))
    return canonical(IntentFacts(
        raw=request,
        deadline_days=deadline_days if deadline_days is not None else model_deadline,
        brand=_as_str(data.get("brand"), "brand"),
        brand_not=_as_str_tuple(data.get("brand_not"), "brand_not"),
        model=_as_str(data.get("model"), "model"),
        color=_as_str(data.get("color"), "color"),
        size_label=_as_str(data.get("size_label"), "size_label"),
        level=level,
        price_preference=price_preference,
        explicit_max_cents=_as_int(data.get("explicit_max_cents"), "explicit_max_cents"),
        quantity=_as_int(data.get("quantity"), "quantity"),
        needs_refundable=bool(data.get("needs_refundable", False)),
        soft=_as_soft_set(data.get("soft_fields")),
        lines=_as_lines(data.get("lines"), today),
        other=other,
        other_optional=other_optional,
    ))


def canonical(facts: IntentFacts) -> IntentFacts:
    """Одна форма для одного смысла — чтобы ответы двух моделей сравнивались.

    Модели по-разному раскладывают одно и то же: общий цвет кладут то наверх,
    то в каждую строку, а рядом со строками иногда пишут общее количество.
    Здесь всё, что одинаково во всех строках, поднимается наверх, а общее
    количество при строках отбрасывается — оно уже в строках.
    """
    if not facts.lines:
        return facts
    top, lines = {}, [dict(line) for line in facts.lines]
    for name in ("brand", "model", "color", "size_label", "needs_refundable", "deadline_days"):
        values = {line.get(name) for line in lines}
        shared = values.pop() if len(values) == 1 else None
        # needs_refundable наверху — False, когда не просили: это «не задано»
        if shared is not None and getattr(facts, name) in (None, False, shared):
            top[name] = shared
            for line in lines:
                line.pop(name, None)
        elif getattr(facts, name) not in (None, False):
            for line in lines:
                if line.get(name) == getattr(facts, name):
                    line.pop(name)
    lines = [line for line in lines if line] or []
    return replace(facts, quantity=None, lines=tuple(lines) if len(lines) > 1 else (), **top)


_COMPARED_FIELDS = (
    "brand", "brand_not", "model", "color", "size_label", "level", "price_preference",
    "explicit_max_cents", "quantity", "needs_refundable", "deadline_days",
)


_STRICTEST_WINS = ("deadline_days", "explicit_max_cents")


def _norm(value):
    if isinstance(value, tuple):
        return tuple(sorted(v.lower() for v in value))
    return value.lower() if isinstance(value, str) else value


def merge_facts(results: list[IntentFacts]) -> IntentFacts:
    """Сводит факты от нескольких моделей в один набор.

    Где модели согласны — берётся общее значение. Срок и предел суммы, если их
    нашла хоть одна модель, — берётся строжайший из найденных, без пометки
    спора: модели такие факты почти не выдумывают, а пропускают часто
    (Claude то видит «by Friday», то нет). Где разошлись — поле
    попадает в disputed, а значение выбирается так, чтобы факт не потерялся:
    если одна модель вернула null, а другая что-то нашла, берётся найденное;
    если обе нашли разное — значение первой модели. needs_refundable при
    расхождении — True: человек, возможно, просил возврат.

    soft — объединение: если хоть одна модель услышала, что человек сам
    снял жёсткость с требования, требование не блокирует покупку.

    Прочие требования (other) — свободный текст, по словам его не сравнить:
    берутся у модели, которая услышала их больше всего. Если хоть одна
    модель не услышала ни одного — спор "other", требования предупреждают,
    а не останавливают, как и любой спорный факт.

    Строки заказа: разошлись в деталях строк — спор "lines" и "lines.<поле>"
    для каждого поля, в котором разошлись (одна модель не назвала количество —
    спорно количество, а не модель, которую обе услышали одинаково); разошлись
    в том, сколько вещей человек просил, — ещё и "line_count". Строки берутся
    у той модели, что услышала больше вещей: вещь модели почти не выдумывают,
    а сливают две в одну часто (Gemini то видит «ракетку и банку мячей», то
    нет). При одинаковом числе вещей строки сводятся по полям, как и факты.
    """
    if not results:
        raise ValueError("merge_facts: нет ни одного результата")
    first = results[0]
    values, disputed = {}, set()
    for name in _COMPARED_FIELDS:
        found = [getattr(r, name) for r in results]
        if len({_norm(v) for v in found}) == 1:
            values[name] = found[0]
            continue
        # Срок и предел суммы — не спор, а разная оценка одного и того же
        # («к субботе» = 4 или 5 дней) или пропуск одной из моделей. Для
        # стража надёжнее строгая: меньший срок, меньший предел; цена ошибки —
        # лишний вопрос человеку, а не покупка, которая не успеет.
        if name in _STRICTEST_WINS:
            values[name] = min(v for v in found if v is not None)
            continue
        # Исключённый бренд, замеченный хоть одной моделью, — исключён:
        # купить то, что человек прямо отверг, хуже лишнего вопроса.
        if name == "brand_not":
            values[name] = tuple(sorted({b for v in found for b in v}))
            continue
        disputed.add(name)
        if name == "needs_refundable":
            values[name] = any(found)
        else:
            values[name] = next((v for v in found if v is not None), None)
    lines = max((r.lines for r in results), key=len)
    if len({len(r.lines) for r in results}) > 1:
        disputed |= {"lines", "line_count"}
    elif lines:
        merged = []
        for group in zip(*(_align_lines(first.lines, r.lines) for r in results)):
            keys = sorted({k for line in group for k in line})
            for k in keys:
                if len({_norm(line.get(k)) for line in group}) > 1:
                    disputed |= {"lines", f"lines.{k}"}
            merged.append({k: next(line[k] for line in group if line.get(k) is not None)
                           for k in keys if any(line.get(k) is not None for line in group)})
        lines = tuple(merged)
    other = max((r.other for r in results), key=len)
    if other and not all(r.other for r in results):
        disputed.add("other")
    optional = []
    for r in results:
        optional += [t for t in r.other_optional
                     if t.lower() not in {o.lower() for o in other + tuple(optional)}]
    return IntentFacts(
        raw=first.raw,
        other=other,
        other_optional=tuple(optional),
        soft=frozenset().union(*(r.soft for r in results)),
        disputed=frozenset(disputed),
        lines=lines,
        **values,
    )


def _align_lines(base: tuple, other: tuple) -> tuple:
    """Строки другой модели в порядке строк base — по наибольшему совпадению
    полей (модели могут перечислить те же вещи в другом порядке)."""
    if math.factorial(len(other)) > MAX_ASSIGNMENTS:
        return other  # не сопоставить — расхождения станут спорными полями
    def agree(order) -> int:
        return sum(_norm(a.get(k)) == _norm(b.get(k)) for a, b in zip(base, order)
                   for k in a.keys() | b.keys())
    return max(permutations(other), key=agree)


def extract_intent_agreed(request: str, deadline_days: int | None = None,
                          providers=AGREE_PROVIDERS, today: str | None = None) -> IntentFacts:
    """Извлекает факты несколькими независимыми моделями и сводит их.

    Одна модель может уверенно ошибиться, и это не видно. Две модели,
    разошедшиеся в факте, — видно: поле попадает в disputed.
    """
    if not providers:
        raise ExtractionError("no model key: set CLAUDE_API_KEY, LLM_API_KEY (Gemini) "
                              "or OPENAI_COMPAT_API_KEY")
    return merge_facts([extract_intent(request, deadline_days, p, today) for p in providers])


# ---------------------------------------------------------------------------
# 2. Сверка — детерминированная
# ---------------------------------------------------------------------------


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _model_matches(product: dict, model: str) -> bool:
    """Все слова названной модели есть в названии товара: 'EZONE 98' ⊂
    'Yonex EZONE 98, 4 1/4 grip, blue'. Бренд в названии модели не мешает."""
    wanted = _words(model) - _words(product.get("brand") or "")
    return bool(wanted) and wanted <= _words(product["name"])


def _suits(product: dict, facts: IntentFacts) -> bool:
    """Подходит ли товар под названные человеком признаки."""
    return not any(f.code != "unchecked"
                   for f in _item_findings(product, facts, lambda _name: BLOCK))


# Русские названия цветов — по началу слова: «чёрная», «Черный», «чёрные».
# Порядок важен: «серебристый» раньше «серого».
_RU_COLORS = (("черн", "black"), ("бел", "white"), ("син", "blue"), ("голуб", "blue"),
              ("желт", "yellow"), ("серебр", "silver"), ("красн", "red"), ("зелен", "green"),
              ("сер", "grey"), ("розов", "pink"), ("коричн", "brown"), ("беж", "beige"),
              ("оранж", "orange"), ("фиолет", "purple"))


def _color_words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[^\W\d_]+", text.lower().replace("ё", "е")):
        w = "grey" if w == "gray" else w
        out.append(next((en for ru, en in _RU_COLORS if w.startswith(ru)), w))
    return out


def _color_match(have: str, want: str) -> str:
    """Цвет товара против названного человеком: "yes", "second" или "no".

    Совпадение по слову: «Triple Black» — чёрный, «Light Gray» — серый,
    «Чёрный» — тоже чёрный. У многоцветного товара («White/Black») главный
    цвет — первый: чёрный во второй части — это "second", не совпадение.
    """
    wanted = _color_words(want)
    if not wanted:
        return "no"
    parts = [p for p in re.split(r"/|,|&|\+|\bwith\b|\band\b|\bи\b|\bс\b", have.lower()) if p.strip()]
    for i, part in enumerate(parts):
        if set(wanted) <= set(_color_words(part)):
            return "yes" if i == 0 else "second"
    return "no"


# Системы размеров: «EU 42» и «42» — один размер, «US 9» и «EU 9» — разные.
_SIZE_SYSTEMS = {"eu", "us", "uk", "fr", "it", "jp", "ru"}
_SIZE_FILLER = {"size", "sz", "размер", "р"}
_SIZE_WORDS = {"small": "s", "medium": "m", "large": "l"}


def _size_parts(text: str) -> tuple[set, list]:
    tokens = re.findall(r"\d+/\d+|\d+(?:\.\d+)?|[^\W\d_]+", text.lower().replace(",", "."))
    systems = {t for t in tokens if t in _SIZE_SYSTEMS}
    rest = [_SIZE_WORDS.get(t, t.removesuffix(".0")) for t in tokens
            if t not in _SIZE_SYSTEMS and t not in _SIZE_FILLER]
    return systems, rest


def _same_size(have: str, want: str) -> bool:
    """Размер товара совпадает с названным: «EU 42» = «42», «42,5» = «42.5»,
    «Medium» = «M». Если система указана с обеих сторон, она тоже должна
    совпасть."""
    (have_sys, have_rest), (want_sys, want_rest) = _size_parts(have), _size_parts(want)
    if have_sys and want_sys and have_sys != want_sys:
        return False
    return bool(want_rest) and have_rest == want_rest


def _item_findings(product: dict, facts: IntentFacts, sev) -> list[Finding]:
    """Расхождения одного товара с фактами (общими или одной строки).

    Признак, которого у товара нет (None — магазин его не сообщил), не
    сверяется: это пометка "unchecked", а не расхождение, — человек увидит,
    что проверить не удалось.
    """
    out: list[Finding] = []
    name = product["name"]

    def unknown(key: str, what: str) -> bool:
        if product.get(key) is not None:
            return False
        out.append(Finding("unchecked", WARN, f"Asked for {what}; the order doesn't say: {name}."))
        return True

    brand = product.get("brand")
    if facts.brand and not unknown("brand", facts.brand) and brand.lower() != facts.brand.lower():
        out.append(Finding(
            "brand", sev("brand"),
            f"Asked for {facts.brand}, the item is {brand}: {name}.",
        ))

    if facts.brand_not and not facts.brand:
        unknown("brand", f"anything but {', '.join(facts.brand_not)}")
    if brand and brand.lower() in {b.lower() for b in facts.brand_not}:
        out.append(Finding(
            "brand-excluded", sev("brand_not"),
            f"Asked for anything but {', '.join(facts.brand_not)}, the item is "
            f"{brand}: {name}.",
        ))

    if facts.model and not _model_matches(product, facts.model):
        out.append(Finding(
            "model", sev("model"),
            f"Asked for the {facts.model}, the item is a different model: {name}.",
        ))

    if facts.color and not unknown("color", facts.color):
        match = _color_match(product["color"], facts.color)
        if match != "yes":
            second = f" ({facts.color} only as a second colour)" if match == "second" else ""
            out.append(Finding(
                "color", sev("color"),
                f"Asked for {facts.color}, the item is {product['color']}{second}: {name}.",
            ))

    # пустой размер — у товара размеров нет вовсе (банка мячей)
    if (facts.size_label and not unknown("size_label", f"size {facts.size_label}")
            and product["size_label"] and not _same_size(product["size_label"], facts.size_label)):
        out.append(Finding(
            "size", sev("size_label"),
            f"Asked for size {facts.size_label}, the item is size {product['size_label']}: {name}.",
        ))

    if (facts.level and not unknown("level", f"{facts.level} level")
            and product["level"] not in (facts.level, "any")):
        out.append(Finding(
            "level", sev("level"),
            f"Asked for {facts.level} level, the item is {product['level']} level: {name}.",
        ))

    if (facts.needs_refundable and not unknown("refundable", "something returnable")
            and not product["refundable"]):
        out.append(Finding(
            "refund", sev("needs_refundable"),
            f"Asked to be able to return it, the item is final sale: {name}.",
        ))

    if (facts.deadline_days is not None
            and not unknown("ships_in_days", f"delivery within {facts.deadline_days} days")
            and product["ships_in_days"] > facts.deadline_days):
        out.append(Finding(
            "deadline", sev("deadline_days"),
            f"Needed within {facts.deadline_days} days, the item ships in {product['ships_in_days']} days: {name}.",
        ))
    return out


def _describe(line: dict) -> str:
    parts = [line.get("brand"), line.get("model"), line.get("color"),
             f"size {line['size_label']}" if line.get("size_label") else None,
             f"×{line['quantity']}" if line.get("quantity") else None]
    if not (line.get("brand") or line.get("model")):
        parts.insert(0, "one more item")
    return " ".join(p for p in parts if p)


# Сколько раскладок позиций по строкам перебирать (около 8!: строк в
# живых просьбах единицы, а 6 строк × 6 позиций — уже 665 тысяч вариантов).
MAX_ASSIGNMENTS = 50_000


def _check_lines(facts: IntentFacts, items, sev) -> list[Finding]:
    """Каждой строке просьбы — своя позиция в корзине, без лишних и пропущенных.

    Раскладка позиций по строкам — та, при которой расхождений меньше всего
    (полный перебор: строк и позиций в заказе всегда немного). Если модели
    разошлись в деталях строк, предупреждает только поле, в котором разошлись
    (а если в числе вещей — всё, что взято из строк);
    условия на весь заказ («всё к пятнице») блокируют как обычно. Пропущенная
    позиция блокирует, даже если её услышала только одна модель: заказ, где
    пропала половина, хуже лишнего вопроса. Лишняя позиция при споре о числе
    вещей только предупреждает.
    """
    def count_sev(code: str) -> str:
        if "lines" in facts.soft or (code == "extra" and "line_count" in facts.disputed):
            return WARN
        return BLOCK

    def line_sev(i: int):
        def from_line(name: str) -> str:
            if f"lines.{name}" in facts.disputed or (
                    "line_count" in facts.disputed and name in facts.lines[i]):
                return WARN
            return sev(name)
        return from_line

    line_facts = [replace(facts, lines=(), **line) for line in facts.lines]
    # Перебор растёт как факториал: на десятке строк он не кончится никогда.
    # Такой заказ не проверяется автоматически, а уходит человеку.
    if math.perm(len(items) + len(line_facts), len(line_facts)) > MAX_ASSIGNMENTS:
        return [Finding("lines", BLOCK,
                        f"Too many items to check automatically ({len(line_facts)} asked for, "
                        f"{len(items)} in the order).")]

    def pair_findings(i: int, j: int) -> list[Finding]:
        product, qty = items[j]
        out = _item_findings(product, line_facts[i], line_sev(i))
        units = product.get("units", 1) * qty
        want = line_facts[i].quantity
        if want is not None and units != want:
            out.append(Finding("quantity", line_sev(i)("quantity"),
                               f"Asked for {want} of {_describe(facts.lines[i])}, "
                               f"the order has {units}: {product['name']}."))
        return out

    def cost(assignment) -> tuple[int, int]:
        # блокирующие расхождения + пропущенные строки + лишние позиции;
        # при равенстве — меньше предупреждений (иначе спорная строка может
        # достаться не той позиции)
        found = [f for i, j in enumerate(assignment) if j is not None for f in pair_findings(i, j)]
        used = {j for j in assignment if j is not None}
        missing = sum(j is None for j in assignment)
        blocking = sum(f.severity == BLOCK for f in found)
        unmatched = missing + len(items) - len(used)
        return blocking + unmatched, len(found) + unmatched

    slots = list(range(len(items))) + [None] * len(line_facts)
    best = min(set(permutations(slots, len(line_facts))), key=lambda a: (cost(a), a.__repr__()))

    out: list[Finding] = []
    for i, j in enumerate(best):
        if j is None:
            out.append(Finding("missing", count_sev("missing"),
                               f"Asked for {_describe(facts.lines[i])}; nothing in the order "
                               "matches it."))
        else:
            out += pair_findings(i, j)
    used = {j for j in best if j is not None}
    for j, (product, _qty) in enumerate(items):
        if j not in used:
            out.append(Finding("extra", count_sev("extra"), f"Not asked for: {product['name']}."))
    return out


def check_coherence(facts: IntentFacts, purchase, allowed_band, allowlist=(),
                    find=catalog.find) -> Verdict:
    """purchase: список (артикул, количество). allowed_band: (мин, макс) в центах.

    allowlist — утверждённые артикулы: нужны, чтобы понять, был ли у агента
    более подходящий выбор. Без этого «дорого» не отличить от «дешевле не было».
    find — поиск товара по артикулу (каталог прототипа или песочницы-магазина).
    """
    def sev(field_name: str) -> str:
        return WARN if field_name in facts.soft or field_name in facts.disputed else BLOCK

    findings: list[Finding] = []
    band_min, band_max = allowed_band
    items = [(find(sku), qty) for sku, qty in purchase]
    total = sum(p["price_cents"] * q for p, q in items)

    if facts.lines:
        findings += _check_lines(facts, items, sev)
    else:
        for product, _qty in items:
            findings += _item_findings(product, facts, sev)

    # цена: был ли доступен более дешёвый подходящий вариант
    if facts.price_preference == "cheap" and len(items) == 1 and not facts.lines:
        chosen, _ = items[0]
        cheaper = [
            find(s) for s in allowlist
            if find(s).get("category") == chosen.get("category")
            and _suits(find(s), facts)
            and find(s)["price_cents"] < chosen["price_cents"] * 0.85
        ]
        if cheaper:
            best = min(cheaper, key=lambda p: p["price_cents"])
            findings.append(Finding(
                "price", sev("price_preference"),
                f"Asked for something cheap; this costs ${chosen['price_cents']/100:.2f} "
                f"while {best['name']} fits too at ${best['price_cents']/100:.2f}.",
            ))

    if facts.explicit_max_cents and total > facts.explicit_max_cents:
        findings.append(Finding(
            "explicit-max", sev("explicit_max_cents"),
            f"Set a limit of ${facts.explicit_max_cents/100:.2f}, "
            f"the order costs ${total/100:.2f}.",
        ))

    # количество — в тех единицах, в которых считает человек (банки мячей,
    # а не упаковки); меньше просьбы — тоже расхождение
    if facts.quantity is not None and not facts.lines:
        bought = sum(p.get("units", 1) * q for p, q in items)
        if bought != facts.quantity:
            findings.append(Finding(
                "quantity", sev("quantity"),
                f"Asked for {facts.quantity}, the order has {bought}.",
            ))

    # требования без поля: код их не сверяет, но и не теряет — решает человек
    for text in facts.other:
        findings.append(Finding(
            "other", sev("other"),
            f"You asked for “{text}”; I can't check that from the order details.",
        ))
    for text in facts.other_optional:
        findings.append(Finding(
            "other", WARN, f"Wished for “{text}” if possible; not checked against the order.",
        ))

    return Verdict(coherent=not any(f.severity == BLOCK for f in findings), findings=findings)


# ---------------------------------------------------------------------------
# 3. Режим «до покупки» — та же сверка, другой момент вызова
# ---------------------------------------------------------------------------
#
# check_coherence выше отвечает на вопрос «эта уже сделанная покупка совпадает
# с просьбой?» — годится для аудита и споров постфактум. decide_before_purchase
# задаёт тот же вопрос до того, как агент нажал «купить»: результат — не
# вердикт для спора, а команда «можно продолжать» или «сначала спроси
# человека», с готовой причиной, которую можно ему показать.


ASK = "ask"
PROCEED = "proceed"


@dataclass
class Decision:
    action: str                                    # PROCEED | ASK
    reasons: list[Finding] = field(default_factory=list)   # BLOCK-находки — из-за них решили спросить
    notes: list[Finding] = field(default_factory=list)     # WARN-находки — можно продолжать, но человеку видно

    @property
    def question(self) -> str | None:
        """Готовый вопрос человеку, если решили спросить. None, если можно продолжать."""
        if self.action != ASK:
            return None
        bullets = "\n".join(f"  - {f.text}" for f in self.reasons)
        return f"Before I buy this, please check:\n{bullets}\nShould I still go ahead?"


def decide_before_purchase(facts: IntentFacts, purchase, allowed_band, allowlist=(),
                           find=catalog.find) -> Decision:
    """Решает, можно ли агенту продолжить покупку без подтверждения человека.

    Ничего нового не проверяет — использует ту же check_coherence на
    предполагаемой покупке, до того как она состоялась. BLOCK-находки
    останавливают агента и требуют подтверждения; WARN-находки не
    останавливают, но остаются видны в notes.
    """
    verdict = check_coherence(facts, purchase, allowed_band, allowlist, find)
    reasons = [f for f in verdict.findings if f.severity == BLOCK]
    notes = [f for f in verdict.findings if f.severity == WARN]
    return Decision(action=ASK if reasons else PROCEED, reasons=reasons, notes=notes)
