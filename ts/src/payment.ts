// Checks of an on-chain payment before the agent signs it. A port of
// src/asasked/payment.py.
//
// The cart check asks "is this what the person asked for?". When the agent
// pays in crypto there is a second question: "is this payment the one the
// cart and the person call for?". The wrong token, a swap that can lose a
// tenth of the money, a recipient address that is not the shop's: none of
// these show in the cart.
//
// Everything here is plain arithmetic and string comparison. Amounts,
// addresses and rates come from the caller: the shop's payment request (x402,
// Solana Pay) and the swap quote. The guard does not read the chain, fetch
// prices or sign; pass what the shop and the swap provider returned, not what
// the agent says.
//
// The binding (does the site say this address is its own?) is checked outside
// the guard, over the network, by the caller; its answer comes in as
// payment.binding: {outcome: "bound" | "excluded" | "inconclusive", reason}.
// Take it from your own check, never from the agent.

import { BLOCK, WARN, lower, ticker, type Finding, type IntentFacts, type Severity } from "./coherence.js";
import { capitalize, fixed } from "./py.js";

/** How far the payment may differ from the cart total before it counts. */
export const AMOUNT_TOLERANCE = 0.005;
/** A swap may lose this much to slippage before the payment is refused (1%). */
export const MAX_SLIPPAGE_BPS = 100;
/** Blocking findings the person's answer cannot approve: the payment must change. */
export const REFUSED_CODES: ReadonlySet<string> = new Set(["pay-recipient", "pay-excluded",
  "pay-amount", "pay-slippage", "pay-swap-short"]);
export const BINDING_OUTCOMES = ["bound", "excluded", "inconclusive"] as const;
export type BindingOutcome = typeof BINDING_OUTCOMES[number];
/** What vouched for a bound address, by binding.method. */
export const BINDING_VIA: Record<string, string> = {
  "x402-signed-manifest": " (signed list, key in its DNS)",
  "x402-payee-name": " (through the ENS name the payment request gave)",
};

export interface Binding {
  outcome: BindingOutcome;
  reason?: string | null;
  origin?: string | null;
  detail?: string | null;
  method?: string | null;
}

export interface SwapInput {
  from_token: string;
  amount_in: number;
  rate?: number | null;
  quote_out: number;
  min_out: number;
}

/** The payment, next to the cart in Guard.check(cart, {payment}). */
export interface PaymentInput {
  token: string;
  network?: string | null;
  amount: number;
  /** The recipient in the transaction. */
  to: string;
  /** The shop's address, from its payment request. */
  merchant?: string | null;
  /** One unit of token in the cart's currency. */
  rate?: number | null;
  swap?: SwapInput | null;
  max_slippage_bps?: number | null;
  binding?: Binding | null;
}

export interface Payment {
  token: string;
  network: string | null;
  amount: number;
  to: string;
  merchant: string | null;
  rate: number | null;
  swap: { from_token: string; amount_in: number; rate: number | null; quote_out: number;
    min_out: number } | null;
  max_slippage_bps: number;
  binding: { outcome: BindingOutcome; reason: string | null; origin: string | null;
    detail: string | null; method: string | null } | null;
}

/** A finding no answer of the person's can approve (see REFUSED_CODES). */
export function refused(finding: Finding): boolean {
  return finding.severity === BLOCK && REFUSED_CODES.has(finding.code);
}

function num(value: unknown, where: string, required = false): number | null {
  if ((value === null || value === undefined) && !required) return null;
  if (typeof value !== "number" || !(value > 0)) {
    throw new Error(`payment: ${where} must be a number above zero`);
  }
  return value;
}

function text(value: unknown, where: string, required = false): string | null {
  if ((value === null || value === undefined) && !required) return null;
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`payment: ${where} must be a non-empty string`);
  }
  return value.trim();
}

const str = (v: unknown) => (typeof v === "string" ? v : null);

function binding(value: unknown): Payment["binding"] {
  if (value === null || value === undefined) return null;
  const v = value as Record<string, unknown>;
  if (typeof v !== "object" || Array.isArray(v)
    || !(BINDING_OUTCOMES as readonly unknown[]).includes(v.outcome)) {
    throw new Error(`payment: binding must be a dict with outcome ${BINDING_OUTCOMES.join(", ")}`);
  }
  const reason = v.reason;
  return {
    outcome: v.outcome as BindingOutcome,
    reason: typeof reason === "string" && reason.trim() ? reason.trim() : null,
    origin: str(v.origin), detail: str(v.detail), method: str(v.method),
  };
}

