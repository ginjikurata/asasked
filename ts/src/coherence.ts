// Checking intent against the cart. A port of src/asasked/coherence.py.
//
// The design is split in two halves:
//
//   1) EXTRACTION turns a person's words into a set of facts. A language
//      model works here (extract.ts), and only here.
//   2) THE CHECK compares the facts with the cart and gives a verdict. This is
//      ordinary deterministic code: reproducible, explainable and fit to attach
//      to a dispute ("the person asked to be able to return it, the item is
//      final sale", not "the AI decided so").

import { ExtractionError, agreeProviders, callModel } from "./extract.js";
import { SOFTENABLE_FIELDS, WEEKDAYS } from "./prompt.js";
import {
  eq, factorial, fixed, key, maxBy, perm, permutations, reprTuple, sorted, truthy, words,
  repr,
} from "./py.js";

export const BLOCK = "block";
export const WARN = "warn";
export type Severity = typeof BLOCK | typeof WARN;

const SOFTENABLE = new Set(SOFTENABLE_FIELDS);

/** One item of a multi-item request: the LINE_FIELDS that are its own. */
export type Line = {
  brand?: string;
  model?: string;
  color?: string;
  size_label?: string;
  quantity?: number;
  needs_refundable?: boolean;
  deadline_days?: number;
};

/** What the person asked for, as facts. Field names follow the Python
 * library, so facts and vectors move between the two unchanged. */
export interface IntentFacts {
  brand: string | null;
  /** Excluded brands: "anything but Wilson". */
  brand_not: string[];
  /** The model as the person named it: "EZONE 98". */
  model: string | null;
  color: string | null;
  size_label: string | null;
  level: string | null;
  /** "cheap" | "premium". */
  price_preference: string | null;
  explicit_max_cents: number | null;
  quantity: number | null;
  needs_refundable: boolean;
  deadline_days: number | null;
  /** The person asked for a subscription or agreed to one. */
  wants_recurring: boolean;
  /** How often that subscription renews: "month", "2 week", "year". */
  recurring_every: string | null;
  /** The period a spending limit is for ("up to $10 a month" -> "month"). */
  max_every: string | null;
  /** Token ticker in upper case without "$" ("USDC"), checked against the payment. */
  pay_with: string | null;
  /** Chain, lower case ("solana"). */
  pay_network: string | null;
  raw: string;
  /** Fields the person marked as optional or approximate: a mismatch warns. */
  soft: Set<string>;
  /** Fields the extraction models disagreed on: a mismatch warns. */
  disputed: Set<string>;
  /** Several different items or variants in one order. */
  lines: Line[];
  /** Requirements no field holds, in the person's words: musts... */
  other: string[];
  /** ...and nice-to-haves. */
  other_optional: string[];
}

export function intentFacts(init: Partial<IntentFacts> = {}): IntentFacts {
  return {
    brand: null, brand_not: [], model: null, color: null, size_label: null, level: null,
    price_preference: null, explicit_max_cents: null, quantity: null,
    needs_refundable: false, deadline_days: null, wants_recurring: false,
    recurring_every: null, max_every: null, pay_with: null, pay_network: null, raw: "",
    soft: new Set(), disputed: new Set(), lines: [], other: [], other_optional: [],
    ...init,
  };
}

export const LINE_FIELDS = ["brand", "model", "color", "size_label", "quantity",
  "needs_refundable", "deadline_days"] as const;

export interface Finding {
  code: string;
  severity: Severity;
  text: string;
}

export interface Verdict {
  coherent: boolean;
  findings: Finding[];
}

/** An item as the shop describes it. Unknown features are null or absent. */
export interface Product {
  sku?: string;
  name: string;
  price_cents: number;
  brand?: string | null;
  color?: string | null;
  size_label?: string | null;
  level?: string | null;
  refundable?: boolean | null;
  ships_in_days?: number | null;
  category?: string | null;
  units?: number;
  recurring?: { every: string; price_cents?: number | null } | null;
  [extra: string]: unknown;
}

export type Find = (sku: string) => Product;
export type Purchase = ReadonlyArray<readonly [string, number]>;

const finding = (code: string, severity: Severity, text: string): Finding =>
  ({ code, severity, text });

// ---------------------------------------------------------------------------
// 1. Extraction
// ---------------------------------------------------------------------------

function plausible(data: Record<string, unknown>): boolean {
  const below = (name: string, low: number) => {
    const value = data[name];
    return typeof value === "number" && Number.isInteger(value) && value < low;
  };
  return !(below("deadline_days", 0) || below("explicit_max_cents", 1));
}

const show = repr;

function asInt(value: unknown, field: string): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") {
    throw new ExtractionError(`Field ${field}: expected a number, got bool ${show(value)}`);
  }
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (typeof value === "string" && /^-?\d+$/.test(value.trim())) return parseInt(value.trim(), 10);
  throw new ExtractionError(`Field ${field}: expected an integer, got ${show(value)}`);
}

function asStr(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  throw new ExtractionError(`Field ${field}: expected a string, got ${show(value)}`);
}

function asStrList(value: unknown, field: string): string[] {
  if (value === null || value === undefined) return [];
  if (!Array.isArray(value) || !value.every((v) => typeof v === "string")) {
    throw new ExtractionError(`Field ${field}: expected a list of strings, got ${show(value)}`);
  }
  return [...value];
}

