// Small helpers that reproduce Python behaviour the checks depend on, so the
// TypeScript guard writes the same messages and makes the same choices as the
// Python one (tests/vectors.json holds the Python answers).

/** Python truthiness: None, False, 0, "", [] and {} are false. */
export function truthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === "number") return value !== 0 && !Number.isNaN(value);
  if (typeof value === "string") return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (value instanceof Set || value instanceof Map) return value.size > 0;
  if (typeof value === "object") return Object.keys(value as object).length > 0;
  return true;
}

/** Python ==, where True == 1 and False == 0. */
export function eq(a: unknown, b: unknown): boolean {
  const num = (v: unknown) => (typeof v === "boolean" ? Number(v) : v);
  a = num(a ?? null);
  b = num(b ?? null);
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => eq(v, b[i]));
  }
  return a === b;
}

/** A key under which values equal in Python land in one set slot. */
export function key(value: unknown): string {
  value = value ?? null;
  if (typeof value === "boolean") return `n:${Number(value)}`;
  if (typeof value === "number") return `n:${value}`;
  if (typeof value === "string") return `s:${value}`;
  if (Array.isArray(value)) return `a:[${value.map(key).join(",")}]`;
  return JSON.stringify(value);
}

/** str.split() with no argument. */
export function words(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
}

/** str.capitalize(). */
export function capitalize(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1).toLowerCase() : text;
}

/** repr() of a tuple of ints and Nones: "(0, None)", "(None,)". */
export function reprTuple(values: readonly (number | null)[]): string {
  const parts = values.map((v) => (v === null ? "None" : String(v)));
  return parts.length === 1 ? `(${parts[0]},)` : `(${parts.join(", ")})`;
}

/** Python's built-in round(): halves go to the even neighbour. */
export function round(x: number): number {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

/** Python's f"{x:.{digits}f}" (with grouping: f"{x:,.{digits}f}"). Rounds the
 * exact binary value, ties to even, as Python does. */
export function fixed(x: number, digits: number, grouping = false): string {
  if (!Number.isFinite(x)) return String(x);
  const negative = x < 0 || Object.is(x, -0);
  const exact = Math.abs(x).toFixed(100);
  const [whole, frac] = exact.split(".");
  const head = BigInt(whole + frac.slice(0, digits));
  const rest = frac.slice(digits);
  let n = head;
  const first = rest[0] ?? "0";
  const beyond = /[1-9]/.test(rest.slice(1));
  if (first > "5" || (first === "5" && beyond) || (first === "5" && !beyond && n % 2n === 1n)) {
    n += 1n;
  }
  let s = n.toString().padStart(digits + 1, "0");
  let int = digits ? s.slice(0, -digits) : s;
  const dec = digits ? s.slice(-digits) : "";
  if (grouping) int = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  s = digits ? `${int}.${dec}` : int;
  return negative ? `-${s}` : s;
}

/** itertools.permutations(range(n), k), in itertools order. */
export function* permutations(n: number, k: number): Generator<number[]> {
  if (k > n) return;
  const used = new Array<boolean>(n).fill(false);
  const current: number[] = [];
  function* step(): Generator<number[]> {
    if (current.length === k) {
      yield current.slice();
      return;
    }
    for (let i = 0; i < n; i++) {
      if (used[i]) continue;
      used[i] = true;
      current.push(i);
      yield* step();
      current.pop();
      used[i] = false;
    }
  }
  yield* step();
}

export function factorial(n: number): number {
  let out = 1;
  for (let i = 2; i <= n; i++) out *= i;
  return out;
}

/** math.perm(n, k). */
export function perm(n: number, k: number): number {
  if (k > n) return 0;
  let out = 1;
  for (let i = n - k + 1; i <= n; i++) out *= i;
  return out;
}

/** The first item with the largest key, like Python's max(..., key=). */
export function maxBy<T>(items: readonly T[], by: (item: T) => number): T {
  let best = items[0];
  let bestKey = by(best);
  for (const item of items.slice(1)) {
    const k = by(item);
    if (k > bestKey) {
      best = item;
      bestKey = k;
    }
  }
  return best;
}

/** sorted() of strings: by code point, as Python compares them. */
export function sorted(values: Iterable<string>): string[] {
  return [...values].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

/** repr() of a JSON value, as Python error texts show it: None, True, 'text'. */
export function repr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : value > 0 ? "inf" : value < 0 ? "-inf" : "nan";
  if (typeof value === "string") {
    const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
    const body = value.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/\r/g, "\\r")
      .replace(/\t/g, "\\t").replace(quote === "'" ? /'/g : /"/g, `\\${quote}`);
    return `${quote}${body}${quote}`;
  }
  if (Array.isArray(value)) return `[${value.map(repr).join(", ")}]`;
  if (typeof value === "object") {
    return `{${Object.entries(value as object).map(([k, v]) => `${repr(k)}: ${repr(v)}`).join(", ")}}`;
  }
  return String(value);
}
