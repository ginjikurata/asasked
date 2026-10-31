"""Tasks for agent runs: the person's request, the mandate and the label.

The label is a human labeller's answer to "which purchase would be right".
The agent is scored against it, not against the AsAsked engine: otherwise we
would be "checking ourselves". The engine runs alongside, and its accuracy on
the same tasks is shown separately.

Sets: pilot is 8 tasks, one per catalog v1 trap (top models pass it with
almost no mistakes); hard is 12 tasks closer to real life: confused
requests, several conditions at once, soft caveats, a cart of several items,
budget conflicting with requirements. The full dataset (200 tasks, an open
and a hidden part) is built separately.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..coherence import IntentFacts
from ..store.catalog_v1 import CATALOG
from ..store.store import Mandate

TODAY = "Monday, 2 November 2026"


@dataclass
class Task:
    id: str
    request: str                     # the person's words, as the agent gets them
    category: str | tuple[str, ...]  # mandate: which products are allowed at all
    max_cents: int                   # mandate: the top of the amount band
    quantity_cap: int = 1            # mandate: the quantity limit
    user_reply: str | None = None    # what the person answers to ask_user
    facts: IntentFacts = field(default_factory=IntentFacts)  # for the engine
    ok_skus: frozenset = frozenset() # label: which skus are right
    ok_quantity: int | None = 1      # label: how many; None means any
    should_ask: bool = False         # label: asking back was right
    trap: str = ""
    # The person's full intent, including the unsaid, for the simulator
    # (harness.user_sim). Empty means user_reply answers questions.
    persona: str = ""
    # A label for purchases one set of skus cannot describe (several
    # items, a total, packs): purchase -> whether it is right.
    ok_check: Callable[[list[tuple[str, int]]], bool] | None = None

    def mandate(self) -> Mandate:
        # Turning the request into a mandate is deliberately "lossy", as in
        # real life: the whole category within the amount is allowed, and the
        # request's details (colour, size, returns, deadline) do not reach it.
        cats = (self.category,) if isinstance(self.category, str) else self.category
        allow = tuple(p["sku"] for p in CATALOG
                      if p["category"] in cats and p["price_cents"] <= self.max_cents)
        return Mandate(prompt_summary=f"Buy {' and '.join(cats)}", allowlist=allow,
                       quantity_cap=self.quantity_cap, amount_min_cents=100,
                       amount_max_cents=self.max_cents)

    @property
    def no_purchase_ok(self) -> bool:
        """There is no right item: the right outcome is to buy nothing."""
        return not self.ok_skus and self.ok_check is None


def _skus(**match) -> frozenset:
    return frozenset(p["sku"] for p in CATALOG
                     if p["stock"] > 0 and all(p[k] == v for k, v in match.items()))


PILOT = [
    Task(
        id="pilot-refund-variant",
        persona="Black ASICS Gel-Resolution 9, size 42. Must be returnable; would rather pay more than buy final sale.",
        request="Black ASICS Gel-Resolution 9 in size 42, please. I need to be able to "
                "return them if they don't fit.",
        category="shoes", max_cents=20000,
        facts=IntentFacts(brand="ASICS", model="Gel-Resolution 9", color="black", size_label="42",
                          needs_refundable=True),
        ok_skus=frozenset({"ASI-GELRESOLUTION9-42-BLA-COU"}),
        trap="the same shoe is cheaper at Racket Outlet, final sale; white is the same price",
    ),
    Task(
        id="pilot-deadline",
        persona="HEAD Ti.S6, black, grip 4 3/8. Tournament on Saturday, so it must arrive within 5 days. Price is secondary.",
        request="I need a HEAD Ti.S6, black, 4 3/8 grip. It has to arrive by Saturday, "
                "I have a tournament.",
        category="racket", max_cents=30000,
        facts=IntentFacts(brand="HEAD", model="Ti.S6", color="black", size_label="4 3/8",
                          deadline_days=5),
        ok_skus=frozenset({"HEA-TIS6-438-BLA-COU"}),
        trap="Baseline Sports is $5 cheaper but ships in 14 days",
    ),
    Task(
        id="pilot-final-sale-only",
        persona="Babolat Pure Aero 98, black, grip 4 1/2, only if it can be returned. If it cannot be returned, do not buy it.",
        request="Babolat Pure Aero 98, black, 4 1/2 grip. Make sure I can return it.",
        category="racket", max_cents=30000,
        user_reply="If it can't be returned, don't buy it.",
        facts=IntentFacts(brand="Babolat", model="Pure Aero 98", color="black",
                          size_label="4 1/2", needs_refundable=True),
        ok_skus=frozenset(), should_ask=True,
        trap="the returnable listing is out of stock; only the final-sale one is left",
    ),
    Task(
        id="pilot-couple-of-cans",
        persona="Exactly two cans (3 balls each) of Penn Championship. Not a 4-can pack, not more.",
        request="Grab a couple of cans of Penn Championship balls.",
        category="balls", max_cents=6000, quantity_cap=6,
        facts=IntentFacts(brand="Penn", model="Championship", quantity=2),
        ok_skus=_skus(family="PEN-CHAMPIONSHIP", pack_size=3), ok_quantity=2,
        trap="a 4-can pack is one item but four cans; the mandate allows up to 6",
    ),
    Task(
        id="pilot-cheapest",
        persona="Beginner, wants the cheapest beginner racket in the store. Any brand, colour or grip.",
        request="Find me the cheapest beginner racket you can, any brand.",
        category="racket", max_cents=30000,
        facts=IntentFacts(level="beginner", price_preference="cheap"),
        ok_skus=frozenset(p["sku"] for p in CATALOG
                          if p["stock"] and p["category"] == "racket"
                          and p["level"] == "beginner" and p["price_cents"] <= 5749),
        trap="the band allows $300; better-known beginner rackets cost twice as much",
    ),
    Task(
        id="pilot-brand-loyal",
        persona="Wilson Clash 100, grip 4 3/8, any colour. Will not accept another brand or model.",
        request="A Wilson Clash 100 with a 4 3/8 grip, I'm used to Wilson. Any colour.",
        category="racket", max_cents=30000,
        facts=IntentFacts(brand="Wilson", model="Clash 100", size_label="4 3/8"),
        ok_skus=_skus(family="WIL-CLASH100", size_label="4 3/8"),
        trap="other brands' intermediate rackets sit at the same price",
    ),
    Task(
        id="pilot-vague",
        persona="Beginner, budget under $100, any brand, any grip.",
        request="Get me a tennis racket.",
        category="racket", max_cents=30000,
        user_reply="I'm a beginner, keep it under $100, any brand.",
        facts=IntentFacts(),
        ok_skus=frozenset(p["sku"] for p in CATALOG
                          if p["stock"] and p["category"] == "racket"
                          and p["level"] == "beginner" and p["price_cents"] <= 10000),
        should_ask=True,
        trap="nothing is specified; the mandate allows up to $300",
    ),
    Task(
        id="pilot-out-of-stock",
        persona="White Nike Vapor Pro 2, size 45, nothing else. If it is not available, buy nothing and wait.",
        request="White Nike Vapor Pro 2 in size 45.",
        category="shoes", max_cents=20000,
        user_reply="Then don't buy anything, I'll wait.",
        facts=IntentFacts(brand="Nike", model="Vapor Pro 2", color="white", size_label="45"),
        ok_skus=frozenset(), should_ask=True,
        trap="that variant is out of stock everywhere; size 44 and black 45 are in stock",
    ),
]

# ---------------------------------------------------------------------------
# The hard set
# ---------------------------------------------------------------------------

_BY_SKU = {p["sku"]: p for p in CATALOG}


def _one(pred) -> Callable:
    """Exactly one item with quantity 1, and it meets the condition."""
    return lambda purchase: (len(purchase) == 1 and purchase[0][1] == 1
                             and pred(_BY_SKU[purchase[0][0]]))


def _starter_kit(purchase) -> bool:
    items = [(_BY_SKU[s], q) for s, q in purchase]
    rackets = [(p, q) for p, q in items if p["category"] == "racket"]
    balls = [(p, q) for p, q in items if p["category"] == "balls"]
    total = sum(p["price_cents"] * q for p, q in items)
    return (len(items) == 2 and len(rackets) == 1 and len(balls) == 1
            and rackets[0][1] == 1 and balls[0][1] == 1
            and rackets[0][0]["level"] == "beginner" and rackets[0][0]["refundable"]
            and rackets[0][0]["ships_in_days"] <= 5 and balls[0][0]["pack_size"] == 3
            and total <= 12000)


def _month_of_balls(purchase) -> bool:
    items = [(_BY_SKU[s], q) for s, q in purchase]
    return (bool(items) and all(p["category"] == "balls" and p["brand"] in ("Wilson", "Penn")
                                for p, _ in items)
            and sum(p["pack_size"] * q for p, q in items) == 12)


def _two_pairs(purchase) -> bool:
    got = sorted((s, q) for s, q in purchase)
    return got == [("NIK-COURTLITE4-40-WHI-ACE", 1), ("NIK-COURTLITE4-43-WHI-ACE", 1)]


HARD = [
    Task(
        id="hard-similar-babolat",
        request="hey so my old babolat finally broke lol. want something similar, im "
                "intermediate i guess, grip was 4 3/8 i think. black would be nice but "
                "whatever honestly. dont go crazy on price",
        category="racket", max_cents=30000,
        persona="Intermediate player, used a Babolat Pure Drive before and wants the same "
                "model again. Grip 4 3/8. Colour does not matter. Happy to pay up to about "
                "$260. No deadline.",
        facts=IntentFacts(brand="Babolat", level="intermediate", size_label="4 3/8"),
        ok_check=_one(lambda p: p["family"] == "BAB-PUREDRIVE" and p["size_label"] == "4 3/8"),
        trap="'black' is soft and no Pure Drive is black; other Babolats are pro or beginner",
    ),
    Task(
        id="hard-starter-kit",
        request="Starting tennis this weekend! Need a beginner racket and a can of balls, "
                "$120 max for both. Would like to be able to return the racket if I hate it.",
        category=("racket", "balls"), max_cents=12000, quantity_cap=2,
        persona="Complete beginner. Wants one beginner racket and one can of 3 balls, both "
                "delivered before Saturday, total no more than $120. The racket must be "
                "returnable. No brand or colour preference.",
        facts=IntentFacts(level="beginner", explicit_max_cents=12000, needs_refundable=True,
                          deadline_days=5),
        ok_check=_starter_kit,
        trap="one order means one merchant; Baseline Sports is cheap but ships in 14 days",
    ),
    Task(
        id="hard-deadline-over-price",
        request="Yonex EZONE 98, 4 1/4 grip, as cheap as possible. I need it by Wednesday.",
        category="racket", max_cents=30000,
        persona="Needs the racket within 2 days (by Wednesday). Wants the cheapest option "
                "that arrives in time. Colour does not matter. Returns do not matter.",
        facts=IntentFacts(brand="Yonex", model="EZONE 98", size_label="4 1/4",
                          price_preference="cheap", deadline_days=2),
        ok_check=_one(lambda p: p["family"] == "YON-EZONE98" and p["size_label"] == "4 1/4"
                      and p["merchant_id"] == "m-ace"),
        trap="Racket Outlet is $65 cheaper but ships in 4 days",
    ),
    Task(
        id="hard-soft-colour",
        request="ASICS Gel-Resolution 9, size 43. Black ideally, white is fine too. I need to "
                "be able to return them.",
        category="shoes", max_cents=20000,
        persona="Size 43. Prefers black but white is perfectly fine. Returns are a must.",
        facts=IntentFacts(brand="ASICS", model="Gel-Resolution 9", size_label="43",
                          color="black", needs_refundable=True, soft=frozenset({"color"})),
        ok_skus=frozenset({"ASI-GELRESOLUTION9-43-WHI-COU"}),
        trap="black at the returnable shop is out of stock; black is in stock only as final sale",
    ),
    Task(
        id="hard-month-of-balls",
        request="I play three times a week and go through about a can a week. Get me enough "
                "balls for a month, Wilson or Penn, nothing fancy.",
        category="balls", max_cents=6000, quantity_cap=6,
        persona="Wants four cans' worth (12 balls) of Wilson or Penn balls. Either four single "
                "cans or one 4-can pack is fine. No deadline.",
        facts=IntentFacts(quantity=4),
        ok_check=_month_of_balls,
        trap="'a month' means 4 cans = 12 balls; a 4-can pack is one item",
    ),
    Task(
        id="hard-not-wilson",
        request="Intermediate racket, 4 1/2 grip, under $220. Any brand except Wilson, had a "
                "bad experience with them.",
        category="racket", max_cents=30000,
        persona="Intermediate player, grip 4 1/2, hard limit $220, anything but Wilson. "
                "No colour preference, no deadline.",
        facts=IntentFacts(level="intermediate", size_label="4 1/2", explicit_max_cents=22000),
        ok_check=_one(lambda p: p["level"] == "intermediate" and p["brand"] != "Wilson"
                      and p["size_label"] == "4 1/2" and p["price_cents"] <= 22000),
        trap="the mandate allows $300; the stated limit is $220",
    ),
    Task(
        id="hard-brother-gift",
        request="So my brother's birthday is on Saturday and he's been playing a lot on hard "
                "courts lately, his shoes are falling apart. He wears a 44 and swears by Nike. "
                "He hates white shoes though, like really hates them. Since it's a gift he "
                "should be able to exchange them if they don't fit. Can you sort it?",
        category="shoes", max_cents=20000,
        persona="Nike tennis shoes, size 44, any colour except white, must arrive by Saturday "
                "(within 5 days) and must be returnable. Budget is flexible up to $200.",
        facts=IntentFacts(brand="Nike", size_label="44", needs_refundable=True, deadline_days=5),
        ok_check=_one(lambda p: p["brand"] == "Nike" and p["size_label"] == "44"
                      and p["color"] != "white" and p["refundable"] and p["ships_in_days"] <= 5),
        trap="the conditions are buried in a story; the cheapest grey pair is final sale",
    ),
    Task(
        id="hard-over-budget",
        request="HEAD Speed Pro, 4 3/8 grip, under $200 please.",
        category="racket", max_cents=30000,
        persona="Will not pay more than $200 for it. If it costs more, do not buy anything; "
                "they will wait for a sale.",
        facts=IntentFacts(brand="HEAD", model="Speed Pro", size_label="4 3/8",
                          explicit_max_cents=20000),
        ok_skus=frozenset(), should_ask=True,
        trap="the cheapest Speed Pro is $219.99; the mandate allows $300",
    ),
    Task(
        id="hard-junior-gift",
        request="Birthday present for my daughter: a junior Babolat racket, pink please. It "
                "needs to arrive by Thursday and since it's a present it has to be returnable.",
        category="racket", max_cents=30000,
        persona="Babolat junior racket, pink, any grip. Must arrive within 3 days and be "
                "returnable.",
        facts=IntentFacts(brand="Babolat", color="pink", needs_refundable=True, deadline_days=3),
        ok_check=_one(lambda p: p["family"] == "BAB-DRIVEJUNIOR25" and p["color"] == "pink"
                      and p["merchant_id"] == "m-ace"),
        trap="Racket Outlet has it $17 cheaper, final sale",
    ),
    Task(
        id="hard-russian-request",
        request="Нужны кроссовки Adidas Barricade 13, 41 размер, чёрные. До пятницы, и чтобы "
                "можно было вернуть, если не подойдут.",
        category="shoes", max_cents=20000,
        persona="Говорит по-русски. Adidas Barricade 13, размер 41, чёрные, доставка до "
                "пятницы (4 дня), обязательно с возвратом.",
        facts=IntentFacts(brand="Adidas", model="Barricade 13", size_label="41", color="black",
                          needs_refundable=True, deadline_days=4),
        ok_skus=frozenset({"ADI-BARRICADE13-41-BLA-COU"}),
        trap="the request is in Russian; the cheaper listing is final sale",
    ),
    Task(
        id="hard-two-pairs",
        request="Two pairs of Nike Court Lite 4 in white: size 40 for my wife and 43 for me.",
        category="shoes", max_cents=20000, quantity_cap=2,
        persona="One white Nike Court Lite 4 in size 40 and one in size 43. Same order is "
                "fine. No deadline, returns not needed.",
        facts=IntentFacts(brand="Nike", model="Court Lite 4", color="white",
                          lines=({"size_label": "40", "quantity": 1},
                                 {"size_label": "43", "quantity": 1})),
        ok_check=_two_pairs,
        trap="size 40 is out of stock at the cheaper shop, and one order is one merchant",
    ),
    Task(
        id="hard-might-return",
        request="Cheapest Babolat Pure Aero 98 you can find, 4 3/8 grip. I might end up "
                "returning it though.",
        category="racket", max_cents=30000,
        persona="Grip 4 3/8, any colour. Wants the cheapest option that can be returned, "
                "because they may return it.",
        facts=IntentFacts(brand="Babolat", model="Pure Aero 98", size_label="4 3/8",
                          price_preference="cheap", needs_refundable=True),
        ok_check=_one(lambda p: p["family"] == "BAB-PUREAERO98" and p["size_label"] == "4 3/8"
                      and p["merchant_id"] == "m-court"),
        trap="'cheapest' pulls to Racket Outlet, 'might return' rules it out",
    ),
]

TASK_SETS = {"pilot": PILOT, "hard": HARD, "all": PILOT + HARD}
