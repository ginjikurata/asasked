// The TypeScript checks against answers the Python checks gave on the same
// inputs, recorded while the Python tests ran (scripts/build_ts.py --vectors).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ExtractionError, Guard, checkCoherence, checkPayment, decideBeforePurchase,
  factsFromModel, intentFacts, intervalName, mergeFacts, parsePayment, plainYes,
} from "../dist/index.js";

const vectors = JSON.parse(readFileSync(new URL("./vectors.json", import.meta.url), "utf8"));

const facts = (json) => intentFacts({ ...json, soft: new Set(json.soft), disputed: new Set(json.disputed) });
const plain = (f) => ({ ...f, soft: [...f.soft].sort(), disputed: [...f.disputed].sort() });
const finder = (products) => (sku) => {
  if (!(sku in products)) throw new Error(`unknown sku ${sku}`);
  return products[sku];
};

function each(kind, fn) {
  const cases = vectors[kind] ?? [];
  test(`${kind}: ${cases.length} Python answers`, async () => {
    assert.ok(cases.length > 0, `no ${kind} vectors`);
    for (const [i, v] of cases.entries()) {
      try {
        await fn(v);
      } catch (e) {
        e.message = `${kind}[${i}]: ${e.message}\ninput: ${JSON.stringify(v).slice(0, 2000)}`;
        throw e;
      }
    }
  });
}

each("coherence", (v) => {
  const opts = { allowlist: v.allowlist, spentBeforeCents: v.spent_before_cents };
  const verdict = checkCoherence(facts(v.facts), v.purchase, finder(v.products), opts);
  assert.deepEqual(verdict, { coherent: v.coherent, findings: v.findings });
  const decision = decideBeforePurchase(facts(v.facts), v.purchase, finder(v.products), opts);
  assert.equal(decision.action, v.findings.some((f) => f.severity === "block") ? "ask" : "proceed");
});

each("payment", (v) => {
  const out = checkPayment(facts(v.facts), v.payment, v.total_cents,
    { overLimit: v.over_limit, payees: v.payees, spentBeforeCents: v.spent_before_cents });
  assert.deepEqual(out, v.findings);
});

each("parse_payment", (v) => {
  if ("raises" in v) assert.throws(() => parsePayment(v.input), { message: v.raises });
  else assert.deepEqual(parsePayment(v.input), v.output);
});

each("merge", (v) => {
  assert.deepEqual(plain(mergeFacts(v.results.map(facts), v.strict)), v.output);
});

each("extract", (v) => {
  const run = () => factsFromModel(v.data, v.request, v.deadline_days, v.today);
  if ("raises" in v) assert.throws(run, { message: v.raises });
  else assert.deepEqual(plain(run()), v.output);
});

each("interval_name", (v) => assert.equal(intervalName(v.input), v.output));
each("plain_yes", (v) => assert.equal(plainYes(v.input), v.output));

each("guard", async (v) => {
  const guard = new Guard("request", {
    payees: v.payees,
    extract: () => { throw new ExtractionError(v.error); },
  });
  guard._facts = v.facts ? facts(v.facts) : null;
  guard._error = v.facts ? "" : v.error;
  guard._agreed = v.agreed;
  guard._uncheckedApproved = v.unchecked_approved;
  const input = { allowlist: v.allowlist, payment: v.payment, spentBefore: v.spent_before };
  let purchase = v.cart;
  if (!v.cart) {
    purchase = v.purchase;
    input.find = finder(v.products);
  }
  if ("raises" in v.result) {
    await assert.rejects(guard.check(purchase, input), { message: v.result.raises });
    return;
  }
  const out = await guard.check(purchase, input);
  const expected = Object.fromEntries(Object.keys(out).map((k) => [k, v.result[k]]));
  assert.deepEqual(out, expected);
});
