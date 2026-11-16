// The guard before payment. A port of src/asasked/guard.py (without the
// Verifiable Intent mandate parts).
//
// The agent has filled a cart. Before payment the guard checks it against the
// person's words and answers:
//
//   proceed: the cart matches the request, payment can go ahead;
//   ask:     there is a mismatch; here is a ready question for the person;
//   refuse:  the payment itself is wrong (recipient, amount, slippage) and no
//            answer of the person's can approve it.
//
// Models extract facts from the request (two independent ones; disputed facts
// do not block), and deterministic code makes the decision. If the facts
// cannot be extracted, the guard asks the person rather than letting the
// purchase through.
//
//   const guard = new Guard("black running shoes, size 42, by Friday");
//   const result = await guard.check([{ name: "Nike Pegasus 41", brand: "Nike",
//     color: "Triple Black", size: "42", price: 129.99, quantity: 1,
//     returnable: true, delivery_days: 3 }]);
//   result.decision  // "proceed" | "ask" | "refuse"; result.question for the person
//
// So that the agent cannot pay around the guard, the check goes into payment:
//
//   const pay = guard.protect(checkout, (order) => order.items);
//
// The person's answer is passed on by your code, guard.answer(message), not
// by the agent: otherwise the agent could "agree" on the person's behalf.

import {
  ASK, BLOCK, PROCEED, checkAgreedRenewals, decideBeforePurchase, extractIntentAgreed,
  intentFacts, questionFor, renewalTerms, type Decision, type Find, type Finding, type IntentFacts,
  type Product, type Purchase, type RenewalTerms,
} from "./coherence.js";
import { ExtractionError } from "./extract.js";
import { checkPayment, parsePayment, refused, type Payment, type PaymentInput } from "./payment.js";
import { fixed, round, words } from "./py.js";

/** The third decision, for a payment no answer of the person's can approve. */
export const REFUSE = "refuse";

/** What the agent sees instead of payment. */
export const NOT_PAID = "NOT PAID. The order doesn't match what the person asked for. "
  + "Show the person this question as it is and wait for their reply; "
  + "do not try to pay again before they answer.\n\n{question}";

/** A refused payment: the agent is told to change the payment instead. */
export const REFUSED = "NOT PAID. This payment can't be made as it is, and no answer from the person "
  + "can approve it:\n{reasons}\nChange the payment itself: pay the address on the "
  + "shop's invoice, the amount of the order, with any swap kept within the allowed "
  + "slippage and guaranteed to cover the amount. Do not ask the person to approve "
  + "this payment.";
export const UNCHECKED = "I couldn't automatically check this order against your request:";
export const ALSO_ASK = "\n\nThe order also doesn't match what the person asked for. Show the person "
  + "this question as it is and wait for their reply before paying:\n\n{question}";

/** A cart line as an agent developer has it. Prices in the shop's currency units. */
export interface CartItem {
  name: string;
  price: number;
  quantity?: number;
  brand?: string | null;
  color?: string | null;
  size?: string | number | null;
  level?: string | null;
  category?: string | null;
  returnable?: boolean | null;
  delivery_days?: number | null;
  units?: number;
  /** {every: "month", price: 12.99}: renews and charges again; price optional. */
  recurring?: { every: string; price?: number | null } | null | false;
}

export interface GuardResult {
  decision: typeof PROCEED | typeof ASK | typeof REFUSE;
  reasons: string[];
  refused: string[];
  question: string | null;
  notes: string[];
  error?: string;
}

const isNum = (v: unknown): v is number => typeof v === "number" && !Number.isNaN(v);

