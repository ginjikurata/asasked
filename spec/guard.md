# AsAsked pre-checkout guard — specification

**Status:** draft 0.1, revised 2026-11-02. Describes the reference implementation in
`src/asasked/guard.py` and `src/asasked/coherence.py`; where the two disagree,
that is a bug in one of them.

## 1. Purpose

An agent has assembled a cart on a person's behalf. Before payment, the guard
answers one question: **does this cart match what the person asked for?** It
returns one of two decisions:

- `proceed`: no blocking mismatch; payment may go ahead.
- `ask`: at least one blocking mismatch; the agent must consult the person
  before paying, and the guard supplies the reasons and a ready question.

When the payment itself is passed too (§5), a third decision exists:
`refuse`, for a payment that is wrong whatever the person says, such as one
to another address than the shop's. The agent must change the payment, not
ask the person to approve it.

The guard works alongside authorization schemes such as Verifiable Intent and
does not replace them. Those prove the purchase stays within the limits the person
signed (allowed items, amount, merchants). The guard checks the part those
limits cannot express: colour, size, model, returnability, delivery deadline,
quantity as the person counts it, a stated budget, a price preference.

The guard prevents. It does not audit. Running the same check after payment is
possible and useful for disputes, but that is not its purpose.

## 2. Terms

| Term | Meaning |
|---|---|
| **Request** | The person's own words to the agent, verbatim. |
| **Cart** | A list of `(item, quantity)` the agent intends to buy. |
| **Mandate** | The formal limits the person authorised: allowed items, amount band, merchants. |
| **Facts** | Structured statements extracted from the request (§3). |
| **Finding** | One mismatch between a fact and the cart, with a severity (§5). |
| **Decision** | `proceed` or `ask` (§6). |

## 3. Intent facts

Facts are what the person stated, not what the extractor guesses. A field the
person did not state is `null` (or `false` for `needs_refundable`).

| Field | Type | Meaning |
|---|---|---|
| `brand` | string | Brand chosen. An excluded brand ("anything but Wilson") is not a choice: `null`. |
| `brand_not` | list of strings | Brands the person excluded ("anything but Wilson"). |
| `model` | string | Product model or line as named ("EZONE 98"), without the brand. |
| `color` | string | Colour chosen. A colour that is only excluded: `null`. |
| `size_label` | string | Size as stated ("42", "4 3/8"). |
| `level` | `beginner` \| `intermediate` \| `pro` | Level stated or clearly described. |
| `price_preference` | `cheap` \| `premium` | Stated preference. |
| `explicit_max_cents` | integer | A stated spending limit, in minor units. Hyperbole is not a limit. |
| `quantity` | integer | How many, **in the units the person counts** (cans of balls, not packs). |
| `needs_refundable` | boolean | The person wants to be able to return or exchange. |
| `deadline_days` | integer | Days until a stated deadline, relative to a given *today*. |
| `pay_with` | string | The token or coin the person wants to pay with ("pay in USDC", "with my SOL"), as an upper-case ticker without `$`. Not a card, cash or the currency prices are in. |
| `pay_network` | string | The blockchain the person named for the payment ("on Solana"), lower-case English. |
| `lines` | list | Several variants in one order ("size 40 for my wife and 43 for me"): one entry per variant with its own `model`, `color`, `size_label`, `quantity`; everything else is shared. Empty otherwise. |
| `other` | list of strings | Requirements no field above holds ("gluten-free", "fits an iPhone 15"), in the person's words, that the person made a must. |
| `other_optional` | list of strings | The same, marked by the person as nice to have. |
| `soft` | set of field names | Fields the person themselves marked as optional ("black ideally, white is fine"). |
| `disputed` | set of field names | Fields the extractors disagreed on (§4). |

## 4. Extraction

