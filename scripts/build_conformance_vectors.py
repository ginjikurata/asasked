"""Контрольные примеры совместимости для стандарта Verifiable Intent.

Такого набора сегодня не существует у самого стандарта: вторая реализация
не может доказать, что совпадает с первой (issue упоминается в CLAUDE.md).
Этот скрипт закрывает это — но не так, как обычно ожидают "тестовые
векторы".

Почему не статичный файл с застывшими байтами: мандаты L3 в этой версии
стандарта живут 5 минут (exp = iat + 300) — если один раз сериализовать
цепочку и закоммитить, через 5 минут она станет "просроченной" и любая
корректная реализация будет обязана её отклонить. Замороженный вектор
превратился бы в вектор "мы умеем отклонять просрочку", а не в то, что
нужно на самом деле.

Поэтому вектор здесь — не байты, а рецепт + ожидание: этот скрипт берёт
восемь сценариев из scenarios.py (реальная просьба человека → ограничения
→ покупка), строит для каждого настоящую подписанную цепочку VI заново
(ключи детерминированные — helpers.py в самом SDK, не секрет) и записывает
её вместе с тем, каким должен быть ответ валидатора: чейн валиден или нет,
ограничения соблюдены или нет, какие именно нарушения.

Вторая реализация стандарта берёт получившийся JSON, валидирует artifacts
своим кодом и сверяет свой ответ с полем "expected". Совпадение — и есть
доказательство совместимости, которого сегодня нет ни у кого.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from asasked.catalog import find
from asasked.scenarios import SCENARIOS
from asasked.vi_runner import run_vi

OUT_PATH = Path(__file__).resolve().parents[1] / "conformance_vectors.json"


def build_vector(scn) -> dict:
    result = run_vi(scn)
    purchase = [
        {"sku": sku, "name": find(sku)["name"], "quantity": qty}
        for sku, qty in scn.purchase
    ]
    return {
        "id": scn.id,
        "title": scn.title,
        "request": scn.request,
        "prompt_summary": scn.prompt_summary,
        "input": {
            "allowed_merchants": "см. catalog.MERCHANTS (2 продавца, оба разрешены)",
            "allowlist": scn.allowlist,
            "quantity_cap": scn.quantity_cap,
            "amount_min_cents": scn.amount_min_cents,
            "amount_max_cents": scn.amount_max_cents,
            "purchase": purchase,
        },
        "keys": result["keys"],
        "artifacts": result["artifacts"],
        "expected": {
            "chain_valid": result["chain_valid"],
            "chain_errors": result["chain_errors"],
            "constraints_satisfied": result["constraints_ok"],
            "violations": result["violations"],
            "total_cents": result["total_cents"],
        },
    }


def main() -> int:
    vectors = [build_vector(scn) for scn in SCENARIOS]

    doc = {
        "$comment": (
            "Контрольные примеры совместимости для Verifiable Intent v0.1. "
            "Артефакты (artifacts.*) — настоящие подписанные SD-JWT цепочки, "
            "сгенерированные детерминированными демо-ключами из "
            "verifiable-intent/examples/helpers.py (см. keys.*). Мандаты "
            "L3 живут 5 минут от момента генерации (generated_at) — "
            "валидировать сразу после генерации, не хранить как статичный "
            "фикстур. Как использовать: своей реализацией провалидировать "
            "artifacts.layer1/layer2/layer3_payment/layer3_checkout "
            "(layer2_payment_presentation — уже применённое выборочное "
            "раскрытие для платёжной сети) и сверить свой ответ с полем "
            "expected. Совпадение на всех векторах — свидетельство "
            "совместимости с этой реализацией."
        ),
        "generated_at": int(time.time()),
        "valid_for_seconds": 300,
        "vectors": vectors,
    }

    OUT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Записано {len(vectors)} векторов в {OUT_PATH.name}")
    print(f"Действительны {doc['valid_for_seconds']} секунд с момента генерации "
          f"({time.strftime('%H:%M:%S', time.localtime(doc['generated_at']))}).")
    for v in vectors:
        exp = v["expected"]
        print(f"  [{v['id']:<12}] chain_valid={exp['chain_valid']!s:<5} "
              f"constraints_satisfied={exp['constraints_satisfied']!s:<5} "
              f"violations={len(exp['violations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
