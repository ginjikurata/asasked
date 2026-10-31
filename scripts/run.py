"""Прогон всех сценариев.

Для каждого: настоящая проверка Verifiable Intent, затем сверка намерения
с корзиной. Интересны строки, где первая говорит «в порядке», а вторая — нет.
"""

from __future__ import annotations

from asasked.catalog import find
from asasked.coherence import BLOCK, check_coherence, extract_intent
from asasked.scenarios import SCENARIOS
from asasked.vi_runner import run_vi

G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"


def line(ch="─", n=78):
    print(D + ch * n + X)


def main() -> int:
    rows, mismatches = [], 0

    for scn in SCENARIOS:
        print()
        line("═")
        print(f"{B}{scn.title}{X}  {D}[{scn.id}]{X}")
        line("═")
        print(f'{D}Человек:{X} «{scn.request}»')
        print(f'{D}В мандат попало:{X} «{scn.prompt_summary}»')
        allow = ", ".join(f"{s} ({find(s)['price_cents']/100:.0f})" for s in scn.allowlist)
        print(f"{D}Разрешено:{X} {allow}")
        print(f"{D}Коридор суммы:{X} {scn.amount_min_cents/100:.0f}–{scn.amount_max_cents/100:.0f}"
              f"   {D}предел количества:{X} {scn.quantity_cap}")
        bought = ", ".join(f"{find(s)['name']} ×{q}" for s, q in scn.purchase)
        print(f"{D}Куплено:{X} {bought}")

        vi = run_vi(scn)
        vi_ok = vi["chain_valid"] and vi["constraints_ok"]
        mark = f"{G}пропускает{X}" if vi_ok else f"{R}отклоняет{X}"
        print(f"\n  Verifiable Intent: {mark}"
              f"   {D}(подпись цепочки: {'ок' if vi['chain_valid'] else 'сбой'}){X}")
        for v in vi["violations"] or vi["chain_errors"]:
            print(f"    {R}·{X} {v}")

        facts = extract_intent(scn.request, scn.deadline_days)
        verdict = check_coherence(facts, scn.purchase,
                                  (scn.amount_min_cents, scn.amount_max_cents),
                                  scn.allowlist)
        cmark = f"{G}совпадает{X}" if verdict.coherent else f"{Y}расходится{X}"
        print(f"  Сверка намерения:  {cmark}")
        for f in verdict.findings:
            if f.severity == BLOCK:
                print(f"    {Y}·{X} {f.text}")
            else:
                print(f"    {D}· (мягко, не блокирует) {f.text}{X}")

        gap = vi_ok and not verdict.coherent
        if gap:
            mismatches += 1
            print(f"\n  {B}{R}Дыра:{X} криптография довольна, человек — нет.")
        if scn.note:
            print(f"  {D}{scn.note}{X}")

        rows.append((scn.id, vi_ok, verdict.coherent, gap, scn.expect))

    # --- сводка --------------------------------------------------------
    print()
    line("═")
    print(f"{B}Сводка{X}")
    line("═")
    print(f"{'сценарий':<16}{'стандарт':<14}{'намерение':<14}{'разрыв':<10}")
    line()
    for sid, vi_ok, coh, gap, _ in rows:
        print(f"{sid:<16}"
              f"{(G+'пропускает'+X if vi_ok else R+'отклоняет'+X):<23}"
              f"{(G+'совпадает'+X if coh else Y+'расходится'+X):<23}"
              f"{(R+'да'+X if gap else D+'—'+X)}")
    line()
    total = len(rows)
    print(f"\nСценариев: {total}. Стандарт пропустил покупку, расходящуюся "
          f"с просьбой: {B}{mismatches}{X}.")

    ok = all(
        (exp == "vi_rejects" and not vi_ok)
        or (exp == "coherent" and vi_ok and coh)
        or (exp == "divergent" and vi_ok and not coh)
        for _, vi_ok, coh, _, exp in rows
    )
    print("Ожидания сценариев:", f"{G}сошлись{X}" if ok else f"{R}разошлись{X}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
