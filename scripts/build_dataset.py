"""Сборка датасета задач v1 и таблиц для разметчиков.

    python scripts/build_dataset.py                      # data/tasks_v1.jsonl + таблицы
    python scripts/build_dataset.py --agreement a.csv b.csv

Генератор предлагает задачи и метки; решает человек. Разметчик получает
таблицу (data/review_v1_<имя>.csv; скрытая половина — в такой же таблице
в HIDDEN_DIR, вне репозитория) и для каждой задачи ставит в колонке verdict:

    ok        — формулировка естественная, метка верная;
    fix       — задача годится, но метку или текст надо поправить (в comment — что);
    drop      — задачу выбросить (в comment — почему).

Датасет v1 размечает один человек, поэтому согласие разметчиков для него
не считается. Если появится второй, независимый разметчик (своя таблица,
в чужую не смотрит), --agreement посчитает согласие и выведет задачи, где
мнения разошлись, — их разбирают вместе.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from asasked.harness.dataset import DATASET_VERSION, build, dir_of, write
from asasked.harness.labels import describe

FIELDS = ["id", "split", "template", "lang", "request", "persona", "label", "right_purchase",
          "trap", "verdict", "comment"]


def write_review(tasks, who: str) -> list[Path]:
    paths = []
    for split in ("open", "hidden"):
        path = dir_of(split) / f"review_{DATASET_VERSION}_{who}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for t in tasks:
                if t["split"] != split:
                    continue
                w.writerow({
                    "id": t["id"], "split": t["split"], "template": t["template"],
                    "lang": t["lang"], "request": t["request"], "persona": t["persona"],
                    "label": describe(t["label"]),
                    "right_purchase": "; ".join(f"{s} ×{q}" for s, q in t["right_purchase"] or []),
                    "trap": t["trap"], "verdict": "", "comment": "",
                })
        paths.append(path)
    return paths


def agreement(path_a: Path, path_b: Path) -> int:
    def read(p):
        with p.open(encoding="utf-8") as f:
            return {r["id"]: r for r in csv.DictReader(f)}

    a, b = read(path_a), read(path_b)
    ids = sorted(set(a) & set(b))
    pairs = [(a[i]["verdict"].strip().lower(), b[i]["verdict"].strip().lower()) for i in ids]
    filled = [(x, y) for x, y in pairs if x and y]
    if not filled:
        print("Ни одной задачи не размечено обоими.")
        return 1
    agree = sum(x == y for x, y in filled)
    # каппа Коэна: согласие сверх случайного
    n = len(filled)
    ca, cb = Counter(x for x, _ in filled), Counter(y for _, y in filled)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    kappa = (agree / n - expected) / (1 - expected) if expected < 1 else 1.0
    print(f"Размечено обоими: {n} из {len(ids)}. Совпало: {agree} ({agree / n:.0%}). "
          f"Каппа Коэна: {kappa:.2f}.")
    print("Итог по двум разметчикам:", dict(Counter(x for x, y in filled if x == y)))
    disputes = [i for i, (x, y) in zip(ids, pairs) if x and y and x != y]
    if disputes:
        print(f"\nРазошлись ({len(disputes)}) — разобрать вместе:")
        for i in disputes:
            print(f"  {i}: {a[i]['verdict']} / {b[i]['verdict']} — {a[i]['request'][:70]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agreement", nargs=2, type=Path, metavar=("A.csv", "B.csv"))
    parser.add_argument("--annotators", default="cos",
                        help="имена разметчиков для таблиц, через запятую")
    args = parser.parse_args()
    if args.agreement:
        return agreement(*args.agreement)

    tasks, rejected = build()
    paths = write(tasks)
    print(f"Задач: {len(tasks)} →", ", ".join(map(str, paths)))
    print("По шаблонам:", dict(Counter(t["template"] + ("-ru" if t["lang"] == "ru" else "")
                                       for t in tasks)))
    print("Открытых / скрытых:", dict(Counter(t["split"] for t in tasks)))
    if rejected:
        print("Отброшено кандидатов:", dict(Counter(rejected)))
    for who in args.annotators.split(","):
        print("Таблицы для разметчика:", ", ".join(map(str, write_review(tasks, who.strip()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
