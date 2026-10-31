"""Build task dataset v1 and the labellers' tables.

    python scripts/build_dataset.py                      # data/tasks_v1.jsonl + tables
    python scripts/build_dataset.py --agreement a.csv b.csv

The generator proposes tasks and labels; a person decides. A labeller gets a
table (data/review_v1_<name>.csv; the hidden half is in the same kind of table
in HIDDEN_DIR, outside the repository) and for every task fills the verdict
column:

    ok        - the wording is natural, the label is right;
    fix       - the task is usable, but the label or text needs fixing (what, in comment);
    drop      - drop the task (why, in comment).

Dataset v1 is labelled by one person, so labeller agreement is not computed
for it. If a second, independent labeller appears (their own table, not
looking at the other one), --agreement computes agreement and prints the
tasks where they disagree, to be resolved together.
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
        print("No task is labelled by both.")
        return 1
    agree = sum(x == y for x, y in filled)
    # Cohen's kappa: agreement beyond chance
    n = len(filled)
    ca, cb = Counter(x for x, _ in filled), Counter(y for _, y in filled)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    kappa = (agree / n - expected) / (1 - expected) if expected < 1 else 1.0
    print(f"Labelled by both: {n} of {len(ids)}. Agreed: {agree} ({agree / n:.0%}). "
          f"Cohen's kappa: {kappa:.2f}.")
    print("Result over both labellers:", dict(Counter(x for x, y in filled if x == y)))
    disputes = [i for i, (x, y) in zip(ids, pairs) if x and y and x != y]
    if disputes:
        print(f"\nDisagreed ({len(disputes)}), resolve together:")
        for i in disputes:
            print(f"  {i}: {a[i]['verdict']} / {b[i]['verdict']} — {a[i]['request'][:70]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agreement", nargs=2, type=Path, metavar=("A.csv", "B.csv"))
    parser.add_argument("--annotators", default="cos",
                        help="labeller names for the tables, comma-separated")
    args = parser.parse_args()
    if args.agreement:
        return agreement(*args.agreement)

    tasks, rejected = build()
    paths = write(tasks)
    print(f"Tasks: {len(tasks)} ->", ", ".join(map(str, paths)))
    print("By template:", dict(Counter(t["template"] + ("-ru" if t["lang"] == "ru" else "")
                                       for t in tasks)))
    print("Open / hidden:", dict(Counter(t["split"] for t in tasks)))
    if rejected:
        print("Rejected candidates:", dict(Counter(rejected)))
    for who in args.annotators.split(","):
        print("Tables for the labeller:", ", ".join(map(str, write_review(tasks, who.strip()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
