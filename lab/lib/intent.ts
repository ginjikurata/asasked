// Turns a plain request ("black loafers size 42 under $400, pay with crypto") into conditions,
// then checks each product against them the way the guard checks a cart: what fits, what differs.
// Runs in the browser for site search, and on our server for the agent tools (server/).

import type { Product, Store } from "./products";

export type Intent = {
  terms: string[]; // item words that must appear in the product
  size?: string;
  color?: string;
  option?: string; // card condition, e.g. "near mint"
  budget?: number; // USD
  crypto: boolean;
};

export type Check = { fits: boolean; good: string[]; bad: string[] };

const COLORS: [RegExp, string][] = [
  [/\bdark brown\b|тёмно-коричнев[а-яё]*|темно-коричнев[а-яё]*/, "dark brown"],
  [/\bblack\b|ч[её]рн[а-яё]*/, "black"],
  [/\bbrown\b|коричнев[а-яё]*/, "brown"],
  [/\bwhite\b|бел[а-яё]*/, "white"],
  [/\bnavy\b|т[её]мно-син[а-яё]*/, "navy"],
  [/\bblue\b|син[а-яё]*|голуб[а-яё]*/, "blue"],
  [/\bgr[ae]y\b|сер[а-яё]*/, "grey"],
  [/\bgreen\b|зел[её]н[а-яё]*/, "green"],
  [/\bburgundy\b|бордов[а-яё]*/, "burgundy"],
  [/\btan\b|\bcognac\b|коньячн[а-яё]*/, "tan"],
  [/\bbeige\b|бежев[а-яё]*/, "beige"],
  [/\bred\b|красн[а-яё]*/, "red"],
];

// Colour names stores use for the same shade.
const SHADES: Record<string, string[]> = {
  "dark brown": ["dark brown", "chocolate", "espresso"],
  brown: ["brown", "chocolate", "espresso", "cognac", "tan"],
  tan: ["tan", "cognac", "camel"],
  grey: ["grey", "gray"],
  navy: ["navy"],
};

const OPTIONS: [RegExp, string][] = [
  [/\bnear mint\b|\bnm\b/, "near mint"],
  [/\blightly played\b|\blp\b/, "lightly played"],
  [/\bmoderately played\b|\bmp\b/, "moderately played"],
];

// Russian item words to the English the store catalogs use.
const RU: [RegExp, string][] = [
  [/^лофер[а-яё]*|^мокасин[а-яё]*/, "loafer"],
  [/^оксфорд[а-яё]*/, "oxford"],
  [/^дерби/, "derby"],
  [/^монк[а-яё]*/, "monk"],
  [/^челси/, "chelsea"],
  [/^ботин[а-яё]*|^сапог[а-яё]*/, "boot"],
  [/^туфл[а-яё]*|^обув[а-яё]*/, "shoes"],
  [/^замш[а-яё]*/, "suede"],
  [/^кож[а-яё]*/, "leather"],
  [/^карт[а-яё]*|^карточ[а-яё]*/, "card"],
  [/^бустер[а-яё]*/, "booster"],
  [/^колодк[а-яё]*/, "shoe trees"],
  [/^покемон[а-яё]*/, "pokemon"],
  [/^палат[а-яё]*/, "tent"],
  [/^печ[ьиек][а-яё]*|^печь$/, "stove"],
  [/^обогревател[а-яё]*/, "heater"],
];

// One lowercase word to the English word(s) the catalogs use ("обувь" → ["shoes"], "колодки" → ["shoe", "trees"]).
export const toEnglish = (w: string) => (RU.find(([re]) => re.test(w))?.[1] ?? w).split(" ");

// "Pokémon" and "Pokemon" are the same word to a shopper. Only Latin accents: NFD would break й and ё.
export const plain = (s: string) =>
  s.replace(/[éèêë]/g, "e").replace(/[áàâä]/g, "a").replace(/[íìîï]/g, "i").replace(/[óòôö]/g, "o").replace(/[úùûü]/g, "u");

