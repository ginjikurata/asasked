# AsAsked pre-checkout guard — specification

**Status:** draft 0.1 (2026-10-26). Describes the reference implementation in
`src/asasked/guard.py` and `src/asasked/coherence.py`; where the two disagree,
that is a bug in one of them.

## 1. Purpose

An agent has assembled a cart on a person's behalf. Before payment, the guard
answers one question: **does this cart match what the person asked for?** It
returns one of two decisions:

- `proceed`: no blocking mismatch; payment may go ahead.
- `ask`: at least one blocking mismatch; the agent must consult the person
  before paying, and the guard supplies the reasons and a ready question.

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
| `model` | string | Product model or line as named ("EZONE 98"), without the brand. |
| `color` | string | Colour chosen. A colour that is only excluded: `null`. |
| `size_label` | string | Size as stated ("42", "4 3/8"). |
| `level` | `beginner` \| `intermediate` \| `pro` | Level stated or clearly described. |
| `price_preference` | `cheap` \| `premium` | Stated preference. |
| `explicit_max_cents` | integer | A stated spending limit, in minor units. Hyperbole is not a limit. |
| `quantity` | integer | How many, **in the units the person counts** (cans of balls, not packs). |
| `needs_refundable` | boolean | The person wants to be able to return or exchange. |
| `deadline_days` | integer | Days until a stated deadline, relative to a given *today*. |
| `lines` | list | Several variants in one order ("size 40 for my wife and 43 for me"): one entry per variant with its own `model`, `color`, `size_label`, `quantity`; everything else is shared. Empty otherwise. |
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
   - `soft` → the union.
3. The extractor MUST be given today's date, so that "by Saturday" becomes a
   number of days. When the deadline is a named weekday, the extractor returns
   the weekday and the number of days is counted by code, inclusive of that
   day (from Monday, "by Friday" is 4): two models counting the same weekday
   differently is not a disagreement worth stopping a purchase over.
4. Extraction output MUST be validated against the schema. Malformed output is
   an extraction failure, never silently coerced to `null`.
5. **Fail closed:** if facts cannot be extracted, the decision is `ask`, with a
   reason saying the request could not be checked.

## 5. Checks

Every check compares one fact with the cart. The item attributes it needs
(brand, name, colour, size, level, returnability, delivery time, units, price)
must be available to the guard from the catalog or checkout data.

| Code | Finding when |
|---|---|
| `brand` | item brand ≠ `brand` |
| `model` | the words of `model` (minus the brand) are not all in the item name |
| `color` | item colour ≠ `color` |
| `size` | item has a size and it ≠ `size_label` |
| `level` | item level is not `level` and not `any` |
| `refund` | `needs_refundable` and the item is final sale |
| `deadline` | item delivery time > `deadline_days` |
| `price` | `price_preference = cheap`, a single-item cart, and an item that fits every stated fact is more than 15% cheaper among the allowed items |
| `explicit-max` | cart total > `explicit_max_cents` |
| `quantity` | total units in the cart ≠ `quantity` (both more and fewer) |

**With `lines`.** Cart items are assigned to lines so that the number of
blocking findings, missing lines and extra items is smallest. Every check above
then runs per pair, using the line's own fields over the shared ones;
`quantity` is compared per line, and two more codes apply:

| Code | Finding when |
|---|---|
| `missing` | a line has no cart item assigned |
| `extra` | a cart item is not assigned to any line |

If `lines` is disputed, every finding that comes from the lines is `warn`.

**Severity.** A finding is `warn` if its field is in `soft` or in `disputed`,
otherwise `block`.

## 6. Decision

- `proceed` if there is no `block` finding. `warn` findings are returned as
  notes so the person can see them.
- `ask` otherwise, with every `block` finding as a reason and a question for
  the person:

  > Before I buy this, please check:
  > – Asked to be able to return it, the item is final sale: …
  > Should I still go ahead?

The guard does not forbid. It requires the person to be consulted. A person
who knowingly accepts a final-sale item has made a decision; the guard's job
is to make sure they were asked.

## 7. Where it runs

- **Agent side, advisory:** the agent calls the guard before checkout and
  decides what to do with the answer.
- **Store or checkout side, enforced:** checkout runs the guard itself. On
  `ask`, the order is held until the agent has consulted the person; a changed
  cart is checked again.
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
- **Measured in a sandbox.** The numbers below come from our own catalog and
  tasks; see the README's limitations.

## 10. Measured behaviour (sandbox, 2026-10-26)

20 labelled tasks, catalog v1, facts extracted by Claude Sonnet 5 and Gemini 3
Flash. A naive agent (buys the first search result) made 17 wrong purchases
without the guard and 0 with it. The guard flagged 17 of 17 wrong carts, missed
none, and stopped no right cart. With four model agents (GPT-6 Sol, DeepSeek V4
Flash, MiniMax M3, Nemotron 3.5 Lightning) it never stopped a right purchase.
An earlier run had one wrong purchase left: the guard flagged it, and the
simulated person approved it against their own stated intent; the simulator's
instructions were tightened after that.

## 11. Conformance

A conforming implementation, given the same facts and cart, MUST produce the
same decision and the same set of finding codes. Test cases live in
`tests/test_coherence.py`, `tests/test_guard.py` and `tests/test_hard.py`. A
standalone case file (`facts`, `cart`, item attributes, expected `decision` and
`codes`) is planned.
