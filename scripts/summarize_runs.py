"""The README benchmark tables, computed from run logs.

    python scripts/summarize_runs.py data/runs/v1-open-0.1.3.jsonl.gz
    python scripts/summarize_runs.py runs/*.jsonl --markdown

Per agent, guard off -> enforced: purchases as asked, wrong purchases that
VI passed, and runs that bought nothing when something should have been
bought. Then the guard's own checks on the agents' carts: wrong carts it
stopped (caught), wrong carts it let through (missed), right carts it
stopped (false stops). Runs that errored are counted apart, not scored.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path


def load(paths: list[Path]) -> list[dict]:
    records = []
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as f:
            records.extend(json.loads(line) for line in f if line.strip())
    return records


def tally(records: list[dict]) -> dict:
    table = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in records:
        cell = table[r["agent"]][r.get("guard_mode") or "off"]
        if r["score"] is None:
            cell["errors"] += 1
            continue
        cell["runs"] += 1
        outcome = r["score"]["outcome"]
        cell["as_asked"] += outcome == "as_asked"
        cell["wrong"] += outcome == "wrong_purchase"
        cell["stopped_short"] += outcome == "stopped_short"
        guard = r.get("guard")
        if guard:
            cell["checks"] += len(guard["checks"])
            cell["caught"] += guard["caught"]
            cell["missed"] += guard["missed"]
            cell["false_stops"] += guard["false_stops"]
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--markdown", action="store_true", help="print the README table")
    args = parser.parse_args()

    table = tally(load(args.logs))
    order = sorted(table, key=lambda a: (a != "naive", a))
    rows = []
    for agent in order:
        off, on = table[agent]["off"], table[agent]["enforced"]
        rows.append((agent, *(f"{off[k]} → {on[k]}" for k in ("as_asked", "wrong", "stopped_short")),
                     f"{off['errors']} / {on['errors']}"))
    if args.markdown:
        print("| Agent | As asked | Wrong, VI passed | Bought nothing, should have |")
        print("|---|---|---|---|")
        for agent, *cells, _ in rows:
            print(f"| {agent} | " + " | ".join(cells) + " |")
    else:
        print(f"{'agent':<24}{'as asked':<12}{'wrong':<12}{'nothing':<12}errors off / on")
        for row in rows:
            print("".join(f"{c:<12}" if i else f"{c:<24}" for i, c in enumerate(row)))

    for label, agents in (("models'", [a for a in order if a != "naive"]),
                          ("naive agent's", [a for a in order if a == "naive"])):
        if not agents:
            continue
        on = [table[a]["enforced"] for a in agents]
        total = {k: sum(c[k] for c in on) for k in ("checks", "caught", "missed", "false_stops")}
        print(f"\nGuard on the {label} carts: {total['checks']} checks, caught {total['caught']}, "
              f"missed {total['missed']}, stopped {total['false_stops']} right carts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