function cartItem(i: number, item: CartItem): [string, Product, number] {
  if (!item || !item.name) throw new Error(`cart[${i}]: the item needs a name (name)`);
  const price = item.price;
  if (!isNum(price) || !(price >= 0)) {
    throw new Error(`cart[${i}]: the item needs a price (price), a number not below zero`);
  }
  const quantity = item.quantity ?? 1;
  if (!Number.isInteger(quantity) || quantity < 1) {
    throw new Error(`cart[${i}]: quantity must be an integer from 1`);
  }
  const product: Product = {
    sku: `cart-${i}`,
    name: item.name,
    brand: item.brand ?? null,
    color: item.color ?? null,
    size_label: item.size === null || item.size === undefined ? null : String(item.size),
    level: item.level ?? null,
    category: item.category ?? null,
    price_cents: round(price * 100),
    refundable: item.returnable ?? null,
    ships_in_days: item.delivery_days ?? null,
    units: item.units ?? 1,
    recurring: recurring(i, item.recurring),
  };
  return [product.sku!, product, quantity];
}

function recurring(i: number, value: CartItem["recurring"]): Product["recurring"] {
  if (value === null || value === undefined || value === false) return null;
  if (typeof value !== "object" || typeof value.every !== "string" || !value.every.trim()) {
    throw new Error(`cart[${i}]: recurring is {"every": "month", "price": 12.99} (price optional) or null`);
  }
  const price = value.price;
  if (price !== null && price !== undefined && (!isNum(price) || !(price >= 0))) {
    throw new Error(`cart[${i}]: recurring price must be a number not below zero`);
  }
  return { every: value.every.trim(),
    price_cents: price === null || price === undefined ? null : round(price * 100) };
}

function renews(product: Product): string {
  const r = product.recurring;
  if (!r) return "";
  const cents = r.price_cents ?? product.price_cents;
  return `, then $${fixed(cents / 100, 2)} every ${r.every}`;
}

const MARKS = /the\s+(person|agent)\s+(answered|added|asked)\s*:/giu;

/** The agent's words on one line and without the marks that label the
 * person's words: otherwise the agent could pass its words off as theirs. */
function quoted(agentText: string): string {
  return words(agentText).join(" ").replace(MARKS, "[...]");
}

const YES = new Set(["yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "confirmed",
  "approve", "approved", "да", "ага", "ок", "окей", "хорошо", "конечно", "давай",
  "подтверждаю", "согласен", "согласна"]);
const FILLER = new Set(["go", "ahead", "please", "fine", "buy", "pay", "it", "that", "is", "do",
  "покупай", "оплачивай", "плати", "бери", "можно", "пожалуйста", "оформляй"]);

/** A bare "yes" read by plain code, for when the models that read answers are down. */
export function plainYes(answer: string): boolean {
  const found = answer.toLowerCase().match(/\p{L}+/gu) ?? [];
  return found.length > 0 && found.length <= 6 && found.some((w) => YES.has(w))
    && found.every((w) => YES.has(w) || FILLER.has(w));
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];

