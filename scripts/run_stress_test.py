"""Прогон живых формулировок через extract_intent.

Для фраз с expect — автоматическая сверка по названным полям.
Для фраз без expect — печатаем сырой результат, сверяем глазами: там,
где у просьбы нет единственно верного ответа, автоматическая проверка
только создала бы иллюзию точности.

    python scripts/run_stress_test.py --lang en --provider anthropic
    python scripts/run_stress_test.py --provider both   # сверка двух моделей
"""

from __future__ import annotations

import argparse
import time

from asasked.coherence import extract_intent, extract_intent_agreed
from asasked.llm_extract import DEFAULT_PROVIDER, PROVIDERS, ExtractionError
from asasked.stress_phrases import CASES
from asasked.stress_phrases_en import CASES_EN

SETS = {"ru": CASES, "en": CASES_EN, "all": CASES + CASES_EN}

G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", choices=SETS, default="all")
    parser.add_argument("--provider", choices=(*PROVIDERS, "both"), default=DEFAULT_PROVIDER)
    args = parser.parse_args()
    cases = SETS[args.lang]

    def extract(phrase):
        if args.provider == "both":
            return extract_intent_agreed(phrase, deadline_days=None)
        return extract_intent(phrase, deadline_days=None, provider=args.provider)

    print(f"{D}Набор: {args.lang}, фраз: {len(cases)}, провайдер: {args.provider}{X}")
    errors = []
    disputed = []
    checked_pass = []
    checked_fail = []
    review_only = []

    for i, case in enumerate(cases):
        if i > 0:
            time.sleep(1.5)
        print(f"\n{B}[{case.id}]{X} {D}{case.category}{X}")
        print(f'  «{case.phrase}»')

        try:
            facts = extract(case.phrase)
        except ExtractionError as e:
            print(f"  {R}ExtractionError:{X} {e}")
            errors.append((case, str(e)))
            continue

        if facts.disputed:
            print(f"  {Y}модели разошлись:{X} {', '.join(sorted(facts.disputed))}")
            disputed.append((case, facts))

        mismatches = []
        for key, expected_val in (case.expect or {}).items():
            actual_val = getattr(facts, key)
            norm_actual = actual_val.lower() if isinstance(actual_val, str) else actual_val
            norm_expected = expected_val.lower() if isinstance(expected_val, str) else expected_val
            if norm_actual != norm_expected:
                mismatches.append((key, expected_val, actual_val))

        missing_soft = sorted(case.expect_soft - facts.soft)
        if missing_soft:
            mismatches.append(("soft_fields", sorted(case.expect_soft), sorted(facts.soft)))

        if case.expect is None and not case.expect_soft:
            print(f"  {D}(без автосверки — читаем глазами){X}")
            print(f"  {facts}")
            review_only.append((case, facts))
            if case.note:
                print(f"  {D}{case.note}{X}")
            continue

        if mismatches:
            print(f"  {R}расхождение:{X}")
            for key, exp, act in mismatches:
                print(f"    {key}: ожидали {exp!r}, получили {act!r}")
            checked_fail.append((case, facts, mismatches))
        else:
            checked_keys = list(case.expect or {}) + (["soft:" + ",".join(sorted(case.expect_soft))] if case.expect_soft else [])
            print(f"  {G}совпало{X} ({', '.join(checked_keys)})")
            checked_pass.append((case, facts))

        if case.note:
            print(f"  {D}{case.note}{X}")

    total = len(cases)
    print(f"\n{B}{'=' * 78}{X}")
    print(f"{B}Итог:{X} всего {total}, "
          f"{G}прошли проверку{X} {len(checked_pass)}, "
          f"{R}разошлись с ожиданием{X} {len(checked_fail)}, "
          f"{R}ExtractionError{X} {len(errors)}, "
          f"{D}без автосверки (на ручной разбор){X} {len(review_only)}")
    if args.provider == "both":
        print(f"{Y}Модели разошлись хотя бы в одном поле:{X} {len(disputed)} из {total}")

    if checked_fail:
        print(f"\n{B}Разошлись с ожиданием:{X}")
        for case, facts, mismatches in checked_fail:
            print(f"  [{case.id}] {', '.join(f'{k}: {exp!r}!={act!r}' for k, exp, act in mismatches)}")

    if errors:
        print(f"\n{B}Упали с ExtractionError:{X}")
        for case, err in errors:
            print(f"  [{case.id}] {err}")

    return 0 if not checked_fail and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
