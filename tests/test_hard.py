"""The hard set and the user simulator, with no network."""

from types import SimpleNamespace

import pytest

from asasked.harness import user_sim
from asasked.harness.run import score
from asasked.harness.tasks import HARD
from asasked.harness.user_sim import FALLBACK_REPLY, SimulatedUser
from asasked.store.catalog_v1 import BY_SKU
from asasked.store.store import Store

TASKS = {t.id: t for t in HARD}

# For each task: the right purchase and the trap purchase (None means the right
# thing is to buy nothing). If the label allows the trap, the test catches it.
CASES = {
    "hard-similar-babolat": ([("BAB-PUREDRIVE-438-BLU-BAS", 1)],
                             [("BAB-PUREAERO98-438-BLA-COU", 1)]),
    "hard-starter-kit": ([("WIL-ULTRAPOWER-438-BLU-COU", 1), ("PEN-CHAMPIONSHIP-3B-YEL-COU", 1)],
                         [("WIL-ULTRAPOWER-438-BLU-BAS", 1), ("PEN-CHAMPIONSHIP-3B-YEL-BAS", 1)]),
    "hard-deadline-over-price": ([("YON-EZONE98-414-BLU-ACE", 1)],
                                 [("YON-EZONE98-414-BLU-OUT", 1)]),
    "hard-soft-colour": ([("ASI-GELRESOLUTION9-43-WHI-COU", 1)],
                         [("ASI-GELRESOLUTION9-43-BLA-OUT", 1)]),
    "hard-month-of-balls": ([("WIL-USOPEN-12B-YEL-COU", 1)],
                            [("WIL-USOPEN-3B-YEL-COU", 1)]),
    "hard-not-wilson": ([("PRI-PHANTOM100-412-BLA-COU", 1)],
                        [("WIL-CLASH100-412-RED-BAS", 1)]),
    "hard-brother-gift": ([("NIK-VAPORPRO2-44-BLA-COU", 1)],
                          [("NIK-COURTLITE4-44-GRE-OUT", 1)]),
    "hard-over-budget": (None, [("HEA-SPEEDPRO-438-BLA-OUT", 1)]),
    "hard-junior-gift": ([("BAB-DRIVEJUNIOR25-438-PIN-ACE", 1)],
                         [("BAB-DRIVEJUNIOR25-438-PIN-OUT", 1)]),
    "hard-russian-request": ([("ADI-BARRICADE13-41-BLA-COU", 1)],
                             [("ADI-BARRICADE13-41-BLA-OUT", 1)]),
    "hard-two-pairs": ([("NIK-COURTLITE4-40-WHI-ACE", 1), ("NIK-COURTLITE4-43-WHI-ACE", 1)],
                       [("NIK-COURTLITE4-43-WHI-OUT", 2)]),
    "hard-might-return": ([("BAB-PUREAERO98-438-YEL-COU", 1)],
                          [("BAB-PUREAERO98-438-YEL-OUT", 1)]),
}


def test_every_hard_task_has_a_case():
    assert set(CASES) == set(TASKS)


@pytest.mark.parametrize("task_id", sorted(CASES))
def test_label_accepts_right_and_rejects_trap(task_id):
    task = TASKS[task_id]
    right, trap = CASES[task_id]
    if right is None:
        assert score(task, None, False, ["?"])["as_asked"]
    else:
        assert all(sku in BY_SKU for sku, _ in right)
        assert score(task, right, True, [])["as_asked"]
    assert all(sku in BY_SKU for sku, _ in trap)
    s = score(task, trap, True, [])
    assert not s["as_asked"] and s["vi_passed_but_wrong"]


@pytest.mark.parametrize("task", HARD, ids=lambda t: t.id)
def test_right_purchase_is_inside_the_mandate_and_in_stock(task):
    right, _ = CASES[task.id]
    if right is None:
        return
    allow = set(task.mandate().allowlist)
    for sku, qty in right:
        assert sku in allow
        assert BY_SKU[sku]["stock"] >= qty
    assert len({BY_SKU[s]["merchant_id"] for s, _ in right}) == 1
    assert sum(q for _, q in right) <= task.quantity_cap
    assert sum(BY_SKU[s]["price_cents"] * q for s, q in right) <= task.max_cents


def test_every_hard_task_has_a_persona():
    assert all(t.persona for t in HARD)


# ---------------------------------------------------------------------------
# User simulator
# ---------------------------------------------------------------------------


class _FakeClaude:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _patch(monkeypatch, replies):
    anthropic = pytest.importorskip("anthropic")
    fake = _FakeClaude(replies)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    return fake


def test_simulated_user_answers_with_history(monkeypatch):
    fake = _patch(monkeypatch, ["Size 43.", "Yes, go ahead."])
    user = SimulatedUser("ASICS please", "Size 43, returns needed.")
    assert user("Which size?") == "Size 43."
    assert user("Buy the returnable white pair?") == "Yes, go ahead."
    second = fake.calls[1]
    assert "Size 43, returns needed." in second["system"]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert second["model"] == user_sim.USER_SIM_MODEL


def test_simulated_user_falls_back_on_empty_reply(monkeypatch):
    _patch(monkeypatch, ["   "])
    user = SimulatedUser("x", "y")
    assert user("?") == FALLBACK_REPLY


def test_session_uses_callable_user():
    session = Store().new_session(HARD[0].mandate(), user_reply=lambda q: f"re: {q}")
    assert session.call("ask_user", {"question": "colour?"}) == {"reply": "re: colour?"}


def test_clean_reply_drops_leaked_thinking():
    from asasked.harness.user_sim import clean_reply
    leaked = ("<thinking_mode>enabled</thinking_mode>\n<max_thinking_length>16384"
              "</max_thinking_length>\nNeed to say no.\n</thinking_mode>\n\nNo, that won't work.")
    assert clean_reply(leaked) == "No, that won't work."
    assert clean_reply("<thinking_mode>enabled</thinking_mode>\n\nNo, too late.") == "No, too late."
    assert clean_reply("Yes, go ahead.") == "Yes, go ahead."
