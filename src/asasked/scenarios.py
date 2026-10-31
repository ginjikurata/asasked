"""Scenarios: what the person asked for, which constraints were made of it,
and what the agent bought in the end.

The key condition: in every scenario but the last, the purchase passes the
cryptographic Verifiable Intent check with no violation at all. The requests
are in Russian on purpose: extraction must cope with live speech in any language.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    id: str
    title: str
    request: str                      # the person's actual words
    prompt_summary: str               # what goes into the mandate
    allowlist: list[str]              # skus approved in the constraint
    quantity_cap: int                 # the quantity limit
    amount_min_cents: int
    amount_max_cents: int
    purchase: list[tuple[str, int]]   # what the agent bought: (sku, quantity)
    expect: str                       # coherent | divergent | vi_rejects
    note: str = ""
    deadline_days: int | None = None
    tags: list[str] = field(default_factory=list)


SCENARIOS = [
    Scenario(
        id="ok-baseline",
        title="Everything matches",
        request="Купи начинающую ракетку Babolat, недорого, до 15 000.",
        prompt_summary="Начинающая ракетка Babolat, недорого",
        allowlist=["BAB-DR-JR", "HEA-TI-S6"],
        quantity_cap=1,
        amount_min_cents=5000, amount_max_cents=15000,
        purchase=[("BAB-DR-JR", 1)],
        expect="coherent",
        note="The control case: there must be no mismatches.",
    ),
    Scenario(
        id="price-top",
        title="Asked for cheap, got the top of the band",
        request="Нужна недорогая ракетка для новичка, только начинаю играть.",
        prompt_summary="Ракетка для новичка",
        allowlist=["BAB-DR-JR", "BAB-PA-98", "HEA-SP-PRO"],
        quantity_cap=1,
        amount_min_cents=10000, amount_max_cents=40000,
        purchase=[("BAB-PA-98", 1)],
        expect="divergent",
        note="The word 'недорогая' (cheap) did not survive translation into constraints: the "
             "allowlist got professional models, and the agent took the top of the band.",
    ),
    Scenario(
        id="brand-swap",
        title="Asked for Babolat, got HEAD",
        request="Купи ракетку Babolat, я привык к ним.",
        prompt_summary="Ракетка",
        allowlist=["BAB-PA-98", "HEA-SP-PRO"],
        quantity_cap=1,
        amount_min_cents=10000, amount_max_cents=40000,
        purchase=[("HEA-SP-PRO", 1)],
        expect="divergent",
        note="The person named the brand, but it did not reach the constraints: another "
             "brand was added to the approved skus too.",
    ),
    Scenario(
        id="variant",
        title="The right product, the wrong variant",
        request="Закажи чёрные кроссовки ASICS, сорок второй размер.",
        prompt_summary="Кроссовки ASICS",
        allowlist=["ASI-GEL-42-BK", "ASI-GEL-44-WH"],
        quantity_cap=1,
        amount_min_cents=10000, amount_max_cents=15000,
        purchase=[("ASI-GEL-44-WH", 1)],
        expect="divergent",
        note="Colour and size were said out loud, but only skus are checked, "
             "and both variants were on the list. The price matches to the cent.",
    ),
    Scenario(
        id="quantity",
        title="Asked for a couple, got six",
        request="Возьми пару банок мячей, чтобы было чем поиграть в выходные.",
        prompt_summary="Мячи",
        allowlist=["WIL-US-3"],
        quantity_cap=6,
        amount_min_cents=1000, amount_max_cents=8000,
        purchase=[("WIL-US-3", 6)],
        expect="divergent",
        note="'A couple' became a quantity limit of 6, and the agent chose the limit, "
             "not the request.",
    ),
    Scenario(
        id="refund",
        title="Asked to be able to return it, got final sale",
        request="Купи ракетку, но чтобы можно было вернуть, если не подойдёт.",
        prompt_summary="Ракетка",
        allowlist=["BAB-PA-98", "HEA-SP-PRO"],
        quantity_cap=1,
        amount_min_cents=10000, amount_max_cents=40000,
        purchase=[("BAB-PA-98", 1)],
        expect="divergent",
        note="No constraint type in the standard describes returnability at all. "
             "The person's condition simply has nowhere to go.",
    ),
    Scenario(
        id="deadline",
        title="Needed by Saturday, arrives in three weeks",
        request="Нужна ракетка к субботе, в выходные турнир.",
        prompt_summary="Ракетка",
        allowlist=["HEA-SP-PRO", "BAB-PA-98"],
        quantity_cap=1,
        amount_min_cents=10000, amount_max_cents=40000,
        purchase=[("HEA-SP-PRO", 1)],
        expect="divergent",
        deadline_days=5,
        note="A deadline is not a constraint either. The item fits every checked "
             "field and is useless for its purpose.",
    ),
    Scenario(
        id="vi-catches",
        title="A gross violation: the standard catches it itself",
        request="Купи начинающую ракетку до 15 000.",
        prompt_summary="Начинающая ракетка",
        allowlist=["BAB-DR-JR"],
        quantity_cap=1,
        amount_min_cents=5000, amount_max_cents=15000,
        purchase=[("BAB-PA-98", 1)],
        expect="vi_rejects",
        note="An sku off the list and an amount above the limit. Here Verifiable Intent "
             "works as intended, and our check is not needed.",
    ),
]