function asLines(value: unknown, today?: string | null): Line[] {
  if (value === null || value === undefined) return [];
  if (!Array.isArray(value)) throw new ExtractionError(`Field lines: expected a list, got ${show(value)}`);
  const lines: Line[] = [];
  for (const raw of value) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      throw new ExtractionError(`Field lines: expected an object, got ${show(raw)}`);
    }
    const r = raw as Record<string, unknown>;
    const allowed = new Set<string>([...LINE_FIELDS, "deadline_weekday"]);
    const unknown = sorted(Object.keys(r).filter((k) => !allowed.has(k)));
    if (unknown.length) throw new ExtractionError(`Field lines: unknown fields ${show(unknown)}`);
    const line: Record<string, unknown> = {};
    for (const k of ["brand", "model", "color", "size_label"]) line[k] = asStr(r[k], `lines.${k}`);
    line.quantity = asInt(r.quantity, "lines.quantity");
    // Only "yes": "no" on a line means "not asked for", not "no returns".
    line.needs_refundable = truthy(r.needs_refundable) ? true : null;
    // A line's deadline works like the shared one: code counts a named day, not the model.
    line.deadline_days = asInt(r.deadline_days, "lines.deadline_days");
    const counted = daysUntil(asStr(r.deadline_weekday, "lines.deadline_weekday"), today);
    if (counted !== null) line.deadline_days = counted;
    lines.push(Object.fromEntries(Object.entries(line).filter(([, v]) => v !== null)) as Line);
  }
  // a single line is not "several variants", just facts
  return lines.length > 1 ? lines : [];
}

function asSoftSet(value: unknown): Set<string> {
  if (value === null || value === undefined) return new Set();
  if (!Array.isArray(value)) {
    throw new ExtractionError(`Field soft_fields: expected a list, got ${show(value)}`);
  }
  // Other conditions carry their own softness (optional); the model sometimes
  // repeats it here, which is not an extraction error.
  const names = value.filter((v) => v !== "other_conditions");
  const unknown = names.filter((v) => !SOFTENABLE.has(v));
  if (unknown.length) {
    throw new ExtractionError(`Field soft_fields: unknown field names ${show(unknown)}`);
  }
  return new Set(names as string[]);
}

/** The model's other_conditions -> [musts, nice-to-haves], without repeats. */
function asConditions(value: unknown): [string[], string[]] {
  if (value === null || value === undefined) return [[], []];
  if (!Array.isArray(value)) {
    throw new ExtractionError(`Field other_conditions: expected a list, got ${show(value)}`);
  }
  const required: string[] = [];
  const optional: string[] = [];
  for (const raw of value) {
    if (typeof raw !== "object" || raw === null || typeof raw.text !== "string") {
      throw new ExtractionError(`Field other_conditions: expected an object with text, got ${show(raw)}`);
    }
    const text = words(raw.text).join(" ");
    const target = truthy(raw.optional) ? optional : required;
    const seen = new Set([...required, ...optional].map((t) => t.toLowerCase()));
    if (text && !seen.has(text.toLowerCase())) target.push(text);
  }
  return [required, optional];
}

/** Days from today to the named weekday, that day included. today is the date
 * in words, starting with the weekday ("Monday, 2 November 2026"). From
 * Monday, "by Friday" is 4 days and "by Monday" is 7. */
export function daysUntil(weekday: string | null | undefined, today: string | null | undefined): number | null {
  if (!weekday || !today) return null;
  const first = today.split(",")[0].trim().toLowerCase();
  const target = WEEKDAYS.indexOf(weekday.toLowerCase());
  const from = WEEKDAYS.indexOf(first);
  if (from < 0 || target < 0) return null;
  return ((target - from) % 7 + 7) % 7 || 7;
}

/** The model's raw answer -> IntentFacts, or ExtractionError. */
export function factsFromModel(data: Record<string, unknown>, request: string,
  deadlineDays: number | null = null, today: string | null = null): IntentFacts {
  let level = asStr(data.level, "level");
  if (level === "advanced") level = "pro";
  let modelDeadline = asInt(data.deadline_days, "deadline_days");
  // Models turn "by Friday" into days differently (4 or 5). The model only
  // names the day; code counts the days to it.
  const counted = daysUntil(asStr(data.deadline_weekday, "deadline_weekday"), today);
  if (counted !== null) modelDeadline = counted;
  const [other, otherOptional] = asConditions(data.other_conditions);
  return canonical(intentFacts({
    raw: request,
    deadline_days: deadlineDays !== null ? deadlineDays : modelDeadline,
    brand: asStr(data.brand, "brand"),
    brand_not: asStrList(data.brand_not, "brand_not"),
    model: asStr(data.model, "model"),
    color: asStr(data.color, "color"),
    size_label: asStr(data.size_label, "size_label"),
    level,
    price_preference: asStr(data.price_preference, "price_preference"),
    explicit_max_cents: asInt(data.explicit_max_cents, "explicit_max_cents"),
    quantity: asInt(data.quantity, "quantity"),
    needs_refundable: truthy(data.needs_refundable ?? false),
    wants_recurring: truthy(data.wants_recurring ?? false),
    recurring_every: intervalName(asStr(data.recurring_every, "recurring_every")),
    max_every: intervalName(asStr(data.max_every, "max_every")),
    pay_with: ticker(asStr(data.pay_with, "pay_with")),
    pay_network: lower(asStr(data.pay_network, "pay_network")),
    soft: asSoftSet(data.soft_fields),
    lines: asLines(data.lines, today),
    other,
    other_optional: otherOptional,
  }));
}