1. Facts are extracted **once per request**, not once per cart check.
2. Extraction SHOULD use **at least two independent extractors** (different
   models or providers) and merge their results:
   - all equal (case-insensitive for strings) → that value;
   - `deadline_days` or `explicit_max_cents` found by **at least one**
     extractor → the strictest (smallest) value found, not disputed. Different
     estimates of one deadline are not a disagreement about whether it exists,
     and extractors miss stated deadlines and limits far more often than they
     invent them; the cost of a wrong value is one extra question;
   - `brand_not` → the union: a brand any extractor heard excluded stays
     excluded;
   - one extractor found a value and another returned `null` → the found
     value, field marked `disputed`;
   - different non-null values otherwise → the first extractor's value, field
     marked `disputed`; for `needs_refundable`, `true`;
   - `lines` that differ between extractors → the first non-empty set, and
     `lines` is marked `disputed`;
   - `other` → the longest list any extractor returned; if some extractor
     returned none, `other` is marked `disputed`. `other_optional` → the
     union, without repeats of `other`;
   - `soft` → the union.

   A single extractor is allowed: then nothing is disputed, and every fact
   blocks unless the person marked it optional.
3. The extractor MUST be given today's date (the reference implementation
   defaults to the current date), so that "by Saturday" becomes a
   number of days. When the deadline is a named weekday, the extractor returns
   the weekday and the number of days is counted by code, inclusive of that
   day (from Monday, "by Friday" is 4): two models counting the same weekday
   differently is not a disagreement worth stopping a purchase over.
4. Extraction output MUST be validated against the schema. Malformed output is
   an extraction failure, never silently coerced to `null`.
5. **Fail closed:** if facts cannot be extracted, the decision is `ask` (or
   `refuse` for a refused payment, §5), with a reason saying the request could
   not be checked.

## 5. Checks

Every check compares one fact with the cart. The item attributes it needs
(brand, name, colour, size, level, returnability, delivery time, units, price)
come from the catalog or checkout data. If the person stated a fact and the
item has no value for the attribute it needs, the check does not run; it
returns an `unchecked` finding, always `warn`, so the person sees what could
not be checked.

| Code | Finding when |
|---|---|
| `brand` | item brand ≠ `brand` (case-insensitive) |
| `brand-excluded` | item brand is in `brand_not` |
| `model` | the words of `model` (minus the brand) are not all in the item name |
| `color` | the words of `color` are not all in the item's **first** colour (below) |
| `size` | item has a size and it ≠ `size_label` (below) |
| `level` | item level is not `level` and not `any` |
| `refund` | `needs_refundable` and the item is final sale |
| `deadline` | item delivery time > `deadline_days` |
| `price` | `price_preference = cheap`, a single-item cart, and an item that fits every stated fact is more than 15% cheaper among the allowed items |
| `explicit-max` | cart total > `explicit_max_cents` |
| `quantity` | total units in the cart ≠ `quantity` (both more and fewer) |
| `other` | one finding per entry of `other` (`block`) and of `other_optional` (`warn`): the guard cannot check free text against the item, so the person decides |
| `unchecked` | a stated fact the item has no attribute for (always `warn`) |

**Colour** is compared by word, in English and Russian ("Triple Black" and
"Чёрный" are black, "gray" is "grey"). An item with several colours
("White/Black") counts as its first one: black as a second colour is a
finding, and the reason says so. **Size** ignores filler ("size 42" = "42"),
a decimal comma ("42,5" = "42.5") and S/M/L spelled out ("Medium" = "M"); a
size system ("EU", "US", "UK"…) counts only when both the item and the person
name one, so "EU 42" = "42" but "US 9" ≠ "EU 9".

**With `lines`.** Cart items are assigned to lines so that the number of
blocking findings, missing lines and extra items is smallest. Every check above
then runs per pair, using the line's own fields over the shared ones;
`quantity` is compared per line, and two more codes apply:

| Code | Finding when |
|---|---|
| `missing` | a line has no cart item assigned |
| `extra` | a cart item is not assigned to any line |

If the extractors disagreed on a field of a line, findings on that field are
`warn`. If they disagreed on how many items the person asked for, every field
taken from the lines is `warn`, and so is `extra`; `missing` still blocks, as
an order missing half of what was asked is worse than one extra question. If
there are too many lines and items to assign exhaustively, the guard returns
a `lines` finding (`block`): the order goes to the person.

**Severity.** A finding is `warn` if its field is in `soft` or in `disputed`,
otherwise `block`.

