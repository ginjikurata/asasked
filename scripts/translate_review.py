"""Перевод просьбы, личности и ловушки задач v1 на русский — для разметчика.

    python scripts/translate_review.py data/review_v1_cos.csv data/review_v1_translation_ru.csv

Переводит модель (CLAUDE_* в .env), поэтому перевод — подсказка, а не
источник истины: в таблице разметки рядом лежит оригинал. Метку модель не
трогает, её переводит кодом build_review_xlsx.py. Готовые строки повторно
не переводятся, прерванный прогон можно продолжить.
"""
import csv, json, sys, time
from pathlib import Path

from asasked import llm_extract as L  # подхватывает .env
import anthropic

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
done = {}
if OUT.exists():
    done = {r["id"]: r for r in csv.DictReader(OUT.open(encoding="utf-8"))}
todo = [r for r in rows if r["id"] not in done]

SYSTEM = """You translate shopping tasks from English into Russian for a human reviewer
who will check, from your translation, whether each task's label is right.

Fidelity matters more than style:
- Keep every condition, hedge, vagueness and ambiguity exactly as strong as in
  the original. If the English is vague, the Russian must be equally vague. Do not
  clarify, add or drop anything.
- Keep brand and model names, sizes, grip sizes, prices with $, merchant names
  (Racket Outlet, Baseline Sports, ...) and numbers exactly as written.
- Natural spoken Russian for "request", plain Russian for "persona" and "trap".

Return only JSON: {"items": [{"id": ..., "request_ru": ..., "persona_ru": ..., "trap_ru": ...}]}
with one item per input, same ids."""

client = anthropic.Anthropic(api_key=L.CLAUDE_API_KEY, base_url=L.CLAUDE_BASE_URL,
                             max_retries=4, timeout=120.0)
fields = ["id", "request_ru", "persona_ru", "trap_ru"]
B = 15
for i in range(0, len(todo), B):
    batch = todo[i:i + B]
    payload = [{k: r[k] for k in ("id", "request", "persona", "trap")} for r in batch]
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=L.CLAUDE_MODEL, max_tokens=8000, system=SYSTEM,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            text = next(b.text for b in resp.content if b.type == "text")
            items = L._parse_json(text)["items"]
            got = {it["id"]: it for it in items}
            assert set(got) == {r["id"] for r in batch}, "ids mismatch"
            assert all(got[r["id"]].get(f, "").strip() for r in batch for f in fields[1:])
            break
        except Exception as e:  # noqa: BLE001
            print("retry", i, attempt, repr(e)[:200], flush=True)
            time.sleep(3)
    else:
        sys.exit(f"batch {i} failed")
    done.update({k: {f: got[k][f] for f in fields} for k in got})
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            if r["id"] in done:
                w.writerow(done[r["id"]])
    print(f"{len(done)}/{len(rows)}", flush=True)
print("model:", L.CLAUDE_MODEL)