export interface ExtractOptions {
  /** A deadline in days given by the caller; wins over the model's. */
  deadlineDays?: number | null;
  /** "gemini" | "anthropic" | "openai_compat". */
  provider?: string;
  /** Today's date in words ("Saturday, 31 October 2026"), for "by Friday". */
  today?: string | null;
}

/** Extracts facts from a person's request with a language model. */
export async function extractIntent(request: string, opts: ExtractOptions = {}): Promise<IntentFacts> {
  const today = opts.today ?? null;
  let data = await callModel(request, opts.provider, today);
  if (!plausible(data)) {
    // Seen in a run on 2026-11-11: for a few minutes a model filled deadlines
    // of -1 days and limits of a cent into requests that named neither.
    // Asked again, it answered null. One more try, then fail.
    data = await callModel(request, opts.provider, today);
    if (!plausible(data)) {
      throw new ExtractionError("The model returned a negative deadline or a limit "
        + `below one cent: ${show(data)}`);
    }
  }
  return factsFromModel(data, request, opts.deadlineDays ?? null, today);
}

// How long each interval is, in days. A month is 365.25 / 12 days, so twelve
// of them make exactly a year.
const INTERVAL_DAYS: Record<string, number> = {
  day: 1.0, week: 7.0, fortnight: 14.0, month: 365.25 / 12, quarter: 365.25 / 4, year: 365.25,
};
const INTERVAL_WORDS: Record<string, string> = {
  daily: "day", weekly: "week", biweekly: "2 week", monthly: "month", quarterly: "quarter",
  yearly: "year", annually: "year", annual: "year", annum: "year", mo: "month", wk: "week",
  yr: "year",
};
const INTERVAL = /^(?:every\s+|per\s+|a\s+|an\s+|each\s+)?(?:(\d+)\s*)?([a-z]+?)s?$/;
const has = (o: Record<string, unknown>, k: string) => Object.prototype.hasOwnProperty.call(o, k);

/** "month", "2 weeks", "monthly", "every 3 months" -> days; null if not understood. */
export function intervalDays(text: string | null | undefined): number | null {
  let t = words((text ?? "").toLowerCase().replaceAll("-", " ")).join(" ");
  if (has(INTERVAL_WORDS, t)) t = INTERVAL_WORDS[t];
  const match = INTERVAL.exec(t);
  if (!match) return null;
  const count = match[1];
  let unit = match[2];
  if (has(INTERVAL_WORDS, unit)) unit = INTERVAL_WORDS[unit];
  if (unit.includes(" ")) return intervalDays(unit); // "biweekly" -> "2 week"
  if (!has(INTERVAL_DAYS, unit)) return null;
  return parseInt(count || "1", 10) * INTERVAL_DAYS[unit];
}

/** One spelling for an interval, so two models' answers compare: "Monthly" -> "month". */
export function intervalName(value: string | null | undefined): string | null {
  const v = words((value ?? "").toLowerCase()).join(" ");
  if (!v) return null;
  const days = intervalDays(v);
  if (days === null) return v;
  for (const unit of ["year", "quarter", "month", "fortnight", "week", "day"]) {
    const count = days / INTERVAL_DAYS[unit];
    if (Math.abs(count - Math.round(count)) < 1e-9 && Math.round(count) >= 1) {
      const n = Math.round(count);
      if (unit === "fortnight") return "2 week";
      if (unit === "quarter") return "3 month";
      return n === 1 ? unit : `${n} ${unit}`;
    }
  }
  return v;
}

export function sameInterval(a: string | null | undefined, b: string | null | undefined): boolean {
  const da = intervalDays(a);
  const db = intervalDays(b);
  if (da === null || db === null) return intervalName(a) === intervalName(b);
  return Math.abs(da - db) < 1e-9;
}

/** How many times a subscription renewing every `every` charges in the worst
 * `period`: weekly in a month is 5. At least once. */
function chargesIn(every: string, period: string | null): number {
  const days = intervalDays(every);
  const span = intervalDays(period);
  if (!days || !span) return 1;
  return Math.max(1, Math.ceil(span / days - 1e-9));
}

/** "$asasked " -> "ASASKED": one spelling for a token, whoever wrote it. */
export function ticker(value: string | null | undefined): string | null {
  const v = (value ?? "").trim().replace(/^\$+/, "").trim().toUpperCase();
  return v || null;
}

export function lower(value: string | null | undefined): string | null {
  const v = (value ?? "").trim().toLowerCase();
  return v || null;
}

const SHARED_LINE_FIELDS = ["brand", "model", "color", "size_label", "needs_refundable",
  "deadline_days"] as const;