**Payment.** When the agent pays on-chain, the caller may pass the payment it
is about to sign next to the cart. Payment checks need no model: amounts,
addresses and rates come from the caller (the shop's payment request and the
swap quote), and the comparison is plain code.

| Payment field | Meaning |
|---|---|
| `token` | What reaches the shop ("USDC"). Required. |
| `network` | The chain the transaction goes out on ("solana"). |
| `amount` | How much of `token` the shop receives, in whole token units (12.5). Required. |
| `to` | The recipient address in the transaction. Required. |
| `merchant` | The address the shop's payment request names. |
| `rate` | Value of one `token` in the cart's currency (1.0 for USDC against dollar prices). |
| `swap` | When the person's token is swapped first: `from_token`, `amount_in` (what leaves the person's wallet), `rate` (value of one `from_token`), `quote_out` and `min_out` (expected and guaranteed amount of `token`). |
| `max_slippage_bps` | Optional caller-set cap on the swap's slippage; default 100 (1%). |

| Code | Finding when |
|---|---|
| `pay-recipient` | `to` ≠ `merchant` (`0x` addresses compare case-insensitively, others exactly). Always `block`, and refused: no fact of the person's can make paying a stranger right. Without `merchant`, `unchecked` (`warn`). |
| `pay-token` | the token the person gives (`swap.from_token`, else `token`) ≠ `pay_with` |
| `pay-network` | `network` ≠ `pay_network`; without `network`, `unchecked` |
| `pay-amount` | `amount × rate` exceeds the cart total by more than max(1 cent, 0.5%): `block`, refused; is below it by as much: `warn` (the shop may reject it, the person loses nothing) |
| `pay-max` | what the person gives (`swap.amount_in × swap.rate`, else `amount × rate`) exceeds `explicit_max_cents` while the cart total does not: swap costs and slippage count toward the limit. Not checked while `pay-amount` refuses: the corrected payment is checked again |
| `pay-slippage` | `(quote_out − min_out) / quote_out` exceeds `max_slippage_bps` (`block`, refused) |
| `pay-swap-short` | `min_out` < `amount`: the swap may not yield enough to pay (`block`, refused) |
| `pay-unchecked` | `pay_with` or `pay_network` stated and no payment passed: `block` like `other`, as the guard cannot see how the order is paid |

`pay-token` and `pay-network` take their severity from the fact, like every
other check; `pay-max` from `explicit_max_cents`. Without `rate` (or
`swap.rate`), `pay-amount` and `pay-max` return `unchecked` (`warn`). Payment
findings join the cart's in the decision (§6).

**Refused findings.** `pay-recipient`, `pay-amount` when overpaying,
`pay-slippage` and `pay-swap-short` (all at `block`) do not depend on what the
person said: the shop's address, the order's amount and a safe swap are right
for every request. No answer from the person can approve them, so they are
not put to the person; the agent has to change the payment. `pay-token`,
`pay-network` and `pay-max` stay questions: the token, the chain and the limit
are the person's to choose. If the facts could not be extracted, the refused
findings still run (they need no facts); the others cannot be checked.

## 6. Decision

- `proceed` if there is no `block` finding. `warn` findings are returned as
  notes so the person can see them.
- `ask` otherwise, with every `block` finding as a reason and a question for
  the person:

  > Before I buy this, please check:
  > – Asked to be able to return it, the item is final sale: …
  > Should I still go ahead?

- `refuse` if any finding is refused (§5), whatever else is found. `reasons`
  lists every `block` finding, `refused` lists the refused ones, and
  `question` covers only the rest: it is empty when nothing else is wrong, and
  otherwise is asked alongside the refusal, so a corrected payment does not
  stop again on the cart.

The guard does not forbid what the person can decide. It requires them to be
consulted. A person who knowingly accepts a final-sale item has made a
decision; the guard's job is to make sure they were asked. A refused payment
is the one exception: it is wrong for every request, so there is nothing to
ask.

## 7. Where it runs

- **Agent side, advisory:** the agent calls the guard before checkout and
  decides what to do with the answer.
