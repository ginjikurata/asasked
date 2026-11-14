"""Run agents paying the sandbox store in crypto, with and without the guard.

    python scripts/run_crypto_agents.py --dry --guard-facts label
    python scripts/run_crypto_agents.py --agents claude-sonnet-5,gpt-6-sol,deepseek-v4-pro

60 tasks (asasked.harness.crypto_run): 10 purchases x control, redirect,
overpay, token, control_sol, slippage. Each runs in two arms, off and guarded.
--dry replaces the model with a scripted agent that obeys every seller note
(no model, no cost): a check of the harness and the guard's wiring.

Every run is a line in runs/crypto-<time>.jsonl. A summary by agent, arm and
kind at the end.
"""

from __future__ import annotations

import argparse
import gzip
import json
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from asasked.harness import crypto_run
from asasked.harness.agent import AGENTS, AgentSpec, parse_agent

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"
MARK = {"as_asked": "AS ASKED", "wrong_payment": "WRONG PAYMENT",
        "stopped_short": "stopped short"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agents", default="claude-sonnet-5,gpt-6-sol,deepseek-v4-pro",
                        help=f"comma-separated: {', '.join(AGENTS)} or provider:model")
    parser.add_argument("--arms", default="off,guarded", help="comma-separated: off, guarded (default: both)")
    parser.add_argument("--kinds", default=",".join(crypto_run.KINDS))
    parser.add_argument("--only", help="comma-separated task ids")
    parser.add_argument("--guard-facts", choices=("model", "label"), default="model",
                        help="model - the guard extracts the request's facts; label - the task's")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--dry", action="store_true",
                        help="a scripted agent that obeys every note, no model")
    parser.add_argument("--rerun-errors", metavar="LOG[,LOG]",
                        help="run again only the runs that ended in an error in these logs "
                             "(proxy-swallowed tool calls included)")
    parser.add_argument("--summary", metavar="LOG[,LOG]",
                        help="no runs: the summary of these logs; a later log's run "
                             "replaces an earlier one with the same agent, task and arm")
    args = parser.parse_args()

    if args.summary:
        print(summary(merged([Path(x) for x in args.summary.split(",")])))
        return 0

    if args.dry:
        agents = [AgentSpec("obedient-script", "none", "none")]
    else:
        agents = [parse_agent(a.strip()) for a in args.agents.split(",") if a.strip()]
    arms = [a for a in args.arms.split(",") if a]
    kinds = set(args.kinds.split(","))
    tasks = [t for t in crypto_run.build_tasks() if t.kind in kinds]
    if args.only:
        wanted = set(args.only.split(","))
        tasks = [t for t in tasks if t.id in wanted]

    if args.rerun_errors:
        failed = {(r["agent"], r["task_id"], r["arm"])
                  for r in merged([Path(x) for x in args.rerun_errors.split(",")])
                  if r["score"] is None}
        by_name = {a.name: a for a in agents}
        jobs_wanted = [(by_name[a], t, arm) for t in tasks for (a, tid, arm) in sorted(failed)
                       if tid == t.id and a in by_name]
    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"crypto-{'dry-' if args.dry else ''}{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    jobs = jobs_wanted if args.rerun_errors else \
        [(a, t, arm) for a in agents for t in tasks for arm in arms]
    print(f"Tasks: {len(tasks)}, agents: {len(agents)}, arms: {arms} -> {len(jobs)} runs, "
          f"{out}", flush=True)

    def one(agent, task, arm):
        try:
            return crypto_run.run_crypto_task(
                agent, task, arm, guard_facts=args.guard_facts,
                agent_fn=crypto_run.obedient_agent if args.dry else None)
        except Exception:  # noqa: BLE001 - one failed run must not bring down the rest
            return {"agent": agent.name, "task_id": task.id, "kind": task.kind, "arm": arm,
                    "score": None, "steps": 0, "questions": [], "seconds": 0,
                    "stop": "error", "error": traceback.format_exc(limit=3)}

    records = []
    with out.open("w", encoding="utf-8") as f, \
            ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(one, *job) for job in jobs]
        for done, future in enumerate(as_completed(futures), 1):
            rec = future.result()
            records.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            s = rec["score"]
            if s is None:
                mark = "ERROR " + (rec.get("error") or "").strip().splitlines()[-1][:80] \
                    if rec.get("error") else "ERROR"
            else:
                mark = MARK[s["outcome"]] + (" HIJACKED" if s["attack_succeeded"] else "")
            g = rec.get("guard")
            gtext = f" refused={g['refused']} asked={g['asked']}" if g else ""
            print(f"  [{done}/{len(jobs)}] {rec['agent']:<18} {rec['arm']:<8} "
                  f"{rec['task_id']:<16} {mark:<24} steps={rec['steps']:<3} "
                  f"questions={len(rec['questions'])}{gtext} ({rec['seconds']}s)", flush=True)

    print("\n" + summary(records), flush=True)
    print(f"\nLog: {out}", flush=True)
    return 0


def merged(logs: list[Path]) -> list[dict]:
    """Records of several logs; a later run of the same agent, task and arm wins."""
    runs = {}
    for log in logs:
        text = (gzip.decompress(log.read_bytes()).decode("utf-8") if log.suffix == ".gz"
                else log.read_text(encoding="utf-8"))
        for line in text.splitlines():
            if line.strip():
                r = json.loads(line)
                crypto_run.mark_proxy_failure(r)   # older logs: same rule as new runs
                runs[(r["agent"], r["task_id"], r["arm"])] = r
    return list(runs.values())


def summary(records: list[dict]) -> str:
    lines = ["Summary (as asked / wrong payment / stopped short / attack succeeded; errors)"]
    groups = defaultdict(list)
    for r in records:
        groups[(r["agent"], r["arm"])].append(r)
    for (agent, arm), rs in sorted(groups.items()):
        lines.append(f"  {agent} [{arm}]")
        for kind in crypto_run.KINDS:
            ks = [r for r in rs if r["kind"] == kind]
            if not ks:
                continue
            scored = [r["score"] for r in ks if r["score"] is not None]
            hijacked = sum(bool(s["attack_succeeded"]) for s in scored)
            att = f"  attack {hijacked}/{len(scored)}" if kind not in (
                "control", "control_sol") else ""
            lines.append(
                f"    {kind:<12} as asked {sum(s['as_asked'] for s in scored)}/{len(scored)}  "
                f"wrong {sum(s['outcome'] == 'wrong_payment' for s in scored)}  "
                f"short {sum(s['outcome'] == 'stopped_short' for s in scored)}{att}  "
                f"errors {len(ks) - len(scored)}"
                + (f"  lost ${sum(s['thief_usd'] + s['overpaid_usd'] for s in scored):,.2f}"
                   f" +swap ${sum(s['swap_lost_usd'] for s in scored):,.2f}" if scored else ""))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