/** One form for one meaning, so that two models' answers can be compared:
 * whatever every line shares moves to the top, and a total quantity next to
 * lines is dropped (it is already in the lines). */
export function canonical(facts: IntentFacts): IntentFacts {
  if (!facts.lines.length) return facts;
  const top: Record<string, unknown> = {};
  const lines = facts.lines.map((line) => ({ ...line })) as Record<string, unknown>[];
  for (const name of SHARED_LINE_FIELDS) {
    const values = new Map<string, unknown>();
    for (const line of lines) values.set(key(line[name]), line[name] ?? null);
    const shared = values.size === 1 ? [...values.values()][0] : null;
    const current = (facts as unknown as Record<string, unknown>)[name];
    // needs_refundable on top is False when not asked for: that means "not set"
    if (shared !== null && (eq(current, null) || eq(current, false) || eq(current, shared))) {
      top[name] = shared;
      for (const line of lines) delete line[name];
    } else if (!(eq(current, null) || eq(current, false))) {
      for (const line of lines) if (eq(line[name], current)) delete line[name];
    }
  }
  const kept = lines.filter((line) => Object.keys(line).length) as Line[];
  return { ...facts, ...top, quantity: null, lines: kept.length > 1 ? kept : [] };
}

export const COMPARED_FIELDS = [
  "brand", "brand_not", "model", "color", "size_label", "level", "price_preference",
  "explicit_max_cents", "quantity", "needs_refundable", "deadline_days", "wants_recurring",
  "recurring_every", "max_every", "pay_with", "pay_network",
] as const;

/** How Guard.hear marks the person's answer inside the request. */
export const ANSWERED = "\nThe person answered: ";

const STRICTEST_WINS = new Set(["deadline_days", "explicit_max_cents"]);

function norm(value: unknown): unknown {
  if (Array.isArray(value)) return sorted(value.map((v: string) => v.toLowerCase()));
  return typeof value === "string" ? value.toLowerCase() : value ?? null;
}

const field = (facts: IntentFacts, name: string) =>
  (facts as unknown as Record<string, unknown>)[name];

/** Merges facts from several models into one set. See merge_facts in
 * coherence.py for the reasoning behind each rule. */
export function mergeFacts(results: IntentFacts[], strict = false): IntentFacts {
  if (!results.length) throw new Error("mergeFacts: no results at all");
  const recounted = strict && new Set(results.map((r) => r.lines.length)).size > 1;
  if (recounted) results = [...results].sort((a, b) => b.lines.length - a.lines.length);
  const first = results[0];
  const values: Record<string, unknown> = {};
  const disputed = new Set<string>();
  for (const name of COMPARED_FIELDS) {
    const found = results.map((r) => field(r, name));
    if (new Set(found.map((v) => key(norm(v)))).size === 1) {
      values[name] = found[0];
      continue;
    }
    // A deadline and an amount limit: the strictest found, without a dispute.
    if (STRICTEST_WINS.has(name)) {
      values[name] = Math.min(...(found.filter((v) => v !== null) as number[]));
      continue;
    }
    // A brand excluded by any model is excluded.
    if (name === "brand_not") {
      values[name] = sorted(new Set((found as string[][]).flat()));
      continue;
    }
    if (name === "wants_recurring") {
      values[name] = false;
      continue;
    }
    // The interval agreed to: if the models heard different ones, none matches.
    if (name === "recurring_every") {
      const heard = sorted(new Set(found.filter((v) => v !== null) as string[]));
      values[name] = heard.length === 1 ? heard[0] : heard.join(" | ");
      continue;
    }
    // The period of a limit: the longest heard is the strictest.
    if (name === "max_every") {
      const heard = found.filter((v) => v !== null) as string[];
      values[name] = maxBy(heard, (v) => intervalDays(v) || 0);
      continue;
    }
    if (!strict) disputed.add(name);
    if (name === "needs_refundable") values[name] = found.some(truthy);
    else if (recounted) values[name] = found[0];
    else values[name] = found.find((v) => v !== null) ?? null;
  }
  let lines = maxBy(results.map((r) => r.lines), (l) => l.length);
  if (recounted) {
    lines = first.lines;
  } else if (new Set(results.map((r) => r.lines.length)).size > 1) {
    disputed.add("lines");
    disputed.add("line_count");
  } else if (lines.length) {
    const aligned = results.map((r) => alignLines(first.lines, r.lines));
    const merged: Line[] = [];
    for (let i = 0; i < Math.min(...aligned.map((a) => a.length)); i++) {
      const group = aligned.map((a) => a[i] as Record<string, unknown>);
      const keys = sorted(new Set(group.flatMap((line) => Object.keys(line))));
      for (const k of keys) {
        if (new Set(group.map((line) => key(norm(line[k])))).size > 1 && !strict) {
          disputed.add("lines");
          disputed.add(`lines.${k}`);
        }
      }
      const out: Record<string, unknown> = {};
      for (const k of keys) {
        const hit = group.find((line) => line[k] !== undefined && line[k] !== null);
        if (hit) out[k] = hit[k];
      }
      merged.push(out as Line);
    }
    lines = merged;
  }
  const other = maxBy(results.map((r) => r.other), (o) => o.length);
  if (other.length && !results.every((r) => r.other.length) && !strict) disputed.add("other");
  const optional: string[] = [];
  for (const r of results) {
    const seen = new Set([...other, ...optional].map((o) => o.toLowerCase()));
    optional.push(...r.other_optional.filter((t) => !seen.has(t.toLowerCase())));
  }
  return intentFacts({
    ...values,
    raw: first.raw,
    other,
    other_optional: optional,
    soft: mergedSoft(results, strict),
    disputed,
    lines,
  });
}