- **Store or checkout side, enforced:** checkout runs the guard itself. On
  `ask`, the order is held until the agent has consulted the person; on
  `refuse`, until the payment is changed. A changed cart or payment is
  checked again.
- **As an MCP tool:** `asasked-mcp` serves one tool, `check_order(request,
  cart, answers, today, payment)`, that returns the decision, reasons,
  refused findings and question; the agent passes back the person's answers
  on the next call.
- **Wrapped around a payment function:** `Guard.protect(pay, cart)` returns a
  payment function that checks the cart first and, on `ask`, does not pay and
  returns the question to the agent instead; on `refuse`, it does not pay and
  tells the agent what to change in the payment, with the question for the
  person only when the cart needs one too. Hooks built on it exist for the
  Claude Agent SDK, the OpenAI Agents SDK and LangChain.
- **With Verifiable Intent:** the guard runs before the agent creates the
  final L3 mandates. The request and, optionally, the extracted facts can
  travel in L2 next to `prompt_summary`, so the same check is reproducible by
  the merchant and in a dispute.

## 8. Determinism and audit

The decision step is deterministic: the same facts and the same cart always
produce the same findings and decision. Only extraction involves a model. An
implementation SHOULD record, per check: the request, the facts with `soft` and
`disputed`, the cart, the findings and the decision. Every `ask` can then be
verified by a human without trusting a model.

## 9. Known limitations

- **Lines cover variants, not unrelated items.** "A racket and a can of
  balls" with different conditions for each (only the racket must be
  returnable) is not yet expressible; shared facts apply to every item.
- **The catalog must expose the attributes.** Without returnability or
  delivery time on the item, the `refund` and `deadline` checks cannot run.
- **`price` is a heuristic.** "Cheap" is compared only within items that fit
  every other stated fact, with a fixed 15% threshold.
- **Extraction quality bounds the guard.** Two extractors reduce silent errors
  but do not remove them; disputed facts only warn.
- **Payment data is the caller's.** The guard compares what it is given: the
  shop's address, the rates and the swap quote. It does not read the chain,
  fetch prices or sign anything, and a caller that passes a forged quote or
  merchant address defeats `pay-*` checks. Pass what the shop's payment
  request and the swap provider returned, not what the agent says.
- **Free-text requirements are not checked.** An `other` requirement is
  always put to the person, even when the item plainly meets it.
- **Measured in a sandbox.** The numbers below come from our own catalog and
  tasks; see the README's limitations.

## 10. Measured behaviour (sandbox, runs of 2026-10-31 to 2026-11-03)

Agents bought from our sandbox store with the guard off and enforced, one run
per task, scored against human-reviewed labels, on the open halves of both
datasets only: v1 with AsAsked 0.1.3, v2 with 0.1.4 and a stricter simulated
person. The run logs are in `data/runs/`; the figures
below are computed from them by `scripts/summarize_runs.py`.

- **Naive agent** (buys the first search result), dataset v1, 100 open tasks:
  99 wrong purchases without the guard, 3 with it. The guard stopped 98 wrong
  carts, missed 1 and stopped no right one; the simulated person then approved
  2 of the stopped carts.
- **Five model agents**, dataset v1, 100 open tasks each: 1 wrong purchase in
  500 without the guard, 0 with it. Across 460 checks the guard caught that 1
  wrong cart, missed none and stopped 9 right ones.
- **The same five agents**, dataset v2 (templates chosen where strong models
  made mistakes), 50 open tasks each: wrong purchases fell from 11 of 250 to 0.
  Across 255 checks the guard caught 8 wrong carts, missed none and stopped 14
  right ones, each costing one extra question to the person. The simulated
  person never accepts a missing, deferred or substituted item; that rule was
  written after an earlier run on these same tasks.

Per-model tables are in the README.

## 11. Conformance

A conforming implementation, given the same facts and cart, MUST produce the
same decision and the same set of finding codes. Test cases live in
`tests/test_coherence.py`, `tests/test_guard.py` and `tests/test_hard.py`. A
standalone case file (`facts`, `cart`, item attributes, expected `decision` and
`codes`) is planned.
