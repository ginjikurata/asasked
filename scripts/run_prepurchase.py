"""Demo of the "before purchase" mode.

The same check (check_coherence) as in run.py, only called at the moment
"the agent is about to press buy" rather than "has already bought". BLOCK
findings stop the agent and require the person's confirmation; WARN ones do
not stop it but stay visible.

Uses the same 8 scenarios from scenarios.py: where run.py shows the gap after
the fact ("the cryptography is satisfied, the person is not"), this shows what
would have happened if the agent had asked before rather than after.
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
    print(f'{D}Person:{X} "{request}"')
    if decision.action == ASK:
        print(f"\n  {R}The agent stops before buying:{X}")
        for reason in decision.reasons:
            print(f"    {Y}·{X} {reason.text}")
    else:
        print(f"\n  {G}The agent goes on without questions.{X}")
        for note in decision.notes:
            print(f"    {D}· (soft, does not stop) {note.text}{X}")


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

    # extra case: a soft mismatch must not stop the agent
    soft_request = ("Черные кроссовки, а вообще если только белые есть — "
                     "ну ладно, разница не принципиальная.")
    facts = extract_intent(soft_request)
    decision = decide_before_purchase(
        facts, [("ASI-GEL-44-WH", 1)], (10000, 15000),
        ["ASI-GEL-42-BK", "ASI-GEL-44-WH"],
    )
    show("Extra case: a soft mismatch must not stop the agent  [soft-demo]",
         soft_request, decision)
    rows.append(("soft-demo", decision.action, False))

    print()
    line("═")
    print(f"{B}Summary{X}")
    line("═")
    print(f"{'scenario':<16}{'decision':<14}{'expected to ask':<18}")
    line()
    ok = True
    for sid, action, expected_ask in rows:
        got_ask = action == ASK
        mark = G + "right" + X if got_ask == expected_ask else R + "wrong" + X
        ok &= got_ask == expected_ask
        print(f"{sid:<16}{action:<23}{('yes' if expected_ask else 'no'):<9}{mark}")
    line()
    print("\nExpectations met:" if ok else "\nThere are mismatches:", f"{G}yes{X}" if ok else f"{R}no{X}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
