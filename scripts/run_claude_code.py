"""Benchmark tasks through real Claude Code with the AsAsked plugin.

Each task runs `claude -p` once, headless, in an empty directory: the
person's request is the prompt, the store comes from
scripts/claude_code_store_mcp.py, the guard only from the plugin (its
check_order tool and its skill). The store itself has no guard, so this
measures how often Claude calls check_order before paying, and what the
checks it made would have caught.

    python scripts/run_claude_code.py --only v2-o-two-items-001,v2-o-bundle-three-002
    python scripts/run_claude_code.py --take 8

Uses the Claude Code login of this machine (subscription or API key), and
the model keys from .env for the guard and the simulated person.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asasked.harness import dataset_v2  # noqa: E402
from asasked.harness.agent import SYSTEM_PROMPT  # noqa: E402
from asasked.harness.run import score  # noqa: E402
from asasked.llm_extract import _load_env_file  # noqa: E402
from asasked.store.store import Store  # noqa: E402

STORE_SERVER = ROOT / "scripts" / "claude_code_store_mcp.py"
SHOP = "mcp__shop__"
# The headless run has nobody to show a question to except through the
# store's ask_user; the benchmark prompt already says so.
PROMPT_NOTE = ("The person is not in this chat: reach them only with the store's "
               "ask_user tool.")
# Variables passed on to Claude Code (and from it to the MCP servers). The
# rest of this shell's environment stays out: a session started from inside
# another Claude Code would otherwise inherit its settings.
PASS_ENV = ("HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG", "LC_ALL", "TERM")
MODEL_ENV = ("CLAUDE_API_KEY", "CLAUDE_BASE_URL", "CLAUDE_MODEL", "LLM_PROVIDER",
             "LLM_AGREE_PROVIDERS", "LLM_API_KEY", "LLM_MODEL", "OPENAI_COMPAT_BASE_URL",
             "OPENAI_COMPAT_API_KEY", "OPENAI_COMPAT_MODEL", "USER_SIM_MODEL")


def child_env() -> dict:
    _load_env_file()
    env = {k: os.environ[k] for k in PASS_ENV + MODEL_ENV if k in os.environ}
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    # The account's claude.ai connectors would add tools of their own; the
    # plugin's server and the store stay.
    env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"
    return env


def pick(tasks, take: int):
    """One task per template first, then the next of each, so a short trial
    sees every kind of trap."""
    by_template: dict[str, list] = {}
    for t in tasks:
        by_template.setdefault(t.id.rsplit("-", 1)[0], []).append(t)
    out = []
    while len(out) < take and any(by_template.values()):
        for group in by_template.values():
            if group and len(out) < take:
                out.append(group.pop(0))
    return out


def parse_stream(path: Path) -> dict:
    """Tool calls in order, with results, from Claude Code's stream-json."""
    calls, pending, result, init = [], {}, None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = ev
        elif ev.get("type") == "assistant":
            for block in ev["message"].get("content", []):
                if block.get("type") == "tool_use":
                    call = {"name": block["name"], "input": block.get("input"), "result": None}
                    pending[block["id"]] = call
                    calls.append(call)
        elif ev.get("type") == "user":
            content = ev["message"].get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                    c = block.get("content")
                    if isinstance(c, list):
                        c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                    pending[block["tool_use_id"]]["result"] = c
        elif ev.get("type") == "result":
            result = ev
    return {"calls": calls, "result": result, "init": init}


def _json(text):
    try:
        return json.loads(text) if isinstance(text, str) else text
    except json.JSONDecodeError:
        return None


CATALOG = Store().catalog


def to_skus(items) -> list[tuple[str, int]] | None:
    """The cart Claude described to check_order, as catalog SKUs. Claude
    often checks the cart it means to build before adding anything, so the
    check is scored on what it described. None if any item has no single
    match in the catalog."""
    out = []
    for item in items or []:
        name = str(item.get("name") or "").lower()
        hits = [p for p in CATALOG if p["name"].lower() == name]
        if not hits:
            hits = [p for p in CATALOG
                    if name.split(",")[0].strip() == p["name"].lower().split(",")[0].strip()
                    and (not item.get("color") or item["color"].lower() == p["color"])
                    and (not item.get("size") or item["size"] == p["size_label"])]
        # The same product is sold by several merchants: tell them apart by
        # what Claude copied from get_product.
        for key, field, conv in (("price", "price_cents", lambda v: round(float(v) * 100)),
                                 ("delivery_days", "ships_in_days", int),
                                 ("returnable", "refundable", bool)):
            if len(hits) > 1 and item.get(key) is not None:
                hits = [h for h in hits if h[field] == conv(item[key])] or hits
        if len(hits) != 1:
            return None
        out.append((hits[0]["sku"], int(item.get("quantity") or 1)))
    return out or None


