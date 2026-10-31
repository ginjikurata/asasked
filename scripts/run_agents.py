"""Run agents on tasks in the sandbox store.

    python scripts/run_agents.py --agents claude-sonnet-5,gpt-6-sol
    python scripts/run_agents.py --agents openai_compat:qwen/qwen3.8-max --tasks pilot

Every run is a line in runs/<time>.jsonl with the full record of calls.
A summary by agent at the end.
"""

from __future__ import annotations

import argparse
import json
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from asasked.harness import dataset, dataset_v2
from asasked.harness.agent import AGENTS, parse_agent
from asasked.harness.run import run_task
from asasked.harness.tasks import TASK_SETS
from asasked.store.store import Store

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agents", default="claude-sonnet-5,gpt-6-sol,deepseek-v4-pro",
                        help=f"comma-separated: {', '.join(AGENTS)} or provider:model")
    parser.add_argument("--tasks", choices=[*TASK_SETS, "v1", "v1-open", "v1-hidden", "v2-pilot", "v2-pilot2", "v2-pilot3", "v2", "v2-open", "v2-hidden"],
                        default="pilot", help="v1* - the dataset from data/tasks_v1.jsonl; v2-pilot - the v2 template pilot")
    parser.add_argument("--only", help="comma-separated task ids")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--guard", choices=("off", "advisory", "enforced", "both"),
                        default="off", help="the guard before payment; both = off and enforced")
    parser.add_argument("--guard-facts", choices=("model", "label"), default="model",
                        help="model - the guard extracts facts itself; label - from the label")
    parser.add_argument("--parallel", type=int, default=4,
                        help="how many runs go at once (the proxy is slow)")
    args = parser.parse_args()

    agents = [parse_agent(a.strip()) for a in args.agents.split(",") if a.strip()]
    if args.tasks.startswith("v1"):
        split = args.tasks.partition("-")[2] or None
        tasks = dataset.load(split)
        if not tasks:
            where = dataset.dir_of(split or "open") / "tasks_v1.jsonl"
            parser.error(f"no {where}; run scripts/build_dataset.py first"
                         + (" (the hidden half lives outside the repository: ASASKED_HIDDEN_DIR)"
                            if split == "hidden" else ""))
        if split is None and not any(t.id for t in dataset.load("hidden")):
            print(f"Note: no hidden half ({dataset.HIDDEN_DIR}), the open one only.",
                  flush=True)
    elif args.tasks == "v2-pilot":
        tasks = dataset_v2.load_pilot()
    elif args.tasks == "v2-pilot2":
        tasks = dataset_v2.load_pilot2()
    elif args.tasks == "v2-pilot3":
        tasks = dataset_v2.load_pilot3()
    elif args.tasks.startswith("v2"):
        split = args.tasks.partition("-")[2] or None
        tasks = dataset_v2.load_v2(split)
        if not tasks:
            parser.error("no tasks_v2.jsonl; run scripts/build_dataset_v2.py first")
    else:
        tasks = TASK_SETS[args.tasks]
    if args.only:
        wanted = set(args.only.split(","))
        tasks = [t for t in tasks if t.id in wanted]

    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    print(f"Tasks: {len(tasks)}, agents: {len(agents)}, repeats: {args.repeats} -> {out}",
          flush=True)

    modes = ("off", "enforced") if args.guard == "both" else (args.guard,)
    jobs = [(agent, task, mode) for agent in agents for task in tasks for mode in modes
            for _ in range(args.repeats)]
    records = []

    def one(agent, task, mode):
        # Every run has its own store: sessions share no state.
        try:
            return run_task(agent, task, Store(), guard_mode=mode, guard_facts=args.guard_facts)
        except Exception:  # noqa: BLE001 - one failed run must not bring down the rest
            return {"agent": agent.name, "task_id": task.id, "guard_mode": mode,
                    "score": None, "steps": 0,
                    "questions": [], "order": None, "seconds": 0, "stop": "error",
                    "error": traceback.format_exc(limit=3)}

    with out.open("w", encoding="utf-8") as f, \
            ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(one, agent, task, mode) for agent, task, mode in jobs]
        for done, future in enumerate(as_completed(futures), 1):
            rec = future.result()
            records.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            s = rec["score"]
            mark = ("ERROR " + rec["error"].strip().splitlines()[-1][:80]) if s is None else {
                "as_asked": "AS ASKED", "wrong_purchase": "WRONG (VI passed)",
                "stopped_short": "stopped short"}[s["outcome"]]
            bought = rec["order"]["purchase"] if rec["order"] and rec["order"]["placed"] else "—"
            guard = f"guard={rec['guard_mode']:<8} " if args.guard != "off" else ""
            print(f"  [{done}/{len(jobs)}] {rec['agent']:<18} {guard}{rec['task_id']:<26} {mark:<18} "
                  f"steps={rec['steps']:<3} asked={len(rec['questions'])} bought={bought} "
                  f"({rec['seconds']}s)", flush=True)

    print("\nSummary", flush=True)
    by_agent = defaultdict(list)
    for r in records:
        key = r["agent"] if args.guard == "off" else f"{r['agent']} [{r.get('guard_mode')}]"
        by_agent[key].append(r)
    for name, rs in sorted(by_agent.items()):
        scored = [r for r in rs if r["score"] is not None]
        n = len(scored)
        if not n:
            print(f"  {name}: every run failed", flush=True)
            continue
        ok = sum(r["score"]["as_asked"] for r in scored)
        gap = sum(r["score"]["vi_passed_but_wrong"] for r in scored)
        short = sum(r["score"]["outcome"] == "stopped_short" for r in scored)
        engine = [r["engine"]["agrees_with_label"] for r in scored if "engine" in r]
        print(f"  {name:<22} AsAsked {ok}/{n}   VI passed but wrong {gap}/{n}   "
              f"stopped short {short}/{n}   errors {len(rs) - n}   "
              f"engine agrees {sum(engine)}/{len(engine)}", flush=True)
        guarded = [r["guard"] for r in scored if r.get("guard")]
        if guarded:
            print(f"  {'':<22} guard: caught {sum(g['caught'] for g in guarded)}, "
                  f"missed {sum(g['missed'] for g in guarded)}, "
                  f"false stops {sum(g['false_stops'] for g in guarded)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