/** Any model's soft fields; when strict, only those every model let go of. */
function mergedSoft(results: IntentFacts[], strict: boolean): Set<string> {
  const soft = new Set(results.flatMap((r) => [...r.soft]));
  if (!strict) return soft;
  const compared = new Set<string>(COMPARED_FIELDS);
  return new Set([...soft].filter((f) => results.every(
    (r) => r.soft.has(f) || (compared.has(f) && !truthy(field(r, f))))));
}

/** The other model's lines in the order of base's lines, by the most matching fields. */
function alignLines(base: Line[], other: Line[]): Line[] {
  if (factorial(other.length) > MAX_ASSIGNMENTS) return other;
  const agree = (order: Line[]) => {
    let n = 0;
    for (let i = 0; i < Math.min(base.length, order.length); i++) {
      const a = base[i] as Record<string, unknown>;
      const b = order[i] as Record<string, unknown>;
      for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
        if (eq(norm(a[k]), norm(b[k]))) n++;
      }
    }
    return n;
  };
  const orders = [...permutations(other.length, other.length)].map((p) => p.map((i) => other[i]));
  return maxBy(orders, agree);
}

export interface AgreedOptions extends Omit<ExtractOptions, "provider"> {
  providers?: string[];
  /** Defaults to whether the request holds the person's answer (ANSWERED). */
  strict?: boolean;
}

/** Extracts facts with several independent models and merges them: a fact the
 * models disagree on goes into disputed and warns instead of stopping. */
export async function extractIntentAgreed(request: string, opts: AgreedOptions = {}): Promise<IntentFacts> {
  const strict = opts.strict ?? request.includes(ANSWERED);
  const providers = opts.providers ?? agreeProviders();
  if (!providers.length) {
    throw new ExtractionError("no model key: set CLAUDE_API_KEY, LLM_API_KEY (Gemini) "
      + "or OPENAI_COMPAT_API_KEY");
  }
  const results: IntentFacts[] = [];
  for (const provider of providers) results.push(await extractIntent(request, { ...opts, provider }));
  return mergeFacts(results, strict);
}

// ---------------------------------------------------------------------------
// 2. The check: deterministic
// ---------------------------------------------------------------------------

function wordSet(text: string): Set<string> {
  return new Set(text.toLowerCase().match(/[a-z0-9]+/g) ?? []);
}

/** Every word of the named model is in the item's name. A brand in it is fine. */
function modelMatches(product: Product, model: string): boolean {
  const brand = wordSet(product.brand || "");
  const name = wordSet(product.name);
  const wanted = [...wordSet(model)].filter((w) => !brand.has(w));
  return wanted.length > 0 && wanted.every((w) => name.has(w));
}

function suits(product: Product, facts: IntentFacts): boolean {
  return !itemFindings(product, facts, () => BLOCK).some((f) => f.code !== "unchecked");
}

// Russian colour names, matched by the start of the word. Order matters:
// "серебристый" (silver) before "серый" (grey).
const RU_COLORS: [string, string][] = [["черн", "black"], ["бел", "white"], ["син", "blue"],
  ["голуб", "blue"], ["желт", "yellow"], ["серебр", "silver"], ["красн", "red"],
  ["зелен", "green"], ["сер", "grey"], ["розов", "pink"], ["коричн", "brown"], ["беж", "beige"],
  ["оранж", "orange"], ["фиолет", "purple"]];

function colorWords(text: string): string[] {
  const found = text.toLowerCase().replaceAll("ё", "е").match(/\p{L}+/gu) ?? [];
  return found.map((w) => {
    if (w === "gray") w = "grey";
    return RU_COLORS.find(([ru]) => w.startsWith(ru))?.[1] ?? w;
  });
}

// Python's \b is Unicode-aware; JavaScript's is not, even with the u flag.
const W = "[\\p{L}\\p{N}_]";
const COLOR_SPLIT = new RegExp(
  `/|,|&|\\+|${["with", "and", "и", "с"].map((w) => `(?<!${W})${w}(?!${W})`).join("|")}`, "u");

/** The item's colour against the one the person named: "yes", "second" or "no". */
function colorMatch(have: string, want: string): "yes" | "second" | "no" {
  const wanted = colorWords(want);
  if (!wanted.length) return "no";
  const parts = have.toLowerCase().split(COLOR_SPLIT).filter((p) => p.trim());
  for (let i = 0; i < parts.length; i++) {
    const got = new Set(colorWords(parts[i]));
    if (wanted.every((w) => got.has(w))) return i === 0 ? "yes" : "second";
  }
  return "no";
}

const SIZE_SYSTEMS = new Set(["eu", "us", "uk", "fr", "it", "jp", "ru"]);
const SIZE_FILLER = new Set(["size", "sz", "размер", "р"]);
const SIZE_WORDS: Record<string, string> = { small: "s", medium: "m", large: "l" };

