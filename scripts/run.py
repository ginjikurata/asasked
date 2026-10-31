"""Run all scenarios.

For each one: the real Verifiable Intent check, then the intent check against
the cart. The interesting rows are where the first says "fine" and the second does not.
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
        print(f'{D}Person:{X} "{scn.request}"')
        print(f'{D}In the mandate:{X} "{scn.prompt_summary}"')
        allow = ", ".join(f"{s} ({find(s)['price_cents']/100:.0f})" for s in scn.allowlist)
        print(f"{D}Allowed:{X} {allow}")
        print(f"{D}Amount band:{X} {scn.amount_min_cents/100:.0f}–{scn.amount_max_cents/100:.0f}"
              f"   {D}quantity cap:{X} {scn.quantity_cap}")
        bought = ", ".join(f"{find(s)['name']} ×{q}" for s, q in scn.purchase)
        print(f"{D}Bought:{X} {bought}")

        vi = run_vi(scn)
        vi_ok = vi["chain_valid"] and vi["constraints_ok"]
        mark = f"{G}passes{X}" if vi_ok else f"{R}rejects{X}"
        print(f"\n  Verifiable Intent: {mark}"
              f"   {D}(chain signature: {'ok' if vi['chain_valid'] else 'failed'}){X}")
        for v in vi["violations"] or vi["chain_errors"]:
            print(f"    {R}·{X} {v}")

        facts = extract_intent(scn.request, scn.deadline_days)
        verdict = check_coherence(facts, scn.purchase,
                                  (scn.amount_min_cents, scn.amount_max_cents),
                                  scn.allowlist)
        cmark = f"{G}matches{X}" if verdict.coherent else f"{Y}diverges{X}"
        print(f"  Intent check:      {cmark}")
        for f in verdict.findings:
            if f.severity == BLOCK:
                print(f"    {Y}·{X} {f.text}")
            else:
                print(f"    {D}· (soft, does not block) {f.text}{X}")

        gap = vi_ok and not verdict.coherent
        if gap:
            mismatches += 1
            print(f"\n  {B}{R}Gap:{X} the cryptography is satisfied, the person is not.")
        if scn.note:
            print(f"  {D}{scn.note}{X}")

        rows.append((scn.id, vi_ok, verdict.coherent, gap, scn.expect))

    # --- summary -------------------------------------------------------
    print()
    line("═")
    print(f"{B}Summary{X}")
    line("═")
    print(f"{'scenario':<16}{'standard':<14}{'intent':<14}{'gap':<10}")
    line()
    for sid, vi_ok, coh, gap, _ in rows:
        print(f"{sid:<16}"
              f"{(G+'passes'+X if vi_ok else R+'rejects'+X):<23}"
              f"{(G+'matches'+X if coh else Y+'diverges'+X):<23}"
              f"{(R+'yes'+X if gap else D+'—'+X)}")
    line()
    total = len(rows)
    print(f"\nScenarios: {total}. The standard let through a purchase that diverges "
          f"from the request: {B}{mismatches}{X}.")

    ok = all(
        (exp == "vi_rejects" and not vi_ok)
        or (exp == "coherent" and vi_ok and coh)
        or (exp == "divergent" and vi_ok and not coh)
        for _, vi_ok, coh, _, exp in rows
    )
    print("Scenario expectations:", f"{G}met{X}" if ok else f"{R}not met{X}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
