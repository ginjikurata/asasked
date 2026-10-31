"""Датасет v1 и формат разметки — без сети."""

import csv

import pytest

from asasked.harness import dataset
from asasked.harness.labels import describe, purchase_matches
from asasked.harness.run import score
from asasked.store.catalog_v1 import BY_SKU

find = BY_SKU.__getitem__
TASKS, _REJECTED = dataset.build()


# ---------------------------------------------------------------------------
# Формат разметки
# ---------------------------------------------------------------------------

TWO = {"lines": [{"where": {"family": "NIK-COURTLITE4", "color": "white", "size_label": "40"},
                  "units": 1},
                 {"where": {"family": "NIK-COURTLITE4", "color": "white", "size_label": "43"},
                  "units": 1}]}


def test_lines_in_any_order_and_no_extras():
    a, b = "NIK-COURTLITE4-40-WHI-ACE", "NIK-COURTLITE4-43-WHI-ACE"
    assert purchase_matches(TWO, [(b, 1), (a, 1)], find)
    assert not purchase_matches(TWO, [(a, 1)], find)
    assert not purchase_matches(TWO, [(a, 1), (b, 1), ("NIK-COURTLITE4-44-WHI-ACE", 1)], find)
    assert not purchase_matches(TWO, [(a, 2), (b, 1)], find)


def test_units_special_keys_and_total():
    cans = {"lines": [{"where": {"family": "PEN-CHAMPIONSHIP"}, "units": 4}]}
    assert purchase_matches(cans, [("PEN-CHAMPIONSHIP-12B-YEL-COU", 1)], find)
    assert purchase_matches(cans, [("PEN-CHAMPIONSHIP-3B-YEL-COU", 4)], find)
    assert not purchase_matches(cans, [("PEN-CHAMPIONSHIP-3B-YEL-COU", 1)], find)
    cheap = {"lines": [{"where": {"category": "racket", "brand_not": ["Wilson"],
                                  "max_price_cents": 10000, "max_ships_in_days": 3}}]}
    assert purchase_matches(cheap, [("HEA-TIS6-438-BLA-COU", 1)], find)
    assert not purchase_matches(cheap, [("HEA-TIS6-438-BLA-BAS", 1)], find)        # 14 дней
    assert not purchase_matches(cheap, [("WIL-ULTRAPOWER-438-BLU-COU", 1)], find)  # Wilson
    capped = {**cans, "max_total_cents": 1000}
    assert not purchase_matches(capped, [("PEN-CHAMPIONSHIP-12B-YEL-COU", 1)], find)


def test_no_purchase_label():
    label = {"no_purchase": True, "should_ask": True}
    assert purchase_matches(label, [], find)
    assert not purchase_matches(label, [("HEA-TIS6-438-BLA-COU", 1)], find)
    assert describe(label) == "buy nothing; should ask first"


# ---------------------------------------------------------------------------
# Датасет
# ---------------------------------------------------------------------------


def test_build_is_deterministic_and_complete():
    again, _ = dataset.build()
    assert again == TASKS
    assert len(TASKS) == 200
    assert len({t["id"] for t in TASKS}) == 200
    splits = [t["split"] for t in TASKS]
    assert 80 <= splits.count("hidden") <= 120


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t["id"])
def test_every_task_is_solvable_and_has_a_trap(task):
    assert dataset.has_trap(task)
    right = task["right_purchase"]
    if task["label"].get("no_purchase"):
        assert right is None
        return
    allowed = {p["sku"] for p in dataset.allowlist(task)}
    assert all(sku in allowed and BY_SKU[sku]["stock"] >= qty for sku, qty in right)
    assert len({BY_SKU[s]["merchant_id"] for s, _ in right}) == 1
    assert sum(BY_SKU[s]["price_cents"] * q for s, q in right) <= task["max_cents"]
    assert purchase_matches(task["label"], right, find)


def test_loaded_tasks_score_the_right_purchase_as_right():
    for row in TASKS:
        task = dataset.to_task(row)
        if row["label"].get("no_purchase"):
            assert task.no_purchase_ok and score(task, None, False, ["?"])["as_asked"]
        else:
            assert score(task, row["right_purchase"], True, [])["as_asked"]


def test_write_puts_each_half_in_its_own_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(dataset, "HIDDEN_DIR", tmp_path / "hidden")
    dataset.write(TASKS)
    assert {r["split"] for r in dataset.rows("open")} == {"open"}
    assert {r["split"] for r in dataset.rows("hidden")} == {"hidden"}
    assert len(dataset.rows()) == len(TASKS)
    (tmp_path / "hidden" / "tasks_v1.jsonl").unlink()  # у постороннего скрытой половины нет
    assert dataset.rows("hidden") == [] and dataset.rows() == dataset.rows("open")


