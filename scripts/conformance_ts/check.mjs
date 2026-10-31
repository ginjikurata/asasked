// Validates conformance_vectors.json with the TypeScript implementation of
// Verifiable Intent (npm "verifiable-intent", github.com/lukasjhan/verifiable-intent)
// and compares every verdict with the vector's "expected" field.
//
// Two checks per vector, as two verifiers would make them:
// - the network: verifyChain over L1, L2 and L3a with the L2 payment view.
//   This covers the signatures, the bindings and the payment constraints.
// - the merchant: verifyChain over L3b with the L2 checkout view, then the
//   checkout constraints (line_items, allowed_merchants) against the cart with
//   checkConstraints. verifyChain does not read the cart, so the merchant
//   checks it, as with the Mastercard reference SDK.
//
// Usage: node check.mjs path/to/conformance_vectors.json (right after
// generating it: L3 mandates expire in 5 minutes). Exits 1 on any mismatch.

import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { checkConstraints, parseLayer, resolveDisclosures, verifyChain } from "verifiable-intent";

const doc = JSON.parse(readFileSync(process.argv[2] ?? "conformance_vectors.json", "utf8"));
const now = Math.floor(Date.now() / 1000);
const sha = (s) => createHash("sha256").update(s, "ascii").digest("base64url");
const CONSTRAINT_FAIL = /^pair \d+ constraint violation: /;

// The vectors carry the network's L2 view only. The merchant's view is the
// same base JWT with two of its disclosures: find the pair L3b's sd_hash is over.
function checkoutView(l2Serialized, l3b) {
  const [base, ...rest] = l2Serialized.split("~");
  const discs = rest.filter(Boolean);
  for (const a of discs)
    for (const b of discs) {
      const view = `${base}~${a}~${b}~`;
      if (a !== b && sha(view) === l3b.payload.sd_hash) return view;
    }
  return null;
}

// The checkout mandate with its merchant and item references resolved.
async function checkoutConstraints(l2) {
  const byDigest = {};
  for (const d of l2.disclosureStrings) byDigest[sha(d)] = JSON.parse(Buffer.from(d, "base64url")).at(-1);
  const deref = (x) => (x && typeof x === "object" && "..." in x ? byDigest[x["..."]] : x);
  const claims = await resolveDisclosures(l2.payload, l2.disclosureStrings);
  const mandate = claims.delegate_payload.map(deref).find((d) => d?.vct === "mandate.checkout.open.1");
  const merchants = [];
  const constraints = mandate.constraints.map((c) => {
    if (c.type === "mandate.checkout.line_items")
      return { ...c, items: c.items.map((it) => ({ ...it, acceptable_items: it.acceptable_items.map(deref) })) };
    if (c.type === "mandate.checkout.allowed_merchants") {
      const allowed = c.allowed.map(deref);
      merchants.push(...allowed);
      return { ...c, allowed };
    }
    return c;
  });
  return { constraints, merchants };
}

// Python and TypeScript print lists differently ("['A']" against "A").
const norm = (s) => s.replace(/[\[\]']/g, "");

let mismatches = 0;
for (const v of doc.vectors) {
  const a = v.artifacts;
  const [l1, l2, l3a, l3b] = await Promise.all(
    [a.layer1, a.layer2, a.layer3_payment, a.layer3_checkout].map((s) => parseLayer(s)),
  );
  const resolveIssuerKey = async () => v.keys.issuer_public_jwk;

  const network = await verifyChain({
    l1, l2, l3Payment: l3a, l2PaymentSerialized: a.layer2_payment_presentation, resolveIssuerKey, now,
  });
  const view = checkoutView(a.layer2, l3b);
  const merchant = view
    ? await verifyChain({ l1, l2, l3Checkout: l3b, l2CheckoutSerialized: view, resolveIssuerKey, now })
    : { valid: false, errors: ["L2 checkout view not found for L3b"] };

  const chainErrors = [...network.errors.filter((e) => !CONSTRAINT_FAIL.test(e)), ...merchant.errors];
  const violations = network.errors
    .filter((e) => CONSTRAINT_FAIL.test(e))
    .flatMap((e) => e.replace(CONSTRAINT_FAIL, "").split("; "));
  if (chainErrors.length === 0) {
    const { constraints, merchants } = await checkoutConstraints(l2);
    const cart = checkConstraints(constraints, {
      line_items: v.input.purchase.map((p) => ({ id: p.sku, quantity: p.quantity })),
      merchant: merchants[0],
      allowed_merchants: merchants,
    });
    violations.push(...cart.violations);
  }

  const got = { chain_valid: chainErrors.length === 0, constraints_satisfied: violations.length === 0 };
  const exp = v.expected;
  const sameViolations =
    JSON.stringify(violations.map(norm).sort()) === JSON.stringify(exp.violations.map(norm).sort());
  const ok = got.chain_valid === exp.chain_valid && got.constraints_satisfied === exp.constraints_satisfied && sameViolations;
  if (!ok) mismatches++;
  console.log(
    `${ok ? "match   " : "MISMATCH"} [${v.id}] chain_valid=${got.chain_valid} ` +
      `constraints_satisfied=${got.constraints_satisfied} violations=${violations.length}` +
      (ok ? "" : `\n  got: ${JSON.stringify({ chainErrors, violations })}\n  expected: ${JSON.stringify(exp)}`),
  );
}
console.log(`${doc.vectors.length - mismatches} of ${doc.vectors.length} vectors match.`);
process.exit(mismatches ? 1 : 0);