/** A date in words ("Saturday, 31 October 2026"); by default today, local time. */
export function todayInWords(d: Date = new Date()): string {
  return `${DAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export interface GuardOptions {
  /** Today's date in words; defaults to this machine's date. */
  today?: string;
  /** Which models extract facts; by default every one with a key set. */
  providers?: string[];
  /** How to get facts from the request; by default, model agreement. */
  extract?: (request: string) => IntentFacts | Promise<IntentFacts>;
  /** Payment addresses the person approved: a payment may go only there. */
  payees?: string | readonly string[];
}

export interface CheckInput {
  /** With find: the purchase is a list of [sku, quantity] in your catalog. */
  find?: Find;
  /** The approved skus (the mandate's allowlist), for "cheap". */
  allowlist?: readonly string[];
  /** The on-chain payment the agent is about to sign. */
  payment?: PaymentInput | null;
  /** Already paid earlier for this same request, in the cart's currency. */
  spentBefore?: number;
}

export class Guard {
  request: string;
  today: string;
  providers?: string[];
  extract?: GuardOptions["extract"];
  payees: string[];
  checks: Record<string, unknown>[] = [];
  private _facts: IntentFacts | null = null;
  private _error = "";
  private _asked: string | null = null;
  private _uncheckedShown: string | null = null;
  private _uncheckedApproved: string | null = null;
  private _offered: RenewalTerms = {};
  private _agreed: RenewalTerms = {};

  constructor(request: string, opts: GuardOptions = {}) {
    this.request = request;
    this.today = opts.today ?? todayInWords();
    this.providers = opts.providers;
    this.extract = opts.extract;
    const payees = typeof opts.payees === "string" ? [opts.payees] : opts.payees ?? [];
    this.payees = payees.filter((p) => typeof p === "string" && p.trim()).map((p) => p.trim());
  }

  get error(): string {
    return this._error;
  }

  private async _extract(text: string): Promise<IntentFacts> {
    if (this.extract) return this.extract(text);
    return extractIntentAgreed(text, { today: this.today, providers: this.providers });
  }

  /** Facts are extracted once per request, not on every check. */
  async facts(): Promise<IntentFacts | null> {
    if (this._facts === null && !this._error) {
      try {
        this._facts = await this._extract(this.request);
      } catch (e) {
        if (!(e instanceof ExtractionError)) throw e;
        this._error = e.message;
      }
    }
    return this._facts;
  }

  /** The person answered the agent's question: the clarification joins their request. */
  hear(question: string, answer: string): void {
    this.request = `${this.request}\n\n(The agent asked: ${quoted(question)}\n`
      + `The person answered: ${answer})`;
    this._facts = null;
    this._error = "";
    this._agreed = { ...this._agreed, ...this._offered };
  }

  /** Checks a cart (and the payment, if any) against the request. */
  async check(purchase: readonly CartItem[] | Purchase, input: CheckInput = {}): Promise<GuardResult> {
    const spentBefore = input.spentBefore ?? 0;
    if (!isNum(spentBefore) || !(spentBefore >= 0)) {
      throw new Error("spent_before must be a number not below zero");
    }
    // Not rounded to cents: a thousand payments of a tenth of a cent are a dollar.
    const earlier = spentBefore * 100;
    let find = input.find;
    let lines: Purchase;
    if (!find) {
      const items = (purchase as readonly CartItem[]).map((item, i) => cartItem(i, item));
      const products = new Map(items.map(([sku, product]) => [sku, product]));
      lines = items.map(([sku, , qty]) => [sku, qty] as const);
      find = (sku) => {
        const p = products.get(sku);
        if (!p) throw new Error(`unknown sku ${sku}`);
        return p;
      };
    } else {
      lines = purchase as Purchase;
    }
    const payment = parsePayment(input.payment);
    const total = lines.reduce((s, [sku, qty]) => s + find!(sku).price_cents * qty, 0);
    const changed = checkAgreedRenewals(this._agreed, lines, find);
    this._offered = renewalTerms(lines, find);
    const facts = await this.facts();
    let result: GuardResult;
    if (facts === null) {
      const refusals = checkPayment(intentFacts(), payment, total, { payees: this.payees })
        .filter(refused);
      const items = lines.map(([sku, qty]) => {
        const p = find!(sku);
        return `  - ${p.name} ×${qty}, $${fixed(p.price_cents / 100, 2)} each${renews(p)}`;
      }).join("\n");
      this._uncheckedShown = items;
      if (items === this._uncheckedApproved && !refusals.length && !changed.length) {
        result = {
          decision: PROCEED, reasons: [], refused: [], question: null,
          notes: ["Not checked against the request automatically: the person "
            + "approved this order as it was shown to them."],
          error: this._error,
        };
        this.record(lines, result, payment);
        return result;
      }
      result = {
        decision: refusals.length ? REFUSE : ASK,
        reasons: ["The request could not be checked automatically.",
          ...[...changed, ...refusals].map((f) => f.text)],
        refused: refusals.map((f) => f.text),
        question: `${UNCHECKED}\n${items}\nShould I go ahead with it?`,
        notes: [],
        error: this._error,
      };
    } else {
      let decision: Decision = decideBeforePurchase(facts, lines, find, {
        allowlist: input.allowlist, spentBeforeCents: earlier,
      });
      if (changed.length) {
        // Said once, in the "you agreed" form.
        const tails = changed.filter((c) => c.text.includes("this one "))
          .map((c) => c.text.slice(c.text.indexOf("this one ") + "this one ".length));
        const kept = decision.reasons.filter((f) => !(f.code === "recurring-interval"
          && tails.some((t) => f.text.endsWith(t))));
        decision = withReasons([...kept, ...changed], decision.notes);
      }
      const over = [...decision.reasons, ...decision.notes].some((f) => f.code === "explicit-max");
      const paying = checkPayment(facts, payment, total, {
        overLimit: over, payees: this.payees, spentBeforeCents: earlier,
      });
      const refusals = paying.filter(refused);
      if (paying.length) {
        // The person is asked only what their answer can settle.
        const reasons = [...decision.reasons,
          ...paying.filter((f) => f.severity === BLOCK && !refused(f))];
        decision = withReasons(reasons,
          [...decision.notes, ...paying.filter((f) => f.severity !== BLOCK)]);
      }
      result = {
        decision: refusals.length ? REFUSE : decision.action,
        reasons: [...decision.reasons, ...refusals].map((f) => f.text),
        refused: refusals.map((f) => f.text),
        question: decision.question,
        notes: decision.notes.map((f) => f.text),
      };
    }
    this.record(lines, result, payment);
    return result;
  }

  private record(lines: Purchase, result: GuardResult, payment: Payment | null): void {
    this.checks.push({ purchase: lines.map(([s, q]) => [s, q]), ...result,
      ...(payment ? { payment } : {}) });
  }

  /** The person's message after the guard's question: called by your code, not the agent. */
  answer(text: string): void {
    if (this._asked === null) {
      this.request = `${this.request}\n\n(The person added: ${text})`;
      this._facts = null;
      this._error = "";
    } else {
      if (this._asked.startsWith(UNCHECKED) && plainYes(text)) {
        this._uncheckedApproved = this._uncheckedShown;
      }
      this.hear(this._asked, text);
      this._asked = null;
    }
  }

  /** null: payment can go ahead; otherwise the text for the agent instead of payment. */
  async gate(cart: readonly CartItem[], payment: PaymentInput | null = null,
    spentBefore = 0): Promise<string | null> {
    const result = await this.check(cart, { payment, spentBefore });
    if (result.decision === PROCEED) return null;
    this._asked = result.question;
    if (result.decision === REFUSE) {
      const reasons = result.refused.map((t) => `  - ${t}`).join("\n");
      const told = REFUSED.replace("{reasons}", () => reasons);
      return this._asked ? told + ALSO_ASK.replace("{question}", () => this._asked!) : told;
    }
    return NOT_PAID.replace("{question}", () => result.question!);
  }

  /** Payment that asks the guard first. cart (and payment, if given) get the
   * same arguments as pay. While the cart differs from the request, pay is not
   * called and the text for the agent is returned instead. */
  protect<A extends unknown[], R>(pay: (...args: A) => R | Promise<R>,
    cart: (...args: A) => readonly CartItem[],
    payment?: (...args: A) => PaymentInput | null): (...args: A) => Promise<R | string> {
    return async (...args: A) => {
      const blocked = await this.gate(cart(...args), payment ? payment(...args) : null);
      return blocked ? blocked : pay(...args);
    };
  }
}

function withReasons(reasons: Finding[], notes: Finding[]): Decision {
  const action = reasons.length ? ASK : PROCEED;
  return { action, reasons, notes, question: action === ASK ? questionFor(reasons) : null };
}