/** A caller's payment -> the same, checked and in one spelling. null is no
 * payment. Anything malformed throws: a payment the guard cannot read must not
 * pass as checked. */
export function parsePayment(value: unknown): Payment | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new Error("payment must be a dict (see asasked.payment)");
  }
  const v = value as Record<string, unknown>;
  const payment: Payment = {
    token: ticker(text(v.token, "token", true))!,
    network: lower(text(v.network, "network")),
    amount: num(v.amount, "amount", true)!,
    to: text(v.to, "to", true)!,
    merchant: text(v.merchant, "merchant"),
    rate: num(v.rate, "rate"),
    swap: null,
    max_slippage_bps: MAX_SLIPPAGE_BPS,
    binding: binding(v.binding),
  };
  const bps = v.max_slippage_bps;
  if (bps !== null && bps !== undefined) {
    if (typeof bps !== "number" || !(bps >= 0 && bps <= 10000)) {
      throw new Error("payment: max_slippage_bps must be a number from 0 to 10000");
    }
    payment.max_slippage_bps = bps;
  }
  const swap = v.swap;
  if (swap !== null && swap !== undefined) {
    if (typeof swap !== "object" || Array.isArray(swap)) {
      throw new Error("payment: swap must be a dict or null");
    }
    const s = swap as Record<string, unknown>;
    payment.swap = {
      from_token: ticker(text(s.from_token, "swap.from_token", true))!,
      amount_in: num(s.amount_in, "swap.amount_in", true)!,
      rate: num(s.rate, "swap.rate"),
      quote_out: num(s.quote_out, "swap.quote_out", true)!,
      min_out: num(s.min_out, "swap.min_out", true)!,
    };
    if (payment.swap.min_out > payment.swap.quote_out) {
      throw new Error("payment: swap.min_out cannot be above swap.quote_out");
    }
  }
  return payment;
}

/** EVM addresses are hex and their case is only a checksum; base58 addresses
 * are case-sensitive. A CAIP-10 account id ("eip155:8453:0x…") counts by its address. */
export function sameAddress(a: string, b: string): boolean {
  a = a.slice(a.lastIndexOf(":") + 1);
  b = b.slice(b.lastIndexOf(":") + 1);
  if (a.toLowerCase().startsWith("0x") && b.toLowerCase().startsWith("0x")) {
    return a.toLowerCase() === b.toLowerCase();
  }
  return a === b;
}

const amount = (x: number) => fixed(x, 6, true).replace(/0+$/, "").replace(/\.$/, "");
const money = (cents: number) => `$${fixed(cents / 100, 2, true)}`;

export interface PaymentCheckOptions {
  /** The cart check already found the cart over the limit: don't repeat it. */
  overLimit?: boolean;
  /** Addresses the person approved: the money may go only there. */
  payees?: readonly string[];
  /** What was already paid for the same request. */
  spentBeforeCents?: number;
}

