# asasked (TypeScript)

A guard before an AI agent pays: does this cart match what the person asked
for? Between "the cart is ready" and "pay", it compares the cart with the
person's own words and answers *proceed*, *ask* (with the reasons and a ready
question for the person) or *refuse*.

This is the TypeScript port of the [Python package](https://pypi.org/project/asasked/).
The checks are the same code path for path: the tests feed both libraries the
same inputs and expect the same answers, down to the text of each reason. See
the [main README](https://github.com/ginjikurata/asasked#readme) for how the
check is built and how it was measured.

```bash
npm install asasked
```

```ts
import { Guard } from "asasked";

const guard = new Guard("Black ASICS in size 42, I need to be able to return them.",
  { today: "Monday, 2 November 2026" });
await guard.check([{ name: "ASICS Gel-Nimbus 26", brand: "ASICS", color: "Black/White",
  size: "42", price: 159.0, quantity: 1, returnable: false, delivery_days: 3 }]);
// { decision: "ask",
//   reasons: ["Asked to be able to return it, the item is final sale: ASICS Gel-Nimbus 26."],
//   refused: [],
//   question: "Before I buy this, please check: ... Should I still go ahead?",
//   notes: [] }
```

- Only `name` and `price` are required in a cart item. A fact the person
  stated that the cart says nothing about is not guessed: it lands in `notes`.
- An item that renews carries `recurring: { every: "month", price: 12.99 }`.
- The model only turns the person's words into facts. The decision is plain
  deterministic code over those facts and the cart, so every *ask* can be
  checked by hand.
- It **fails closed**: if the request cannot be checked, it asks, and a plain
  "yes" approves that order as shown and no other.

**In front of your checkout.** While the cart doesn't match the request,
`pay` is not called and the agent gets "NOT PAID… show the person this
question" instead. The person's reply comes from your code through
`guard.answer(text)`, never from the agent.

```ts
const pay = guard.protect(checkout, (items) => items);
```

**Crypto payments.** Pass the payment the agent is about to sign:
`guard.check(cart, { payment: { token: "USDC", network: "solana", amount: 12.5,
to: address, merchant: shopAddress } })`. Token, network, amount and
recipient are checked against the person's words. With
`new Guard(request, { payees: [...] })` money may go only to those addresses;
any other is refused, and no answer from the person approves it. If you have
checked the address with the site yourself, pass the result as
`payment.binding: { outcome: "bound" | "excluded" | "inconclusive" }`.

## Models

Facts are extracted by every model you have a key for, or by the ones in
`new Guard(request, { providers: ["anthropic"] })`. Two are safer than one:
a fact they disagree on can only warn.

| Provider | Settings |
|---|---|
| `anthropic` | `CLAUDE_API_KEY` (or `ANTHROPIC_API_KEY`), optional `CLAUDE_BASE_URL`, `CLAUDE_MODEL` (default `claude-haiku-5-5`) |
| `gemini` | `LLM_API_KEY`, optional `LLM_MODEL` (default `gemini-flash-lite-latest`) |
| `openai_compat` | `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_MODEL` |

Settings are read from `process.env` at call time. Unlike the Python package,
no `.env` file is loaded: use `node --env-file=.env`, or pass your own
extractor with `new Guard(request, { extract })`. The prompt and response
schema are the Python package's, copied by `scripts/build_ts.py`.

## Not in this port yet

The Python package also reads the request from a signed Verifiable Intent
mandate (`Guard.from_mandate`, `claimed=`), checks a payee address with the
site itself (DNS-signed manifest, ENS) and hooks into x402 clients, AP2 and
agent frameworks. Those are Python-only for now.

## Development

```bash
npm install
npm test
```

`test/vectors.json` holds the Python answers, recorded while the Python test
suite runs: `python scripts/build_ts.py --vectors` from the repository root.

Apache-2.0.