const CRYPTO = /\b(crypto|cryptocurrency|bitcoin|btc|usdc|usdt|eth|ethereum|sol|solana)\b|крипт[а-яё]*|биткоин[а-яё]*/g;
const STOP = new Set(
  "buy get find want need i me my a an the pair pairs of in for with and or to some please pay paying using via size color colour купить куплю найти найди хочу нужен нужна нужны нужно мне пару пара в за с и или через оплата оплатить оплатой размер размера цвет цвета".split(" "),
);

export function parseIntent(raw: string): Intent {
  let s = ` ${plain(raw.toLowerCase()).replace(/[“”"!?;:()]/g, " ").replace(/,(?!\d)/g, " ")} `;
  const crypto = CRYPTO.test(s);
  s = s.replace(CRYPTO, " ");

  let budget: number | undefined;
  const money = "\\$?\\s*(\\d[\\d,]*(?:\\.\\d+)?)\\s*(?:\\$|usd|dollars?|долл[а-яё]*)?";
  const b =
    s.match(new RegExp(`(?:under|below|less than|max|maximum|up to|at most|within|до|не дороже|дешевле|максимум)\\s*${money}`)) ??
    s.match(/\$\s*(\d[\d,]*(?:\.\d+)?)/) ??
    s.match(/(\d[\d,]*(?:\.\d+)?)\s*(?:\$|usd|dollars?|долл[а-яё]*)/);
  if (b) {
    budget = Number(b[1].replace(/,/g, ""));
    s = s.replace(b[0], " ");
  }

  let size: string | undefined;
  const z =
    s.match(/(?:size|sz|eu|размер[а-яё]*|р\.)\s*(\d{2}(?:[.,]5)?)\b/) ?? s.match(/\b(\d{2}(?:[.,]5)?)\s*(?:size|eu|размер[а-яё]*|р\.|-?й)(?=\s)/);
  if (z) {
    size = z[1].replace(",", ".");
    s = s.replace(z[0], " ");
  } else {
    // A bare number in the usual shoe range ("loafers 42") is a size.
    const bare = s.match(/\s(3[5-9]|4[0-9])(?:[.,]5)?(?=\s)/);
    if (bare) {
      size = bare[0].trim().replace(",", ".");
      s = s.replace(bare[0], " ");
    }
  }

  let color: string | undefined;
  for (const [re, name] of COLORS) {
    const m = s.match(re);
    if (m) {
      color = name;
      s = s.replace(m[0], " ");
      break;
    }
  }

  let option: string | undefined;
  for (const [re, name] of OPTIONS) {
    const m = s.match(re);
    if (m) {
      option = name;
      s = s.replace(m[0], " ");
      break;
    }
  }

  const terms = s
    .replace(/[,.$]/g, " ")
    .split(/\s+/)
    .filter((w) => w && !STOP.has(w))
    .flatMap(toEnglish);

  return { terms, size, color, option, budget, crypto };
}

export const hasConditions = (i: Intent) => Boolean(i.size || i.color || i.option || i.budget);

// Words a product is found by: title, type, type aliases and store name. Shared by the site and the server.
const ALIAS: Record<string, string> = {
  mocassin: "loafer loafers moccasin",
  "double monk straps": "monk shoes",
  oxford: "oxfords shoes",
  derby: "derbies shoes",
  "ankle boots": "boot",
  "chelsea boots": "boot",
  stove: "stoves",
  heater: "heaters stove stoves", // someone after a tent stove wants to see the diesel heaters too
};
// Words for what a whole store sells, when its own product types are empty.
const STORE_WORDS: Record<string, string> = { "satoshitcg.com": "pokemon trading card cards tcg" };
export const searchText = (p: Product, store: Store) =>
  plain(`${p.t} ${p.k} ${ALIAS[p.k.toLowerCase()] ?? ""} ${STORE_WORDS[store.domain] ?? ""} ${store.name}`.toLowerCase());

