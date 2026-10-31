"""Сборка датасета задач v2.

    python scripts/build_dataset_v2.py            # data/tasks_v2.jsonl + скрытая половина
    python scripts/build_dataset_v2.py --open     # только открытая (без секретного числа)

Открытая половина собирается из числа, записанного в коде, скрытая — из
секретного, которое лежит в HIDDEN_DIR/seed_v2.txt и в репозиторий не попадает.
"""

from __future__ import annotations

import argparse
from collections import Counter

from asasked.harness.dataset_v2 import build_v2, write_v2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--open", action="store_true", help="только открытая половина")
    args = parser.parse_args()
    tasks = build_v2(include_hidden=not args.open)
    for path in write_v2(tasks):
        print(path)
    for (split, name), n in sorted(Counter((t["split"], t["template"] + ("-ru" if t["lang"] == "ru"
                                                                         else "")) for t in tasks).items()):
        print(f"  {split:6} {name:22} {n}")


if __name__ == "__main__":
    main()
