"""Build task dataset v2.

    python scripts/build_dataset_v2.py            # data/tasks_v2.jsonl + the hidden half
    python scripts/build_dataset_v2.py --open     # the open half only (no secret number)

The open half is built from a number written in the code, the hidden one from
a secret number that lives in HIDDEN_DIR/seed_v2.txt and never enters the repository.
"""

from __future__ import annotations

import argparse
from collections import Counter

from asasked.harness.dataset_v2 import build_v2, write_v2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--open", action="store_true", help="the open half only")
    args = parser.parse_args()
    tasks = build_v2(include_hidden=not args.open)
    for path in write_v2(tasks):
        print(path)
    for (split, name), n in sorted(Counter((t["split"], t["template"] + ("-ru" if t["lang"] == "ru"
                                                                         else "")) for t in tasks).items()):
        print(f"  {split:6} {name:22} {n}")


if __name__ == "__main__":
    main()