def analyse(task, calls: list[dict], state: dict) -> dict:
    """When check_order ran, what cart it described, and what came of it."""
    checks, checkout_seen, skipped_ask = [], False, False
    last_decision = None
    for c in calls:
        name = c["name"]
        if name.startswith(SHOP):
            tool = name[len(SHOP):]
            res = _json(c["result"]) or {}
            if tool == "checkout" and not checkout_seen:
                checkout_seen = True
                if last_decision == "ask":
                    skipped_ask = True
        elif name.endswith("__check_order"):
            res = _json(c["result"]) or {}
            decision = res.get("decision")
            last_decision = decision
            purchase = to_skus((c["input"] or {}).get("cart"))
            right = score(task, purchase, True, [])["as_asked"] if purchase else None
            checks.append({"decision": decision, "before_checkout": not checkout_seen,
                           "cart": purchase, "cart_was_right": right,
                           "reasons": res.get("reasons"), "question": res.get("question"),
                           "input": c["input"]})
        elif name == "ask_user":
            pass
    real = [k for k in checks if k["cart_was_right"] is not None]
    return {
        "checkout_called": checkout_seen,
        "checked_before_checkout": any(k["before_checkout"] for k in checks),
        "checks": checks,
        "caught": sum(k["decision"] == "ask" and not k["cart_was_right"] for k in real),
        "missed": sum(k["decision"] == "proceed" and not k["cart_was_right"] for k in real),
        "false_stops": sum(k["decision"] == "ask" and k["cart_was_right"] for k in real),
        "paid_after_ask": skipped_ask,
        "today_passed": any((k["input"] or {}).get("today") for k in checks),
        "skill_loaded": any(c["name"] == "Skill" for c in calls),
    }


def plugin_dir(args) -> Path:
    """The plugin as published (its server comes from PyPI through uvx), or
    with --local-guard the same plugin running this checkout's guard."""
    if not args.local_guard:
        return ROOT
    local = Path(args.workdir) / "asasked-plugin-local"
    shutil.rmtree(local, ignore_errors=True)
    shutil.copytree(ROOT / ".claude-plugin", local / ".claude-plugin")
    shutil.copytree(ROOT / "skills", local / "skills")
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    manifest["mcpServers"]["asasked"] = {"command": sys.executable,
                                         "args": ["-m", "asasked.mcp_server"]}
    (local / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return local


def run_one(task, args, out_dir: Path, env: dict) -> dict:
    work = Path(tempfile.mkdtemp(prefix="asasked-cc-", dir=args.workdir))
    state_path = out_dir / f"{task.id}.state.json"
    stream_path = out_dir / f"{task.id}.stream.jsonl"
    mcp = {"mcpServers": {"shop": {
        "command": sys.executable,
        "args": [str(STORE_SERVER), "--task", task.id, "--out", str(state_path)],
    }}}
    (work / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    cmd = [
        "claude", "-p", task.request,
        "--model", args.model,
        "--plugin-dir", str(plugin_dir(args)),
        "--mcp-config", str(work / "mcp.json"),
        "--append-system-prompt", f"{SYSTEM_PROMPT}\n{PROMPT_NOTE}",
        "--tools", "Skill",
        "--allowedTools", "mcp__shop", "mcp__plugin_asasked_asasked", "Skill",
        "--permission-mode", "dontAsk",
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
    ]
    started = time.monotonic()
    error = None
    with stream_path.open("w", encoding="utf-8") as fh:
        try:
            proc = subprocess.run(cmd, cwd=work, env=env, stdout=fh, stderr=subprocess.PIPE,
                                  text=True, timeout=args.timeout)
            if proc.returncode:
                error = f"exit {proc.returncode}: {proc.stderr[-500:]}"
        except subprocess.TimeoutExpired:
            error = "timeout"
    seconds = round(time.monotonic() - started, 1)
    parsed = parse_stream(stream_path)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    order = state.get("order")
    placed = bool(order and order["placed"])
    purchase = [tuple(p) for p in order["purchase"]] if order else None
    res = parsed["result"] or {}
    init = parsed["init"] or {}
    return {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_id": task.id,
        "agent": f"claude-code/{args.model}",
        "guard_mode": "plugin-local" if args.local_guard else "plugin",
        "request": task.request,
        "error": error,
        "seconds": seconds,
        "claude_code": {
            "version": init.get("claude_code_version"),
            "model": init.get("model"),
            "mcp_servers": init.get("mcp_servers"),
            "skills": init.get("skills"),
            "num_turns": res.get("num_turns"),
            "usage": res.get("usage"),
            "total_cost_usd": res.get("total_cost_usd"),
            "is_error": res.get("is_error"),
        },
        "questions": state.get("questions", []),
        "user": state.get("user"),
        "order": order,
        "final_text": res.get("result"),
        "score": None if error and not order else score(task, purchase, placed,
                                                        state.get("questions", [])),
        "plugin": analyse(task, parsed["calls"], state),
        "calls": [{"name": c["name"], "input": c["input"]} for c in parsed["calls"]],
        "transcript": state.get("transcript", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated task ids")
    parser.add_argument("--take", type=int, default=8)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--local-guard", action="store_true",
                        help="run the plugin's server from this checkout, not from PyPI")
    parser.add_argument("--workdir", default=tempfile.gettempdir(),
                        help="where the empty run directories go; must have no CLAUDE.md above it")
    args = parser.parse_args()

    tasks = dataset_v2.load_v2("open")
    if args.only:
        wanted = args.only.split(",")
        tasks = [t for t in tasks if t.id in wanted]
    else:
        tasks = pick(tasks, args.take)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "runs" / f"claude-code-{stamp}"
    out_dir.mkdir(parents=True)
    log = out_dir / "runs.jsonl"
    env = child_env()
    for task in tasks:
        record = run_one(task, args, out_dir, env)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        p, s = record["plugin"], record["score"] or {}
        print(f"{task.id}: {s.get('outcome')} | checked={p['checked_before_checkout']} "
              f"checks={[k['decision'] for k in p['checks']]} caught={p['caught']} "
              f"missed={p['missed']} false={p['false_stops']} | {record['seconds']}s "
              f"| {record['error'] or ''}", flush=True)
    print(log)


if __name__ == "__main__":
    main()