/** Findings on the payment, in the same form as the cart's. */
export function checkPayment(facts: IntentFacts, payment: Payment | null, totalCents: number,
  opts: PaymentCheckOptions = {}): Finding[] {
  const payees = opts.payees ?? [];
  const sev = (name: string): Severity =>
    (facts.soft.has(name) || facts.disputed.has(name) ? WARN : BLOCK);
  const f = (code: string, severity: Severity, text: string): Finding => ({ code, severity, text });

  const found: Finding[] = [];
  if (payment === null) {
    const wanted = [facts.pay_with, facts.pay_network && capitalize(facts.pay_network)]
      .filter(Boolean).join(" on ");
    if (wanted) {
      const name = facts.pay_with ? "pay_with" : "pay_network";
      found.push(f("pay-unchecked", sev(name),
        `You asked to pay with ${wanted}; I can't see how this order will be paid.`));
    }
    return found;
  }

  const swap = payment.swap;
  const b = payment.binding;
  const outcome = b ? b.outcome : null;
  const site = b ? (b.origin || "the site") : "";
  const why = b && b.reason ? ` (${b.reason})` : "";

  if (outcome === "excluded") {
    found.push(f("pay-excluded", BLOCK, `The signed list of payment addresses that ${site} `
      + `publishes leaves out ${payment.to}${why}.`));
  }
  if (payees.length) {
    if (!payees.some((p) => sameAddress(payment.to, p))) {
      found.push(f("pay-recipient", BLOCK, `The payment goes to ${payment.to}, which is not an `
        + `address the person approved (${payees.join(", ")}).`));
    } else if (payment.merchant !== null && !sameAddress(payment.to, payment.merchant)) {
      found.push(f("unchecked", WARN, `The shop's payment request names ${payment.merchant}, not `
        + `the approved address ${payment.to}; the shop may not see this payment.`));
    }
  } else if (payment.merchant === null && outcome === null) {
    found.push(f("unchecked", WARN,
      "The shop's payment address wasn't given, so I couldn't check who receives the money."));
  } else if (payment.merchant !== null && !sameAddress(payment.to, payment.merchant)) {
    found.push(f("pay-recipient", BLOCK,
      `The payment goes to ${payment.to}, not to the shop's address ${payment.merchant}.`));
  } else if (outcome === "bound") {
    const via = (b!.method && BINDING_VIA[b!.method]) || "";
    found.push(f("pay-seller-unverified", WARN, `${site} lists ${payment.to} as its own address`
      + `${via}, so the money goes to that site. Whether ${site} is a genuine seller that `
      + "will deliver was not checked."));
  } else if (outcome === "inconclusive") {
    found.push(f("pay-unbound", WARN, `Couldn't confirm that ${payment.to} belongs to ${site}${why}; `
      + "the address comes only from the payment request, so a forged request would not be caught."));
  } else if (outcome === null) {
    found.push(f("pay-unpinned", WARN, "The shop's address comes from its payment request, not "
      + "from an address the person approved, so a forged request would not be caught."));
  }

  const given = swap ? swap.from_token : payment.token;
  if (facts.pay_with && given !== facts.pay_with) {
    found.push(f("pay-token", sev("pay_with"),
      `Asked to pay with ${facts.pay_with}, the payment uses ${given}.`));
  }

  if (facts.pay_network) {
    if (payment.network === null) {
      found.push(f("unchecked", WARN, `Asked to pay on ${capitalize(facts.pay_network)}; `
        + "the payment doesn't say which network."));
    } else if (payment.network !== facts.pay_network) {
      found.push(f("pay-network", sev("pay_network"), `Asked to pay on `
        + `${capitalize(facts.pay_network)}, the payment goes out on ${capitalize(payment.network)}.`));
    }
  }

  let overpaid = false;
  if (payment.rate === null) {
    found.push(f("unchecked", WARN, `No ${payment.token} rate was given, so I couldn't check the `
      + "payment against the order total."));
  } else {
    const paid = payment.amount * payment.rate * 100;
    const slack = Math.max(1, totalCents * AMOUNT_TOLERANCE);
    const shown = `${amount(payment.amount)} ${payment.token} (about ${money(paid)})`;
    if (paid > totalCents + slack) {
      overpaid = true;
      found.push(f("pay-amount", BLOCK, `The payment is ${shown}, the order total is ${money(totalCents)}.`));
    } else if (paid < totalCents - slack) {
      found.push(f("pay-amount", WARN, `The payment is ${shown}, less than the order total of `
        + `${money(totalCents)}; the shop may refuse it.`));
    }
  }

  if (facts.explicit_max_cents && !opts.overLimit && !overpaid) {
    const rate = swap ? swap.rate : payment.rate;
    if (rate !== null) {
      const paidIn = swap ? swap.amount_in : payment.amount;
      const spent = paidIn * rate * 100;
      const earlier = Math.max(0, opts.spentBeforeCents ?? 0);
      if (spent + earlier > facts.explicit_max_cents + 1e-6) {
        const before = earlier ? `, with ${money(earlier)} already paid for this request` : "";
        found.push(f("pay-max", sev("explicit_max_cents"),
          `Set a limit of ${money(facts.explicit_max_cents)}; paying takes `
          + `${amount(paidIn)} ${given}, about ${money(spent)}${before}.`));
      }
    }
  }

  if (swap) {
    const loss = (swap.quote_out - swap.min_out) / swap.quote_out * 10000;
    if (loss > payment.max_slippage_bps) {
      found.push(f("pay-slippage", BLOCK, `The swap from ${swap.from_token} to ${payment.token} `
        + `may give up to ${fixed(loss / 100, 2)}% less than quoted (allowed: `
        + `${fixed(payment.max_slippage_bps / 100, 2)}%).`));
    }
    if (swap.min_out < payment.amount) {
      found.push(f("pay-swap-short", BLOCK, `The swap guarantees only ${amount(swap.min_out)} `
        + `${payment.token}, the payment needs ${amount(payment.amount)}.`));
    }
  }
  return found;
}
