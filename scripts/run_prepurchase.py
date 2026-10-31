"""Демонстрация режима «до покупки».

Та же сверка (check_coherence), что и в run.py — только вызывается на
этапе «агент вот-вот нажмёт купить», а не «уже купил». BLOCK-находки
останавливают агента и требуют подтверждения человека; WARN — не
останавливают, но остаются видны.

Использует те же 8 сценариев из scenarios.py: там, где run.py показывает
дыру постфактум («криптография довольна, человек — нет»), здесь показываем,
что случилось бы, если агент спросил бы до, а не после.
"""

from __future__ import annotations

from asasked.coherence import ASK, decide_before_purchase, extract_intent
from asasked.scenarios import SCENARIOS

G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"


def line(ch="─", n=78):
    print(D + ch * n + X)


def show(title: str, request: str, decision) -> None:
    print()
    line("═")
    print(f"{B}{title}{X}")
    line("═")
    print(f'{D}Человек:{X} «{request}»')
    if decision.action == ASK:
        print(f"\n  {R}Агент останавливается перед покупкой:{X}")
        for reason in decision.reasons:
            print(f"    {Y}·{X} {reason.text}")
    else:
        print(f"\n  {G}Агент продолжает без вопросов.{X}")
        for note in decision.notes:
            print(f"    {D}· (мягко, не останавливает) {note.text}{X}")


def main() -> int:
    rows = []

    for scn in SCENARIOS:
        facts = extract_intent(scn.request, scn.deadline_days)
        decision = decide_before_purchase(
            facts, scn.purchase,
            (scn.amount_min_cents, scn.amount_max_cents),
            scn.allowlist,
        )
        show(f"{scn.title}  [{scn.id}]", scn.request, decision)
        expected_ask = scn.expect in ("divergent", "vi_rejects")
        rows.append((scn.id, decision.action, expected_ask))

    # доп. случай: мягкое расхождение не должно останавливать агента
    soft_request = ("Черные кроссовки, а вообще если только белые есть — "
                     "ну ладно, разница не принципиальная.")
    facts = extract_intent(soft_request)
    decision = decide_before_purchase(
        facts, [("ASI-GEL-44-WH", 1)], (10000, 15000),
        ["ASI-GEL-42-BK", "ASI-GEL-44-WH"],
    )
    show("Доп. случай: мягкое расхождение не должно останавливать  [soft-demo]",
         soft_request, decision)
    rows.append(("soft-demo", decision.action, False))

    print()
    line("═")
    print(f"{B}Сводка{X}")
    line("═")
    print(f"{'сценарий':<16}{'решение':<14}{'ожидали спросить':<18}")
    line()
    ok = True
    for sid, action, expected_ask in rows:
        got_ask = action == ASK
        mark = G + "верно" + X if got_ask == expected_ask else R + "разошлось" + X
        ok &= got_ask == expected_ask
        print(f"{sid:<16}{action:<23}{('да' if expected_ask else 'нет'):<9}{mark}")
    line()
    print("\nОжидания сошлись:" if ok else "\nЕсть расхождения:", f"{G}да{X}" if ok else f"{R}нет{X}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
