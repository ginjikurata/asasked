"""A model rates whether the English requests of dataset v1 sound natural.

    python scripts/check_naturalness.py data/review_v1_cos.csv data/naturalness_v1_model.csv

The labeller checks meaning and the label; a model (CLAUDE_* in .env) checks
whether the English is natural, and it is called exactly that: a model check.
"""
import csv, json, sys, time
from pathlib import Path

from asasked import llm_extract as L  # loads .env
import anthropic

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8")) if r["lang"] == "en"]
done = {}
if OUT.exists():
    done = {r["id"]: r for r in csv.DictReader(OUT.open(encoding="utf-8"))}
todo = [r for r in rows if r["id"] not in done]

SYSTEM = """You review requests that a person types to an AI shopping assistant in a
tennis store. Judge ONE thing: would a real English-speaking shopper plausibly
write this message? Look for robotic or templated phrasing, wrong idioms,
unnatural word order, implausible combinations of details, or text that reads
like a specification rather than a person.

Do not judge whether the request is clear, complete or easy to fulfil: vague or
muddled requests are intentional and can be perfectly natural. Do not judge any
label or correct answer. Product names, sizes like "4 1/2 grip" and prices are
correct as written.

For each item return:
- "natural": "yes" (a real person could write this), "minor" (understandable but
  slightly off), or "no" (no real person would write it like this)
- "note": for minor/no, one short sentence on what is off; empty for yes
- "rewrite": for minor/no, the same request rewritten naturally with exactly the
  same conditions, hedges and vagueness; empty for yes

Return only JSON: {"items": [{"id": ..., "natural": ..., "note": ..., "rewrite": ...}]}"""

client = anthropic.Anthropic(api_key=L.CLAUDE_API_KEY, base_url=L.CLAUDE_BASE_URL,
                             max_retries=4, timeout=120.0)
fields = ["id", "request", "natural", "note", "rewrite"]
B = 20
for i in range(0, len(todo), B):
    batch = todo[i:i + B]
    payload = [{"id": r["id"], "request": r["request"]} for r in batch]
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=L.CLAUDE_MODEL, max_tokens=8000, system=SYSTEM,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            text = next(b.text for b in resp.content if b.type == "text")
            got = {it["id"]: it for it in L._parse_json(text)["items"]}
            assert set(got) == {r["id"] for r in batch}, "ids mismatch"
            assert all(got[r["id"]].get("natural") in ("yes", "minor", "no") for r in batch)
            break
        except Exception as e:  # noqa: BLE001
            print("retry", i, attempt, repr(e)[:200], flush=True)
            time.sleep(3)
    else:
        sys.exit(f"batch {i} failed")
    for r in batch:
        g = got[r["id"]]
        done[r["id"]] = {"id": r["id"], "request": r["request"], "natural": g["natural"],
                         "note": g.get("note", ""), "rewrite": g.get("rewrite", "")}
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            if r["id"] in done:
                w.writerow(done[r["id"]])
    print(f"{len(done)}/{len(rows)}", flush=True)
print("model:", L.CLAUDE_MODEL)