function sizeParts(text: string): [Set<string>, string[]] {
  const tokens = text.toLowerCase().replaceAll(",", ".")
    .match(/\p{Nd}+\/\p{Nd}+|\p{Nd}+(?:\.\p{Nd}+)?|\p{L}+/gu) ?? [];
  const systems = new Set(tokens.filter((t) => SIZE_SYSTEMS.has(t)));
  const rest = tokens.filter((t) => !SIZE_SYSTEMS.has(t) && !SIZE_FILLER.has(t))
    .map((t) => (has(SIZE_WORDS, t) ? SIZE_WORDS[t] : t.endsWith(".0") ? t.slice(0, -2) : t));
  return [systems, rest];
}

/** "EU 42" = "42", "42,5" = "42.5", "Medium" = "M"; size systems must agree if both name one. */
function sameSize(have: string, want: string): boolean {
  const [haveSys, haveRest] = sizeParts(have);
  const [wantSys, wantRest] = sizeParts(want);
  if (haveSys.size && wantSys.size
    && (haveSys.size !== wantSys.size || [...haveSys].some((s) => !wantSys.has(s)))) return false;
  return wantRest.length > 0 && eq(haveRest, wantRest);
}

const money = (cents: number) => `$${fixed(cents / 100, 2)}`;

type Sev = (field: string) => Severity;

/** Mismatches of one item with the facts (shared ones or one line's). A
 * feature the shop did not give is an "unchecked" note, not a mismatch. */
function itemFindings(product: Product, facts: IntentFacts, sev: Sev): Finding[] {
  const out: Finding[] = [];
  const name = product.name;
  const unknown = (k: string, what: string) => {
    if (product[k] !== null && product[k] !== undefined) return false;
    out.push(finding("unchecked", WARN, `Asked for ${what}; the order doesn't say: ${name}.`));
    return true;
  };

  const brand = product.brand;
  if (facts.brand && !unknown("brand", facts.brand)
    && brand!.toLowerCase() !== facts.brand.toLowerCase()) {
    out.push(finding("brand", sev("brand"), `Asked for ${facts.brand}, the item is ${brand}: ${name}.`));
  }

  if (facts.brand_not.length && !facts.brand) {
    unknown("brand", `anything but ${facts.brand_not.join(", ")}`);
  }
  if (brand && facts.brand_not.some((b) => b.toLowerCase() === brand.toLowerCase())) {
    out.push(finding("brand-excluded", sev("brand_not"),
      `Asked for anything but ${facts.brand_not.join(", ")}, the item is ${brand}: ${name}.`));
  }

  if (facts.model && !modelMatches(product, facts.model)) {
    out.push(finding("model", sev("model"),
      `Asked for the ${facts.model}, the item is a different model: ${name}.`));
  }

  if (facts.color && !unknown("color", facts.color)) {
    const match = colorMatch(product.color!, facts.color);
    if (match !== "yes") {
      const second = match === "second" ? ` (${facts.color} only as a second colour)` : "";
      out.push(finding("color", sev("color"),
        `Asked for ${facts.color}, the item is ${product.color}${second}: ${name}.`));
    }
  }

  // an empty size means the item has no sizes at all (a can of balls)
  if (facts.size_label && !unknown("size_label", `size ${facts.size_label}`)
    && product.size_label && !sameSize(product.size_label, facts.size_label)) {
    out.push(finding("size", sev("size_label"),
      `Asked for size ${facts.size_label}, the item is size ${product.size_label}: ${name}.`));
  }

  if (facts.level && !unknown("level", `${facts.level} level`)
    && product.level !== facts.level && product.level !== "any") {
    out.push(finding("level", sev("level"),
      `Asked for ${facts.level} level, the item is ${product.level} level: ${name}.`));
  }

  if (facts.needs_refundable && !unknown("refundable", "something returnable")
    && !truthy(product.refundable)) {
    out.push(finding("refund", sev("needs_refundable"),
      `Asked to be able to return it, the item is final sale: ${name}.`));
  }

  // Not "unchecked" when the shop says nothing, and never soft or disputed.
  const recurring = product.recurring;
  if (truthy(recurring) && !facts.wants_recurring) {
    out.push(finding("recurring", BLOCK, "Not a one-time purchase: a subscription that charges "
      + `${money(renewalCents(product))} every ${recurring!.every}: ${name}.`));
  } else if (truthy(recurring) && facts.recurring_every && !facts.recurring_every.split(" | ")
    .every((every) => sameInterval(recurring!.every, every))) {
    out.push(finding("recurring-interval", BLOCK,
      `Agreed to a subscription every ${facts.recurring_every}, this one charges `
      + `${money(renewalCents(product))} every ${recurring!.every}: ${name}.`));
  }

  if (facts.deadline_days !== null
    && !unknown("ships_in_days", `delivery within ${facts.deadline_days} days`)
    && product.ships_in_days! > facts.deadline_days) {
    out.push(finding("deadline", sev("deadline_days"),
      `Needed within ${facts.deadline_days} days, the item ships in ${product.ships_in_days} days: ${name}.`));
  }
  return out;
}