// Accessories (laces, bags, spare parts) go below the main items in results.
export const isAccessory = (p: Product) => /accessor/i.test(p.k);

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// A word matches at the start of a word in the text: "tent" finds "tents", not "patent".
const atWord = (t: string, text: string) => new RegExp(`(^|[^a-z0-9а-яё])${esc(t)}`).test(text);

// "loafers" should find "loafer" and the other way round.
export function termMatches(term: string, text: string) {
  if (atWord(term, text)) return true;
  const stem = term.replace(/(es|s)$/, "");
  return stem !== term && stem.length >= 3 && atWord(stem, text);
}

// What the item is: its type, then the type's aliases ("stove" is a heater's alias, a Caminus's type).
const typeName = (p: Product) => plain(p.k.toLowerCase());
const aliasText = (p: Product) => ALIAS[p.k.toLowerCase()] ?? "";
// The words that name the item itself: "Hot Tent with Stove Jack" is a tent, "Floor for UP-5 Hot Tent" is a floor.
// A bundle names each of its items after a "+".
const headText = (p: Product) =>
  plain(p.t.toLowerCase())
    .split(/\s\+\s/)
    .map((part) => part.split(/\s(?:with|for)\s/)[0])
    .join(" ");

// Lower is closer. Each search word scores 0 when it is the item's type, 1 when it is a type alias or
// names the item (or an item in a bundle), 2 when it only comes up in passing: "stove" in "with Stove Jack".
export function relevance(p: Product, terms: string[]) {
  const type = typeName(p);
  const near = `${aliasText(p)} ${headText(p)}`;
  return terms.reduce((sum, w) => sum + (termMatches(w, type) ? 0 : termMatches(w, near) ? 1 : 2), 0);
}

type Opt = { label: string; inStock: boolean };

// "in stock" when an option for this size (exact or a range like 40-42) is in stock,
// "sold out" when the store lists the size but every matching option is sold out.
function sizeState(size: string, opts: Opt[]): "in stock" | "sold out" | "not listed" {
  const n = Number(size);
  const hits = opts.filter(({ label: l }) => {
    if (l === size) return true;
    const r = l.match(/^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$/);
    return r ? n >= Number(r[1]) && n <= Number(r[2]) : false;
  });
  if (!hits.length) return "not listed";
  return hits.some((o) => o.inStock) ? "in stock" : "sold out";
}

const usd = (n: number) => {
  const d = n % 1 ? 2 : 0;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
};

export function checkProduct(p: Product, store: Store, i: Intent): Check {
  const good: string[] = [];
  const bad: string[] = [];
  const title = p.t.toLowerCase();
  // An option's stock is known for WooCommerce stores; unknown counts as in stock.
  const opts: Opt[] = (p.v ?? []).map(([, l, , s]) => ({ label: l.toLowerCase(), inStock: s !== false }));

  if (i.size) {
    const s = sizeState(i.size, opts);
    if (s === "in stock") good.push(`size ${i.size}`);
    else if (s === "sold out") {
      if (p.a) bad.push(`size ${i.size} sold out`); // a fully sold-out product gets "sold out" below
    }
    else bad.push(opts.length ? `no size ${i.size}` : "no sizes listed");
  }
  if (i.color) {
    if ((SHADES[i.color] ?? [i.color]).some((c) => title.includes(c))) good.push(i.color);
    else bad.push(`not ${i.color}`);
  }
  if (i.option) {
    const hits = opts.filter((o) => o.label === i.option);
    if (hits.some((o) => o.inStock)) good.push(i.option);
    else if (hits.length) bad.push(`${i.option} sold out`);
    else bad.push(`no ${i.option}`);
  }
  if (i.budget !== undefined) {
    if (p.c && p.c !== "USD") bad.push(`priced in ${p.c}`);
    else if (p.p <= i.budget) good.push(`${usd(p.p)} ≤ ${usd(i.budget)}`);
    else bad.push(`${usd(p.p)} is over ${usd(i.budget)}`);
  }
  if (!p.a) bad.push("sold out");
  if (i.crypto && !store.payment) bad.push("crypto not confirmed");
  return { fits: bad.length === 0, good, bad };
}
