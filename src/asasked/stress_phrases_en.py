"""Live English phrasings, the pair to stress_phrases.py.

The same rules: expect only for fields where the person spoke unambiguously;
expect=None is for reading by hand. The categories follow the Russian set and
add what is specific to English speech: shortened amounts ("150 bucks",
"1.5k"), "a couple" / "a few" / "half a dozen", British and American
spelling, colloquial "kinda", "tbh", "lmk".

Amounts in explicit_max_cents are in cents of the chosen currency ($150 -> 15000).
"""

from __future__ import annotations

from .stress_phrases import StressCase

CASES_EN: list[StressCase] = [

    # ---- clear, but not literal -------------------------------------------
    StressCase(
        "en-clear-1", "clear",
        "I want a Babbolat racket, black, on the cheaper side.",
        expect={"brand": "Babolat", "color": "black", "price_preference": "cheap"},
        note="misspelled brand",
    ),
    StressCase(
        "en-clear-2", "clear",
        "Asics, size 42, and make sure I can send them back if they don't fit.",
        expect={"brand": "ASICS", "size_label": "42", "needs_refundable": True},
    ),
    StressCase(
        "en-clear-3", "clear",
        "Grab me a couple of cans of balls, actually three should be plenty.",
        expect={"quantity": 3},
        note="the later number overrides 'a couple'",
    ),

    # ---- muddled -----------------------------------------------------------
    StressCase(
        "en-confused-1", "muddled",
        "So I used to have this racket, can't remember the brand, it was "
        "really good, I want something kinda like that but not crazy "
        "expensive, you know what I mean.",
        expect={"price_preference": "cheap", "brand": None},
        note="no brand or level named; the model must not invent one",
    ),
    StressCase(
        "en-confused-2", "muddled",
        "Get something for beginners, I've literally never held a racket before.",
        expect={"level": "beginner"},
    ),
    StressCase(
        "en-confused-3", "muddled",
        "Those tennis shoes, what are they called, I need them for Saturday, "
        "gotta run.",
        expect=None,
        note="a deadline is stated without a reference date; a day estimate or null are both fine",
    ),
    StressCase(
        "en-confused-4", "muddled",
        "I need that thing for tennis, the one you hit with, my brother "
        "recommended something but I forgot what.",
        expect={"brand": None, "color": None},
        note="almost no facts; control for invented brand or colour",
    ),

    # ---- caveats -> soft fields ------------------------------------------
    StressCase(
        "en-caveat-1", "caveat",
        "Babolat ideally, but if it's pricey another brand is fine as long as "
        "it's not worse than HEAD.",
        expect={"brand": "Babolat"},
        expect_soft=frozenset({"brand"}),
        note="the person loosens the brand themselves",
    ),
    StressCase(
        "en-caveat-2", "caveat",
        "Black shoes, but if they only have white, whatever, not a big deal.",
        expect=None,
        expect_soft=frozenset({"color"}),
    ),
    StressCase(
        "en-caveat-3", "caveat",
        "Something cheap overall, but if you see a really great one for a bit "
        "more, go for it.",
        expect=None,
        expect_soft=frozenset({"price_preference"}),
    ),

    # ---- contradictions ---------------------------------------------------
    StressCase(
        "en-contra-1", "contradiction",
        "Cheap, but the absolute top model you've got.",
        expect=None,
        note="cheap vs premium; see what the model does",
    ),
    StressCase(
        "en-contra-2", "contradiction",
        "I need 2, but grab like five just in case.",
        expect=None,
    ),
    StressCase(
        "en-contra-3", "contradiction",
        "Don't care about returns, I'm specifically after the cheapest "
        "non-refundable one, but I can still return it if it doesn't fit, right?",
        expect=None,
    ),
    StressCase(
        "en-contra-4", "contradiction",
        "Get Wilson, actually no, not Wilson, any other brand.",
        expect={"brand": None},
        note="the person takes the brand back; the final fact must be null",
    ),

    # ---- negations ---------------------------------------------------------
    StressCase(
        "en-negation-1", "negation",
        "Any brand is fine, just not Wilson.",
        expect={"brand": None},
    ),
    StressCase(
        "en-negation-2", "negation",
        "Anything but black or white, any other colour works.",
        expect={"color": None},
        note="British spelling of colour",
    ),

    # ---- money formats -----------------------------------------------------
    StressCase(
        "en-price-1", "money format",
        "Budget is $150 max, no more.",
        expect={"explicit_max_cents": 15000},
    ),
    StressCase(
        "en-price-2", "money format",
        "Around 300 bucks, give or take.",
        expect=None,
        expect_soft=frozenset({"explicit_max_cents"}),
        note="an approximate amount; if extracted it must be soft",
    ),
    StressCase(
        "en-price-3", "money format",
        "Under 1.5k, that's my hard ceiling.",
        expect={"explicit_max_cents": 150000},
    ),
    StressCase(
        "en-price-4", "money format",
        "Don't spend more than a hundred and twenty dollars.",
        expect={"explicit_max_cents": 12000},
        note="amount written in words",
    ),

    # ---- deadlines ---------------------------------------------------------
    StressCase(
        "en-deadline-1", "deadline",
        "Super urgent, I need it tomorrow or the day after at the latest.",
        expect=None,
        note="expect 1-2 days; checked by eye",
    ),
    StressCase(
        "en-deadline-2", "deadline",
        "No rush at all, a month from now is fine.",
        expect=None,
    ),
    StressCase(
        "en-deadline-3", "deadline",
        "Has to arrive within 3 days, I'm flying out.",
        expect={"deadline_days": 3},
    ),

    # ---- level by description ---------------------------------------------
    StressCase(
        "en-level-1", "level by description",
        "First time ever picking up a racket, so something simple.",
        expect={"level": "beginner"},
    ),
    StressCase(
        "en-level-2", "level by description",
        "Been playing ten years, three times a week, I need a serious racket.",
        expect={"level": "pro"},
    ),

    # ---- refunds, indirectly ----------------------------------------------
    StressCase(
        "en-refund-1", "refund, indirect",
        "What happens if it doesn't work out? I'd like a safety net.",
        expect={"needs_refundable": True},
    ),
    StressCase(
        "en-refund-2", "refund, indirect",
        "I want a money-back guarantee in case I don't like it.",
        expect={"needs_refundable": True},
    ),

    # ---- slang, typos, lowercase -----------------------------------------
    StressCase(
        "en-slang-1", "slang/typos",
        "need asix kicks sz 42 black pref but tbh other colours r fine too",
        expect={"brand": "ASICS", "size_label": "42"},
        note="the colour preference is softened; it must not become a hard requirement",
    ),
    StressCase(
        "en-slang-2", "slang/typos",
        "babolat cheapest one pls lmk",
        expect={"brand": "Babolat", "price_preference": "cheap"},
    ),

    # ---- hyperbole ---------------------------------------------------------
    StressCase(
        "en-hyperbole-1", "hyperbole",
        "I couldn't care less about the brand, just don't make it cost a million.",
        expect={"brand": None, "explicit_max_cents": None},
        note="hyperbole about price is not a limit",
    ),

    # ---- comparison with last time ---------------------------------------
    StressCase(
        "en-compare-1", "comparison",
        "Same as last time, just cheaper.",
        expect={"price_preference": "cheap", "brand": None},
        note="nothing may be inferred from 'last time'",
    ),

    # ---- empty / irrelevant ----------------------------------------------
    StressCase(
        "en-empty-1", "empty/irrelevant",
        "Hey! How's it going? What's new?",
        expect={"brand": None, "color": None, "quantity": None, "needs_refundable": False},
        note="no purchase facts at all; the key hallucination control",
    ),
    StressCase(
        "en-empty-2", "empty/irrelevant",
        "Just see what's out there, nothing specific yet.",
        expect={"brand": None, "quantity": None},
    ),

    # ---- long and muddled -------------------------------------------------
    StressCase(
        "en-long-1", "long, muddled",
        "Ok so I need a racket, I'm a beginner tbh, but my friend says get a "
        "proper one straight away, not a kids' one, but I don't want to "
        "overpay either, let's say Babolat since everyone has them, though I "
        "honestly don't mind, main thing is it gets here within a week max, my "
        "first lesson is in 10 days.",
        expect={"brand": "Babolat"},
        note="level, price and deadline all pull in different directions inside one phrase",
    ),

    # ---- quantity in words -------------------------------------------------
    StressCase(
        "en-quantity-1", "quantity in words",
        "Get a couple of cans of balls.",
        expect={"quantity": 2},
    ),
    StressCase(
        "en-quantity-2", "quantity in words",
        "Half a dozen cans should do it.",
        expect={"quantity": 6},
    ),
    StressCase(
        "en-quantity-3", "quantity in words",
        "Four or so cans, maybe five, doesn't really matter.",
        expect=None,
        expect_soft=frozenset({"quantity"}),
        note="the person is undecided between 4 and 5 and says it doesn't matter",
    ),

    # ---- unusual size formats ---------------------------------------------
    StressCase(
        "en-size-1", "unusual size",
        "Racket with a 4 and 3/8 grip, if that's how you measure it.",
        expect={"size_label": "4 3/8"},
    ),
    StressCase(
        "en-size-2", "unusual size",
        "42 ideally, but if you've only got 43 then 43, not critical.",
        expect=None,
        expect_soft=frozenset({"size_label"}),
    ),

    # ---- mixed language ----------------------------------------------------
    StressCase(
        "en-mixed-1", "mixed language",
        "Need ASICS, сорок второй размер, black please.",
        expect={"brand": "ASICS", "size_label": "42", "color": "black"},
        note="code-switching between English and Russian in one request",
    ),
]