/** What a subscription charges each time; the item's price if no separate one. */
function renewalCents(product: Product): number {
  const cents = product.recurring?.price_cents;
  return cents === null || cents === undefined ? product.price_cents : cents;
}

export type RenewalTerms = Record<string, [string, number]>;

/** The subscriptions in an order: sku -> [every, cents per renewal]. */
export function renewalTerms(purchase: Purchase, find: Find): RenewalTerms {
  const out: RenewalTerms = {};
  for (const [sku] of purchase) {
    const product = find(sku);
    if (truthy(product.recurring)) out[sku] = [product.recurring!.every, renewalCents(product)];
  }
  return out;
}

/** A subscription the person agreed to holds its interval and renewal price. */
export function checkAgreedRenewals(agreed: RenewalTerms, purchase: Purchase, find: Find): Finding[] {
  if (!Object.keys(agreed).length) return [];
  const out: Finding[] = [];
  for (const [sku, [every, cents]] of Object.entries(renewalTerms(purchase, find))) {
    const name = find(sku).name;
    const seen = has(agreed, sku) ? [agreed[sku]] : Object.values(agreed);
    const same = seen.filter(([e]) => sameInterval(e, every)).map(([, c]) => c);
    if (!same.length) {
      const was = sorted(new Set(seen.map(([e]) => e))).join(" or ");
      out.push(finding("recurring-changed", BLOCK, `You agreed to a subscription every ${was}; `
        + `this one charges ${money(cents)} every ${every}: ${name}.`));
    } else if (cents > Math.max(...same)) {
      out.push(finding("recurring-changed", BLOCK, `You agreed to ${money(Math.max(...same))} `
        + `every ${every}; this subscription renews at ${money(cents)}: ${name}.`));
    }
  }
  return out;
}

function describe(line: Line): string {
  const parts: (string | null | undefined)[] = [line.brand, line.model, line.color,
    line.size_label ? `size ${line.size_label}` : null,
    line.quantity ? `×${line.quantity}` : null];
  if (!(line.brand || line.model)) parts.unshift("one more item");
  return parts.filter(Boolean).join(" ");
}

/** How many assignments of cart lines to request lines to try. */
export const MAX_ASSIGNMENTS = 50_000;

/** Each line of the request gets its own cart line, none extra, none missing. */
function checkLines(facts: IntentFacts, items: [Product, number][], sev: Sev): Finding[] {
  const countSev = (code: string): Severity =>
    facts.soft.has("lines") || (code === "extra" && facts.disputed.has("line_count")) ? WARN : BLOCK;
  const lineSev = (i: number): Sev => (name) => {
    if (facts.disputed.has(`lines.${name}`)
      || (facts.disputed.has("line_count") && name in facts.lines[i])) return WARN;
    return sev(name);
  };

  const lineFacts = facts.lines.map((line) => ({ ...facts, lines: [], ...line }) as IntentFacts);
  // The search grows factorially; such an order goes to the person.
  if (perm(items.length + lineFacts.length, lineFacts.length) > MAX_ASSIGNMENTS) {
    return [finding("lines", BLOCK, `Too many items to check automatically (${lineFacts.length} `
      + `asked for, ${items.length} in the order).`)];
  }

  const pairFindings = (i: number, j: number): Finding[] => {
    const [product, qty] = items[j];
    const out = itemFindings(product, lineFacts[i], lineSev(i));
    const units = (product.units ?? 1) * qty;
    const want = lineFacts[i].quantity;
    if (want !== null && want !== undefined && units !== want) {
      out.push(finding("quantity", lineSev(i)("quantity"),
        `Asked for ${want} of ${describe(facts.lines[i])}, the order has ${units}: ${product.name}.`));
    }
    return out;
  };

  const cost = (assignment: (number | null)[]): [number, number] => {
    const found: Finding[] = [];
    assignment.forEach((j, i) => { if (j !== null) found.push(...pairFindings(i, j)); });
    const used = new Set(assignment.filter((j) => j !== null));
    const missing = assignment.filter((j) => j === null).length;
    const blocking = found.filter((f) => f.severity === BLOCK).length;
    const unmatched = missing + items.length - used.size;
    return [blocking + unmatched, found.length + unmatched];
  };

  const slots: (number | null)[] = [...items.keys(), ...lineFacts.map(() => null)];
  const seen = new Set<string>();
  let best: (number | null)[] = [];
  let bestKey: [number, number, string] | null = null;
  for (const p of permutations(slots.length, lineFacts.length)) {
    const a = p.map((i) => slots[i]);
    const repr = reprTuple(a);
    if (seen.has(repr)) continue;
    seen.add(repr);
    const [c0, c1] = cost(a);
    if (bestKey === null || c0 < bestKey[0] || (c0 === bestKey[0]
      && (c1 < bestKey[1] || (c1 === bestKey[1] && repr < bestKey[2])))) {
      best = a;
      bestKey = [c0, c1, repr];
    }
  }

  const out: Finding[] = [];
  best.forEach((j, i) => {
    if (j === null) {
      out.push(finding("missing", countSev("missing"),
        `Asked for ${describe(facts.lines[i])}; nothing in the order matches it.`));
    } else {
      out.push(...pairFindings(i, j));
    }
  });
  const used = new Set(best.filter((j) => j !== null));
  items.forEach(([product], j) => {
    if (!used.has(j)) out.push(finding("extra", countSev("extra"), `Not asked for: ${product.name}.`));
  });
  return out;
}