def test_repository_holds_no_hidden_tasks():
    hidden = {t["id"] for t in TASKS if t["split"] == "hidden"}
    for path in dataset.DATA_DIR.iterdir():
        if path.suffix in (".jsonl", ".csv"):
            text = path.read_text(encoding="utf-8")
            assert not [i for i in hidden if i in text], path.name


def test_agreement(tmp_path, capsys):
    from importlib import util
    spec = util.spec_from_file_location("bd", dataset.DATA_DIR.parent / "scripts" / "build_dataset.py")
    bd = util.module_from_spec(spec)
    spec.loader.exec_module(bd)

    def sheet(name, verdicts):
        path = tmp_path / name
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "request", "verdict"])
            w.writeheader()
            for i, v in enumerate(verdicts):
                w.writerow({"id": f"t{i}", "request": "r", "verdict": v})
        return path

    a = sheet("a.csv", ["ok", "ok", "drop", "fix"])
    b = sheet("b.csv", ["ok", "ok", "drop", "ok"])
    assert bd.agreement(a, b) == 0
    out = capsys.readouterr().out
    assert "Совпало: 3 (75%)" in out and "t3" in out


def test_v2_pilot_takes_whole_templates_with_traps():
    from collections import Counter

    from asasked.harness.dataset_v2 import PILOT_TAKE, PILOT_TEMPLATES, build_pilot
    tasks = build_pilot()
    counts = Counter(t["id"].rsplit("-", 1)[0] for t in tasks)
    assert len(counts) == len(PILOT_TEMPLATES)
    assert set(counts.values()) == {PILOT_TAKE}
    assert all(dataset.right_purchase(t) and dataset.has_trap(t) for t in tasks)


def test_v2_pilot2_takes_whole_templates_with_traps():
    from collections import Counter

    from asasked.harness.dataset_v2 import PILOT2_TEMPLATES, PILOT_TAKE, build_pilot2
    tasks = build_pilot2()
    counts = Counter(t["id"].rsplit("-", 1)[0] for t in tasks)
    assert len(counts) == len(PILOT2_TEMPLATES)
    assert set(counts.values()) == {PILOT_TAKE}
    assert all(dataset.right_purchase(t) and dataset.has_trap(t) for t in tasks)


def test_v2_pilot3_takes_whole_templates_with_traps():
    from collections import Counter

    from asasked.harness.dataset_v2 import PILOT3_TEMPLATES, PILOT_TAKE, build_pilot3
    tasks = build_pilot3()
    counts = Counter(t["id"].rsplit("-", 1)[0] for t in tasks)
    assert len(counts) == len(PILOT3_TEMPLATES)
    assert set(counts.values()) == {PILOT_TAKE}
    assert all(dataset.right_purchase(t) and dataset.has_trap(t) for t in tasks)


def test_v2_open_half_is_reproducible_and_disjoint_from_v1():
    import json

    from asasked.harness.dataset_v2 import V2_TEMPLATES, build_v2
    tasks = build_v2(include_hidden=False)
    assert tasks == build_v2(include_hidden=False)
    assert len(tasks) == sum(take for _, _, take in V2_TEMPLATES)
    assert all(dataset.right_purchase(t) and dataset.has_trap(t) for t in tasks)
    v1 = {json.dumps(r["label"], sort_keys=True) for r in dataset.rows("open")}
    answers = [json.dumps(t["label"], sort_keys=True) for t in tasks]
    assert len(set(answers)) == len(answers) and not v1 & set(answers)


def test_v2_open_file_matches_generator():
    import json

    from asasked.harness.dataset_v2 import build_v2
    path = dataset.DATA_DIR / "tasks_v2.jsonl"
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    assert rows == json.loads(json.dumps(build_v2(include_hidden=False), ensure_ascii=False))


def test_v2_hidden_half_avoids_public_pilots(tmp_path, monkeypatch):
    """Скрытая половина на своём (здесь — временном) секретном числе не
    повторяет ответов пилотов: их числа открыты."""
    from asasked.harness import dataset_v2 as v2
    monkeypatch.setattr(dataset, "HIDDEN_DIR", tmp_path)
    hidden = [t for t in v2.build_v2() if t["split"] == "hidden"]
    pilots = v2.build_pilot() + v2.build_pilot2() + v2.build_pilot3()
    assert hidden and not {v2._answer(t) for t in hidden} & {v2._answer(t) for t in pilots}
