# AsAsked

[![PyPI](https://img.shields.io/pypi/v/asasked)](https://pypi.org/project/asasked/)

Verifiable Intent proves an agent stayed inside its formal limits. It does not
check whether the agent bought what the person actually asked for.

AsAsked closes that gap **before the money moves**. Between "the cart is
ready" and "pay", a guard compares the cart with the person's own words and
answers either *proceed* or *ask* — with the reasons and a ready question for
the person ("You asked to be able to return them; this pair is final sale.
Should I still go ahead?"). Checking after the purchase is only useful for
disputes; preventing the wrong purchase is the point.

This repository contains the guard, the open sandbox store and benchmark it
is measured in, and the original demonstration of the gap in the standard.

---

## The pre-checkout guard

```bash
pip install asasked
```

Setup for Claude Code, Claude Desktop, Cursor, VS Code, Codex CLI, Gemini CLI
and agent frameworks, model keys and downloads: [docs/install.md](docs/install.md).

```python
from asasked import Guard

guard = Guard("Black ASICS in size 42, I need to be able to return them.",
              today="Monday, 2 November 2026")
guard.check([{"name": "ASICS Gel-Nimbus 26", "brand": "ASICS", "color": "Black/White",
              "size": "42", "price": 159.00, "quantity": 1,
              "returnable": False, "delivery_days": 3}])
# {"decision": "ask",
#  "reasons": ["Asked to be able to return it, the item is final sale: ASICS Gel-Nimbus 26."],
#  "question": "Before I buy this, please check: ... Should I still go ahead?",
#  "notes": []}
```

- The cart is plain dicts; only `name` is required. A fact the person stated
  that the cart says nothing about (no `returnable`, no `delivery_days`) is
  not guessed: it lands in `notes` as "the order doesn't say".
- Colours match by word, in English or Russian ("Triple Black", "Чёрный").
  The first colour of a multi-colour item is its main one: "Black/White" is
  black, "White/Black" is not. Sizes ignore the size system unless both
  sides name one: "EU 42" is 42, "US 9" is not "EU 9".
- `today` defaults to the machine's date. Pass it when the person's day
  differs; deadlines like "by Friday" count from it.
- A Verifiable Intent mandate is optional: `guard.check(cart, mandate)` adds
  its amount limits; without one, only the person's own words are checked.
- Facts are extracted by every model you have a key for (`CLAUDE_API_KEY`
  with `asasked[anthropic]`, `LLM_API_KEY` for Gemini, `OPENAI_COMPAT_*`), or by `Guard(...,
  providers=("anthropic",))`. One model works; two are safer, because a fact
  they disagree on is visible. A disputed detail can only warn, never block.
  The exceptions lean towards asking: if either model heard a deadline, a
  price limit or an item that the order lacks, it counts — models miss
  these far more often than they invent them.
- The decision is plain deterministic code over those facts and the cart,
  so every *ask* can be checked by hand.
- It **fails closed**: if the request cannot be checked, it asks.
- In the sandbox store it runs in three modes: `off`, `advisory` (the agent
  gets a `check_before_checkout` tool) and `enforced` (checkout holds the
  order until the agent has asked the person).

**As an MCP server.** `pip install "asasked[mcp]"` adds `asasked-mcp` (stdio)
with one tool, `check_order(request, cart, answers)`. Its instructions tell
the agent to call it before paying. On *ask* the agent shows the person the
question as it is, then checks again with their reply in `answers`. Facts
are extracted once per request, so re-checking a corrected cart is
instant. Model keys come from the environment, as above. A server can only
answer when asked, so it cannot stop an agent that never calls it. It also
has to take the agent's word for everything it is sent: the request and the
person's replies in `answers` both come from the agent, so an agent could
reword the request or answer for the person. The MCP server is a second
opinion for an agent that wants one, not a lock. If payment goes through
your own code, call `Guard` there instead.

```json
{"mcpServers": {"asasked": {"command": "asasked-mcp",
                            "env": {"CLAUDE_API_KEY": "..."}}}}
```

Configs for each app: [docs/install.md](docs/install.md#the-mcp-server).

**In front of your checkout.** To make sure the agent can't pay around the
guard, put the guard into the payment step itself. While the cart doesn't
match the request, checkout is not called. Instead, the agent gets
"NOT PAID… show the person this question" along with the question. The
person's reply comes from your code, `guard.answer(text)`, never from the
agent, so the agent can't agree on the person's behalf. `cart` turns the
checkout arguments into a cart of dicts, as in `Guard.check`.

```python
pay = guard.protect(checkout, cart=lambda items: items)       # any function, sync or async
```

Hooks for popular agent frameworks are thin layers over the same gate:

| Framework | Install | Hook |
|---|---|---|
| Claude Agent SDK | `asasked[claude-agent]` | `hooks={"PreToolUse": [checkout_hook(guard, cart, tool="mcp__shop__checkout")]}` from `asasked.integrations.claude_agent` |
| OpenAI Agents SDK | `asasked[openai-agents]` | `@function_tool(tool_input_guardrails=[checkout_guardrail(guard, cart)])` from `asasked.integrations.openai_agents` |
| LangChain 1.x | `asasked[langchain]` | `create_agent(..., middleware=[CheckoutGuard(guard, cart)])` from `asasked.integrations.langchain` |

The benchmark runs the same agent with and without the guard and reports
what the guard **caught**, what it **missed**, and how often it **stopped a
right purchase** for nothing — the cost of a guard is as important as its
benefit.

```bash
python scripts/run_agents.py --tasks all --agents naive,gpt-6-sol --guard both
```

---

## The gap

[Verifiable Intent](https://github.com/agent-intent/verifiable-intent) (draft
v0.1) cryptographically binds a purchase to a delegation chain: the item is on
an approved list, the amount is inside a band, the merchant is allowed. All of
that is real and it verifies.

What the person actually said is carried in a single field, `prompt_summary`.
In the spec it is:

- **OPTIONAL** (`spec/credential-format.md`)
- annotated *"for audit trail"* (`spec/README.md`)
- **never read by any verification code** — `grep prompt_summary` across
  `src/verifiable_intent/verification/` returns nothing

So the person's own words are present in the mandate, and nothing compares them
to the constraints or to the final cart.

This is not only a `prompt_summary` problem. The constraint types the standard
defines are:

| Constraint | Expresses |
|---|---|
| `AllowedMerchantConstraint` / `AllowedPayeeConstraint` | who may be paid |
| `CheckoutLineItemsConstraint` | which SKUs, how many |
| `PaymentAmountConstraint` / `PaymentBudgetConstraint` | how much |
| `PaymentRecurrenceConstraint` / `AgentRecurrenceConstraint` | how often |
| `ReferenceConstraint` | linkage |

There is no way to express *"in black"*, *"size 42"*, *"returnable if it
doesn't fit"*, or *"here by Saturday"* — so a purchase can satisfy every
constraint in the standard and still be the wrong purchase.

### Why this matters for liability

Issue [#15](https://github.com/agent-intent/verifiable-intent/issues/15) asks
who absorbs the loss when an agent's error produces a purchase the user
disputes. The issue body records this answer:

> The merchant is liable as they have verified L3 cart_jwt against the L2's
> user intent

Its provenance is worth stating precisely. The answer is marked `[CY]` and
preceded by a request for @fahads9 to verify it; the issue has no comments, so
it has not been confirmed. It is not an official position of the standard, and
the same answer notes that a liability shift is still being worked out in the
Agent Pay Acceptance framework.

It is nonetheless the answer on record, and it is the intuitive one: someone
must reconcile the cart against intent, and the merchant is the obvious
candidate. The problem is that the standard gives merchants no mechanism to do
it. The duty is assigned; the instrument does not exist.

---

## Reproduce it

```bash
git clone https://github.com/agent-intent/verifiable-intent.git   # next to this repo
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../verifiable-intent -e ".[dev]"
python scripts/run.py
```

`scripts/run.py` builds a genuine VI chain for each scenario — real ES256 signatures,
real selective disclosure, verified by the Mastercard SDK, nothing mocked — and
then runs the intent check against the same purchase.

The VI SDK is located via `VI_SDK_PATH`, then `../verifiable-intent`, then
`./verifiable-intent`.

`scripts/run.py` also needs a model for intent extraction (see `.env.example`).
Three providers are supported and interchangeable: Gemini through Google's own
API (`LLM_API_KEY`, no extra dependencies), Claude (`pip install -e
".[anthropic]"`, then `CLAUDE_API_KEY`, plus `CLAUDE_BASE_URL` for a compatible
proxy), and any OpenAI-compatible `/chat/completions` endpoint
(`OPENAI_COMPAT_*`). `LLM_PROVIDER` picks the default; `LLM_AGREE_PROVIDERS`
picks the pair that is compared.
`build_conformance_vectors.py` does **not** need a model — it exercises only
the cryptographic path.

`scripts/run_stress_test.py --provider both` runs every phrase through both
models and reports the fields where they disagree.

---

## What the scenarios show

Eight purchases. In each one the agent stays strictly inside its mandate.

| Scenario | Person asked for | Agent bought | VI | Intent |
|---|---|---|---|---|
| `ok-baseline` | cheap beginner Babolat | Babolat Drive Junior | passes | matches |
| `price-top` | *"cheap, for a beginner"* | top-of-band pro racket | passes | **diverges** |
| `brand-swap` | *"Babolat, I'm used to them"* | HEAD | passes | **diverges** |
| `variant` | black ASICS, size 42 | white ASICS, size 44 | passes | **diverges** |
| `quantity` | *"a couple of cans"* | six | passes | **diverges** |
| `refund` | *"so I can return it"* | non-returnable | passes | **diverges** |
| `deadline` | *"by Saturday, tournament"* | ships in 21 days | passes | **diverges** |
| `vi-catches` | beginner racket under 15 000 | out-of-allowlist pro racket | **rejects** | diverges |

**Six of eight purchases satisfy Verifiable Intent completely while
contradicting what the person asked for.** The last row is the control: given a
real violation, the standard catches it on its own and this project adds
nothing.

In `variant` the price matches to the cent. In `refund` and `deadline` the
person's condition cannot be written as a constraint at all.

---

## How the check is built

```
src/asasked/
  catalog.py                    products with attributes VI constraints cannot express
  scenarios.py                  8 scenarios: request -> constraints -> purchase
  vi_runner.py                  builds a real VI chain, verifies it with the Mastercard SDK
  guard.py                      the pre-checkout guard: proceed or ask, with the question
  coherence.py                  extraction + deterministic checking + pre-purchase decision
  llm_extract.py                the language model call — the only AI in the project
  stress_phrases.py             37 real-speech phrases in Russian for testing extraction
  stress_phrases_en.py          40 real-speech phrases in English, same categories
scripts/
  run_stress_test.py            runs them, auto-checking where an answer is unambiguous
  run.py                        8 scenarios, after the fact
  run_prepurchase.py            same scenarios, decided before checkout
  build_conformance_vectors.py  generates conformance_vectors.json
  store/                        the sandbox store: catalog_v1.py, store.py (tools), http.py
  harness/                      agent runs: tasks.py (labelled pilot and hard sets), agent.py
                                (loop), user_sim.py (simulated person), run.py (scoring)
scripts/run_agents.py           real models shop in the store, results to runs/*.jsonl
scripts/demo_store.py           a naive agent in the store, no model needed
scripts/serve_store.py          the store over HTTP
tests/                          the deterministic check, VI chain, store; no model needed
```

### Extraction and checking are deliberately separate

1. **Extraction** turns a person's words into facts. This needs a language
   model, and it is confined to `llm_extract.py`.
2. **Checking** compares those facts to the cart. This is ordinary
   deterministic code with no model in it.

The split is the point, not decoration. *"The AI decided so"* is worth nothing
in a dispute. *"The person asked to be able to return it; the item is
non-returnable"* is worth something, because a human can verify it by hand. The
same inputs always produce the same findings — 20 identical calls give one
identical result.

### Soft preferences

Stress-testing exposed a second gap, this one in our own schema rather than the
standard's. People hedge:

> черные кроссовки, а вообще если только белые есть — ну ладно, разница не
> принципиальная
> *(black shoes, though if only white are available — fine, not a big deal)*

A schema of hard facts records `color=black` and the checker blocks a perfectly
acceptable purchase. So the model additionally returns `soft_fields`: which
extracted facts the person themselves marked as non-binding. A mismatch on a
soft field produces a warning instead of a block, and does not stop the agent.
Softness on one field does not weaken the others.

### Requirements no field holds

The fact schema is closed: brand, colour, size, price, quantity, returns,
delivery. "Gluten-free", "fits an iPhone 15", "not made in China" fit none of
them, and a closed schema would drop them without a trace. So the model also
returns `other_conditions`: such requirements in the person's own words, each
marked required or optional by the same signals as `soft_fields`. The model
never judges whether the cart meets them. The shop's data has nothing to
check them against, so the checker asks the person about each required one
and turns each optional one into a note. If only one of the models heard a
condition, it becomes a note too. On the 77 stress phrases these appear only
where the person really set such a condition ("not black or white", "no
worse than HEAD"). Fallbacks the fields already hold ("43 if there's no 42")
sometimes show up as optional, and those produce a note, not a stop.

### Before the purchase, not after

`decide_before_purchase()` runs the same check while the agent is still
deciding. Blocking findings stop it and produce a question for the person;
warnings do not. This is the earlier and more useful entry point — the buyer
owns the agent, and being asked beforehand beats discovering the problem in a
chargeback.

---

## The sandbox store

The eight scenarios show that the gap exists. To measure how often agents fall
into it, they need somewhere to shop. `asasked.store` is a deterministic
sandbox store an agent drives through tools: `search_products`, `get_product`,
`add_to_cart`, `remove_from_cart`, `view_cart`, `ask_user`, `checkout`.

- **Catalog v1: 456 products** (rackets, shoes, balls, bags) built from
  product families × colour × size × merchant. Traps come from the
  structure, as in a real store, rather than being planted: the same item in
  another colour at the same price to the cent, the same item cheaper at a
  merchant with no returns, or with two-week delivery, a neighbouring model of
  another level, and variants that are out of stock.
- **Search shows name, price and merchant only.** The return policy, delivery
  time and stock are on the product page, so an agent has to look.
- **Every order goes through a real Verifiable Intent chain** built from the
  person's mandate (allowed SKUs, amount band, merchants). An order outside
  the mandate is declined, as a payment network would decline it.
- **Every call is logged**, so a run can be replayed and published.

```bash
python scripts/demo_store.py        # a naive agent: VI passes, the purchase is wrong
python scripts/serve_store.py       # the same store over HTTP on localhost
```

### Running agents in the store

`asasked.harness` runs a real model as the shopping agent. Every model gets the
same neutral system prompt, the same tools and the same step limit (30), so
differences in results are about the model, not the scaffold. Claude runs
through the Anthropic SDK; anything else through an OpenAI-compatible
`/chat/completions`.

Each task carries a human label: which SKUs and quantity would be the right
purchase, or that buying nothing is right, and whether the agent should have
asked first. **Agents are scored against that label, not against the AsAsked
engine.** The engine's verdict on the same purchase is recorded next to it, so
its own accuracy can be measured separately.

```bash
python scripts/run_agents.py --agents claude-sonnet-5,gpt-6-sol,deepseek-v4-pro
```

Each run is one JSON line in `runs/` with the full tool-call transcript. A
failed transport (a proxy error, an empty reply) is recorded as an error and
not counted as the model's result. `--parallel N` runs several at once.

**Task sets.** `pilot` has 8 tasks, one per trap; frontier models pass almost
all of them, so it is a smoke test, not a benchmark. `hard` has 12 tasks
closer to real requests: muddled wording, several conditions at once, soft
preferences ("black ideally, white is fine"), multi-item carts that must
come from one merchant, a stated budget below the mandate, a request in
Russian. Each hard task's label is tested to accept a right purchase and
reject the tempting wrong one. The full labelled dataset is still to come.

**Dataset v1.** 200 tasks built from 13 trap
templates over catalog v1 (returnable variant, deadline, cheapest-but-
returnable, cheapest-in-time, soft colour, out of stock everywhere, over
budget, cans vs packs, brand exclusion, two sizes in one order, vague
requests, a starter kit, and Russian requests), split by hash into 100 open
and 100 hidden tasks; `data/tasks_v1.jsonl` holds the open half. Labels are data, not code (`harness/labels.py`): which
items and how many, a total limit, buy nothing, ask first. Every task is
checked to have a right purchase that is in stock, inside the mandate and from
one merchant, and at least one trap the mandate allows. The generator only
proposes, and one person reviewed it. 44 tasks from 5 templates were
read row by row (`ok` / `fix` / `drop`; the open half's sheet is
`data/review_v1_cos.csv`); for
each remaining template the reviewer answered a concrete "which purchase is
right?" question, and the template's label was checked against the answer
(`data/review_v1_templates.csv`). The other 156 tasks were not read one by
one. The review changed labels in three templates: two-pair shoe orders now
say and require that both pairs are returnable, and "cheapest" requests now
require the cheapest listing that meets the other conditions, not any of
them. English tasks were read through a Russian translation made by Claude Sonnet 5
(`scripts/translate_review.py`), with the original alongside; labels are
translated by code, not by the model. Whether the English requests sound
natural is checked by a model, not a person (`scripts/check_naturalness.py`,
results in `data/naturalness_v1_model.csv`). Dataset v1 has a single
reviewer, so no inter-annotator agreement is reported for it;
`scripts/build_dataset.py --agreement` computes it when a second,
independent review exists. Its tasks and review sheets for the hidden half
live outside the repository, in `../hidden` or wherever `ASASKED_HIDDEN_DIR`
points, under the same file names as in `data/`.

**The hidden half of v1 is not really hidden.** The generator's seed and the
open/hidden split rule are both in this repository, so anyone can rebuild
the hidden tasks with `scripts/build_dataset.py`. Treat all 200 v1 tasks as
public: they are for development, not for held-out scores. Dataset v2 draws
its hidden tasks from a seed that is kept outside the repository.

```bash
python scripts/build_dataset.py
python scripts/run_agents.py --tasks v1-open --agents naive --guard both
```

**Simulated person.** A fixed reply to every question made one honest agent
fail: it asked "reply yes to confirm" and never got a yes. In hard tasks,
`ask_user` is answered by a model that knows the person's full intent,
including what they did not say, and answers only what is asked, as in
tau-bench. It does not judge; scoring is still against the label. An agent
that ends its turn with a question in plain text instead of calling
`ask_user` ("the cheaper pair is final sale — or the pricier one with
returns?") has asked the person, not given up: the question goes to the same
simulated person and the run continues. The product page states delivery as
"arrives within N days of ordering"; a bare `ships_in_days` was read by one
model as dispatch time, and it would not buy against a deadline.

### Results: with and without the guard

Each agent did every task twice: guard off, and guard on with checkout
asking it first (`--guard both`, the guard extracting facts with models, as in
normal use). One run per task, scored against the labels. "Wrong" means the
payment went through and VI accepted it, but the purchase was not what the
person asked for. These runs date from 26 and 30 October 2026, before the
guard changes of 31 October (requirements no field holds, stricter colour
and size matching), and have not been repeated since. The run logs are not
published yet.

**Dataset v1, all 200 tasks** (off → on):

| Agent | As asked | Wrong, VI passed | Bought nothing, should have |
|---|---|---|---|
| naive (first search result) | 1 → 16 | 198 → 11 | 1 → 173 |
| claude-sonnet-5 | 199 → 198 | 1 → 1 | 0 → 1 |
| deepseek-v4-flash | 195 → 197 | 0 → 0 | 5 → 3 |
| gpt-6-sol | 187 → 184 | 1 → 1 | 12 → 15 |
| minimax-m3 | 145 → 152 | 0 → 1 | 55 → 47 |
| nemotron-3.5-lightning | 165 → 159 | 2 → 1 | 33 → 40 |

The naive agent buys the trap almost every time; the guard stopped 187 of
its 200 carts, let 12 wrong ones through and stopped no right one. The naive
agent cannot answer a question, so a stop leaves it with nothing bought.
Real models rarely fell into v1's traps: 4 wrong purchases in 1,000 without
the guard and 4 with it. Their failures are giving up, which the guard does
not address. Across 821 checks on the models' carts the guard caught 1 wrong
cart, missed 3 and stopped 5 right ones.

**Dataset v2, open half, 50 tasks** (off → on). v1 did not tell the models
apart, so v2 keeps only trap templates in which strong models made mistakes
in a pilot (7 templates: corrections mid-request, an event deadline, three
items from one merchant, cheapest-but-returnable, a brand exclusion, two
items, deadlines in Russian). The templates were chosen where the guard has
something to catch; read the numbers with that in mind. The open half is
`data/tasks_v2.jsonl`; the hidden half was run too and is not reported here.

| Agent | As asked | Wrong, VI passed | Bought nothing, should have |
|---|---|---|---|
| claude-sonnet-5 | 49 → 50 | 1 → 0 | 0 → 0 |
| deepseek-v4-flash | 49 → 50 | 1 → 0 | 0 → 0 |
| gpt-6-sol | 50 → 48 | 0 → 0 | 0 → 2 |
| minimax-m3 | 50 → 50 | 0 → 0 | 0 → 0 |
| nemotron-3.5-lightning | 38 → 48 | 10 → 1 | 2 → 1 |

Wrong purchases fell from 12 of 250 to 1 of 250, almost all of them
nemotron's. The guard itself caught 5 wrong carts and missed 1; the rest of
nemotron's change is the difference between two single runs. The cost: in 19
of 255 checks the guard stopped a right cart and the agent had to ask the
person. Such a stop costs one extra question; with the guard on, 3 of 250
runs ended with nothing bought, against 2 without.

---

## Conformance vectors

The standard ships no cross-implementation test vectors, so a second
implementation has no way to show it agrees with the reference one. Second
implementations do exist — an open TypeScript library is announced in
[#30](https://github.com/agent-intent/verifiable-intent/issues/30) — but none
of the discussions includes shared vectors to test them against.

`build_conformance_vectors.py` generates them: all 8 scenarios, each with a
genuinely signed chain (L1, L2, the L2 payment presentation, L3a, L3b), the
public JWKs, and the expected verdict — chain validity, constraint
satisfaction, and the exact violations.

The output is **not** committed. L3 mandates expire five minutes after
issuance, so a frozen fixture would test "can you reject something stale"
within minutes of being written. Run the generator and validate the result
immediately.

The signatures are real: they verify with a plain ECDSA implementation and no
Mastercard SDK involved, which is exactly what a second implementation would
do.

---

## Limitations

Read the numbers with these in mind:

- **The eight scenarios were written to expose this gap.** "Six of eight" is
  not a measured failure rate in the wild; it shows the failure mode exists and
  is easy to construct, not how often it occurs.
- **The scenario catalog is a toy** — 7 products, 2 merchants. The sandbox
  store has 456 products and 4 merchants, but it is still one sport and a
  catalog we built ourselves.
- **Two models, two languages, 77 phrases.** On 2026-10-25 the full stress
  set (37 Russian + 40 English phrases) ran through Claude Sonnet 5 and
  Gemini 3 Flash, each phrase extracted by both: 61 phrases with an
  unambiguous answer all matched, 0 extraction failures, 16 left for manual
  reading by design. The models disagreed on at least one field in 12 of 77
  phrases, mostly deadlines without a reference date and price preferences
  one model inferred but the person never stated. One disagreement was a
  real catch: one model read the Russian idiom "красная цена" ("the most I'd
  pay") as the colour red. Disputed fields warn instead of blocking. Before
  that run, the earlier prompt made Claude answer greetings in prose instead
  of JSON (3 failures). Earlier, Gemini alone on the 37 Russian phrases:
  0 failures.
- **Extraction is not bit-reproducible.** Even at `temperature=0` Gemini
  occasionally differs on borderline phrasing; the Claude API takes no
  sampling parameters at all. The deterministic half is
  unaffected, and it is the half that belongs in a dispute.
- **Soft-field detection depends on the model** noticing that a person hedged.
- **The agent benchmark is small and was run once.** Each agent did each task
  once with the guard and once without, so a difference of one or two tasks
  is noise. Labels have a single reviewer, the person answering questions is
  a model, and v2's templates were chosen where models make mistakes. The
  runs predate the guard changes of 31 October 2026.
- **On v1, the guard did not help real models**: they bought wrong 4 times
  in 1,000 with or without it. The clear effect is on a naive agent and on
  one weaker model in v2.
- **This is a prototype.** It is packaged and the deterministic half is
  covered by tests (`pytest`, no model or network needed), but there is no
  public API yet.

---

## Relationship to the standard

This repository works *on top of* Verifiable Intent and does not modify it. The
spec is Apache 2.0 and is expected as a sibling checkout, not vendored here.

The question has been put to the standard in issue
[#37](https://github.com/agent-intent/verifiable-intent/issues/37)
(September 2026); as of 31 October 2026 it has no replies. Before it, a
search of every issue, pull request and comment in that repository found
none addressing the mismatch between stated intent and encoded constraints.
The spec itself is unchanged since April 2026 (commit `356c296`).