export interface CheckOptions {
  /** The approved skus: needed to tell "expensive" from "nothing cheaper". */
  allowlist?: readonly string[];
  /** What was already paid earlier for the same request: the limit is for all of it. */
  spentBeforeCents?: number;
}

/** Does this purchase (a list of [sku, quantity]) match the facts? */
export function checkCoherence(facts: IntentFacts, purchase: Purchase, find: Find,
  opts: CheckOptions = {}): Verdict {
  const allowlist = opts.allowlist ?? [];
  const sev: Sev = (name) => (facts.soft.has(name) || facts.disputed.has(name) ? WARN : BLOCK);
  const findings: Finding[] = [];
  const items: [Product, number][] = purchase.map(([sku, qty]) => [find(sku), qty]);
  const total = items.reduce((s, [p, q]) => s + p.price_cents * q, 0);

  if (facts.lines.length) {
    findings.push(...checkLines(facts, items, sev));
  } else {
    for (const [product] of items) findings.push(...itemFindings(product, facts, sev));
  }

  // price: was a cheaper matching option available
  if (facts.price_preference === "cheap" && items.length === 1 && !facts.lines.length) {
    const [chosen] = items[0];
    const cheaper = allowlist.map(find).filter((p) =>
      (p.category ?? null) === (chosen.category ?? null)
      && suits(p, facts)
      && p.price_cents < chosen.price_cents * 0.85);
    if (cheaper.length) {
      const best = cheaper.reduce((a, b) => (b.price_cents < a.price_cents ? b : a));
      findings.push(finding("price", sev("price_preference"),
        `Asked for something cheap; this costs ${money(chosen.price_cents)} `
        + `while ${best.name} fits too at ${money(best.price_cents)}.`));
    }
  }

  // A subscription counts at what it charges each time, whichever is more; a
  // limit for a period counts every charge in that period.
  const charged = (p: Product) => (truthy(p.recurring)
    ? renewalCents(p) * chargesIn(p.recurring!.every, facts.max_every) : 0);
  const limited = items.reduce((s, [p, q]) => s + Math.max(p.price_cents, charged(p)) * q, 0);
  const earlier = Math.max(0, opts.spentBeforeCents ?? 0);
  // A millionth of a cent of slack, for sums of sub-cent payments in floats.
  if (facts.explicit_max_cents && limited + earlier > facts.explicit_max_cents + 1e-6) {
    const per = facts.max_every ? ` a ${facts.max_every}` : "";
    let renewing = "";
    if (limited !== total) {
      renewing = facts.max_every ? ` in renewals over a ${facts.max_every}` : " at the subscription price";
    }
    const before = earlier ? `, and ${money(earlier)} was already paid for this request` : "";
    findings.push(finding("explicit-max", sev("explicit_max_cents"),
      `Set a limit of ${money(facts.explicit_max_cents)}${per}, `
      + `the order costs ${money(limited)}${renewing}${before}.`));
  }

  // quantity in the units the person counts; fewer than asked is a mismatch too
  if (facts.quantity !== null && facts.quantity !== undefined && !facts.lines.length) {
    const bought = items.reduce((s, [p, q]) => s + (p.units ?? 1) * q, 0);
    if (bought !== facts.quantity) {
      findings.push(finding("quantity", sev("quantity"),
        `Asked for ${facts.quantity}, the order has ${bought}.`));
    }
  }

  // requirements with no field: not checked, not lost either; the person decides
  for (const text of facts.other) {
    findings.push(finding("other", sev("other"),
      `You asked for “${text}”; I can't check that from the order details.`));
  }
  for (const text of facts.other_optional) {
    findings.push(finding("other", WARN, `Wished for “${text}” if possible; not checked against the order.`));
  }
  return { coherent: !findings.some((f) => f.severity === BLOCK), findings };
}

export const ASK = "ask";
export const PROCEED = "proceed";

export interface Decision {
  action: typeof ASK | typeof PROCEED;
  /** BLOCK findings: the reason to ask. */
  reasons: Finding[];
  /** WARN findings: can proceed, but the person sees them. */
  notes: Finding[];
  /** A ready question to the person if asking was decided; null otherwise. */
  question: string | null;
}

export function questionFor(reasons: Finding[]): string {
  const bullets = reasons.map((f) => `  - ${f.text}`).join("\n");
  return `Before I buy this, please check:\n${bullets}\nShould I still go ahead?`;
}

/** The same check, before the agent presses "buy": BLOCK findings stop it. */
export function decideBeforePurchase(facts: IntentFacts, purchase: Purchase, find: Find,
  opts: CheckOptions = {}): Decision {
  const verdict = checkCoherence(facts, purchase, find, opts);
  const reasons = verdict.findings.filter((f) => f.severity === BLOCK);
  const notes = verdict.findings.filter((f) => f.severity === WARN);
  const action = reasons.length ? ASK : PROCEED;
  return { action, reasons, notes, question: action === ASK ? questionFor(reasons) : null };
}
