"""The reply set (stress_replies.py) is well formed: no model is called here."""

from asasked.guard import ASK, PROCEED
from asasked.harness import dataset_v3
from asasked.harness.hijacked import _BY_SKU, plan, right_sku
from asasked.stress_replies import CASES

CARTS = {"attack", "right", "right2"}


def test_every_case_names_a_v3_task_and_known_carts():
    tasks = {t.id: t for t in dataset_v3.load()}
    assert len(CASES) == 38
    for case in CASES:
        assert case.task in tasks, case
        assert case.lang in {"en", "ru", "es"}, case
        assert case.reply.strip(), case
        assert case.expect and set(case.expect) <= CARTS, case
        assert set(case.expect.values()) <= {ASK, PROCEED}, case


def test_the_carts_exist_in_the_catalog():
    tasks = {t.id: t for t in dataset_v3.load()}
    for task_id in {case.task for case in CASES}:
        task = tasks[task_id]
        attack = plan(task)
        assert attack and all(sku in _BY_SKU for sku, _ in attack), task_id
        assert right_sku(task) in _BY_SKU, task_id


def test_a_refusal_never_expects_the_attackers_cart_to_pass_alone():
    # A case that sends the agent to the right item must also expect the attack to stop.
    for case in CASES:
        if "right" in case.expect or "right2" in case.expect:
            assert case.expect.get("attack") == ASK, case
