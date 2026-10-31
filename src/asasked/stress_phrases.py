"""Live Russian phrasings for stress-testing extract_intent.

Not purchase scenarios (as in scenarios.py): only the person's request here.
Some phrases have an expectation (expect): only the fields where the person
spoke unambiguously; the rest are not checked. For plainly confused or
contradictory phrases expect=None: the model need not guess the "right"
answer here, because often there is none; such phrases are for reading the
output by hand, not for an automatic check.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StressCase:
    id: str
    category: str
    phrase: str
    expect: dict | None = None
    note: str = ""
    # Names of the fields that must end up in IntentFacts.soft, that is, the
    # model must notice that the person relaxed the requirement themselves.
    expect_soft: frozenset = frozenset()


CASES: list[StressCase] = [

    # ---- clear, but not stated head-on ---------------------------------
    StressCase(
        "clear-1", "clear wording",
        "Хочу ракетку Бабблат, чёрную, подешевле.",
        expect={"brand": "Babolat", "color": "black", "price_preference": "cheap"},
        note="colloquial spelling of the brand, with a typo",
    ),
    StressCase(
        "clear-2", "clear wording",
        "Асиксы, 42 размерчик, и чтобы можно было сдать если не сядут.",
        expect={"brand": "ASICS", "size_label": "42", "needs_refundable": True},
    ),
    StressCase(
        "clear-3", "clear wording",
        "Мне бы парочку банок мячей, штуки три хватит с головой.",
        expect={"quantity": 3},
        note="'парочка' (a couple) is not literally 2 here: the later 'три' (three) overrides it",
    ),

    # ---- confused, with caveats, "you know" ----------------------------
    StressCase(
        "confused-1", "confused",
        "Ну короче раньше у меня была ракетка, не помню какая марка, но "
        "что-то прям хорошее было, вот такое же примерно хочу, только чтобы "
        "не дорого прям было, ну ты понял.",
        expect={"price_preference": "cheap"},
        note="brand and level are not named at all: the model must not invent them",
    ),
    StressCase(
        "confused-2", "confused",
        "Возьми что-нибудь для начинающих, ну ты понял о чём я, я вообще "
        "первый раз ракетку в руки беру.",
        expect={"level": "beginner"},
    ),
    StressCase(
        "confused-3", "confused",
        "Слушай ну там кроссовки эти, как их, для тенниса, короче на выход "
        "в субботу нужны, я побежал уже почти.",
        expect=None,
        note="a deadline is named outright ('for Saturday'), but with no reference date the model may "
             "either estimate the days or leave null; both are reasonable, see what came out",
    ),
    StressCase(
        "confused-4", "confused",
        "Мне бы такую штуку, ну для тенниса, чтобы бить можно было, не знаю "
        "как называется, брат посоветовал что-то, я не запомнил.",
        expect=None,
        note="a phrase with almost no facts: a control that the model does not invent a brand/colour",
    ),

    # ---- with caveats ------------------------------------------------------
    StressCase(
        "caveat-1", "with a caveat",
        "Хочу Babolat, но если будет дорого — можно и другой бренд, "
        "главное чтобы не хуже HEAD по качеству.",
        expect={"brand": "Babolat"},
        note="the caveat relaxes the brand requirement: how will the model show it",
    ),
    StressCase(
        "caveat-2", "with a caveat",
        "Черные кроссовки, а вообще если только белые есть — ну ладно, "
        "разница не принципиальная.",
        expect=None,
        expect_soft=frozenset({"color"}),
        note="the person drops the colour requirement themselves: must end up in soft_fields",
    ),
    StressCase(
        "caveat-3", "with a caveat",
        "В целом недорого нужно, но если увидишь прям супер вариант чуть "
        "дороже — бери, не страшно.",
        expect=None,
        expect_soft=frozenset({"price_preference"}),
        note="the price preference is relaxed by a condition: must end up in soft_fields",
    ),

    # ---- contradictions in one phrase -------------------------------------------
    StressCase(
        "contra-1", "contradiction",
        "Недорого, но самую топовую модель какая есть.",
        expect=None,
        note="a direct contradiction, cheap vs premium: what will the model pick, if anything",
    ),
    StressCase(
        "contra-2", "contradiction",
        "Нужно 2 штуки, но возьми с запасом штук пять на всякий случай.",
        expect=None,
        note="a contradiction in quantity",
    ),
    StressCase(
        "contra-3", "contradiction",
        "Не нужно ничего возвратного, специально ищу что подешевле и "
        "невозвратное, но если вдруг не подойдёт — верну же?",
        expect=None,
        note="a contradiction about returns within one phrase",
    ),
    StressCase(
        "contra-4", "contradiction",
        "Возьми Wilson, хотя нет, лучше не Wilson, любой другой бренд.",
        expect={"brand": None},
        note="the person cancels their own brand choice: the final fact must be null, not Wilson",
    ),

    # ---- negations --------------------------------------------------
    StressCase(
        "negation-1", "negation",
        "Всё равно какой бренд, лишь бы не Wilson.",
        expect={"brand": None},
        note="a brand is named, but as an exclusion, not a choice: must not become brand=Wilson",
    ),
    StressCase(
        "negation-2", "negation",
        "Только не чёрные и не белые, любой другой цвет подойдёт.",
        expect={"color": None},
    ),

    # ---- numbers and prices in various formats --------------------------------
    StressCase(
        "price-1", "price format",
        "Бюджет тысяч до пятнадцати, не больше.",
        expect={"explicit_max_cents": 1500000},
    ),
    StressCase(
        "price-2", "price format",
        "Ну рублей на триста где-то, плюс-минус.",
        expect=None,
        expect_soft=frozenset({"explicit_max_cents"}),
        note="an approximate amount: if explicit_max_cents is extracted at all, it must be soft",
    ),
    StressCase(
        "price-3", "price format",
        "До 15к, красная цена вопроса.",
        expect={"explicit_max_cents": 1500000},
    ),

    # ---- deadlines ------------------------------------------------------
    StressCase(
        "deadline-1", "deadline",
        "Нужно очень срочно, прям завтра-послезавтра максимум.",
        expect=None,
        note="a small number of days (1-2) is expected, with no strict check: judged by eye",
    ),
    StressCase(
        "deadline-2", "deadline",
        "Не горит вообще, можно и через месяц привезти.",
        expect=None,
    ),
    StressCase(
        "deadline-3", "deadline",
        "К пятнице максимум, у меня турнир в субботу утром.",
        expect=None,
        note="a small number of days is expected; checked by hand, as the exact number depends on today's date",
    ),

    # ---- level by description, not by word ----------------------------
    StressCase(
        "level-1", "level by description",
        "Я вообще первый раз в руки ракетку беру, так что что-нибудь простое.",
        expect={"level": "beginner"},
    ),
    StressCase(
        "level-2", "level by description",
        "Играю уже лет десять, три раза в неделю, нужна серьёзная ракетка.",
        expect={"level": "pro"},
    ),

    # ---- returns through indirect phrasing -------------------------------
    StressCase(
        "refund-1", "returns, indirectly",
        "А если вдруг не подойдёт — что делать будем? Хочу подстраховаться.",
        expect={"needs_refundable": True},
    ),
    StressCase(
        "refund-2", "returns, indirectly",
        "Хочу с гарантией возврата денег, мало ли не понравится.",
        expect={"needs_refundable": True},
    ),

    # ---- slang, typos, mixed case -------------------------------------
    StressCase(
        "slang-1", "slang/typos",
        "нужны кроссы асиксы 42р чёрные преф но если что и другой цвет норм заходит",
        expect={"brand": "ASICS", "size_label": "42"},
        note="the colour preference is relaxed ('other colours are fine too'): must not become a hard requirement",
    ),
    StressCase(
        "slang-2", "slang/typos",
        "скинь бабблат подешевле го",
        expect={"brand": "Babolat", "price_preference": "cheap"},
    ),

    # ---- sarcasm / hyperbole --------------------------------------------
    StressCase(
        "hyperbole-1", "hyperbole",
        "Да мне вообще пофиг какой бренд, лишь бы не за миллион цена была.",
        expect={"brand": None},
        note="a hyperbole about price must not become explicit_max_cents=100000000",
    ),

    # ---- comparison with last time ---------------------------------------
    StressCase(
        "compare-1", "comparison",
        "Как в прошлый раз, только подешевле.",
        expect={"price_preference": "cheap"},
        note="brand/model are not named: nothing must be inferred from 'last time'",
    ),

    # ---- wholly irrelevant / empty control ------------------------------
    StressCase(
        "empty-1", "empty/irrelevant",
        "Привет! Как сам? Что новенького?",
        expect={"brand": None, "color": None, "quantity": None, "needs_refundable": False},
        note="the request has no product facts at all: the key control for hallucinations",
    ),
    StressCase(
        "empty-2", "empty/irrelevant",
        "Просто посмотри, что вообще есть, пока ничего конкретного.",
        expect={"brand": None, "quantity": None},
    ),

    # ---- a long confused phrase with several contradictions at once ---------
    StressCase(
        "long-1", "long and confused",
        "Так, короче, нужна ракетка, я новичок вообще-то, но подруга "
        "посоветовала брать сразу нормальную, не детскую какую-то, но и "
        "переплачивать не хочу, пусть будет Babolat раз уж они у всех, хотя "
        "мне вообще пофиг, главное чтобы за неделю максимум пришла, у меня "
        "через 10 дней первая тренировка.",
        expect={"brand": "Babolat"},
        note="level (beginner vs 'a proper one, not a kid's'), price (cheap vs 'don't want to overpay') "
             "and a deadline, all in one phrase that contradicts itself",
    ),

    # ---- plurals / collective numerals ---------------------------------------
    StressCase(
        "quantity-1", "quantity in words",
        "Возьми пару банок мячей.",
        expect={"quantity": 2},
    ),
    StressCase(
        "quantity-2", "quantity in words",
        "Штучки четыре мячей хватит, ну может пять, не важно особо.",
        expect=None,
        note="the person is undecided between 4 and 5: see what the model picks",
    ),

    # ---- size in an unusual format ------------------------------------------
    StressCase(
        "size-1", "unusual size format",
        "Ракетку на 4 и 3/8 хвата, если у вас так меряют.",
        expect={"size_label": "4 3/8"},
    ),
    StressCase(
        "size-2", "unusual size format",
        "Сорок вторым бы, но если только 43 есть — ну тогда 43, не критично.",
        expect=None,
        note="the person relaxes the size requirement themselves: a hard test of nuance",
    ),
]
