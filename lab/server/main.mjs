// AsAsked Lab server: wallet sign-in, profile, agent access and the MCP endpoint.
// No dependencies (Node 24+: node:sqlite, type stripping for ../lib/intent.ts).
// In production Caddy serves the static site and forwards /api/* and /mcp here.
//   LAB_PORT     port on 127.0.0.1 (default 3103)
//   LAB_ORIGIN   the site's origin, used in sign-in texts and links (default https://lab.asasked.dev)
//   LAB_DATA     folder for the SQLite file (default server/data)
//   LAB_PRODUCTS path to products.json (default ../public/products.json)
//   LAB_STATIC   for local checks only: also serve this folder (e.g. out/) like Caddy does
//   LAB_LLM      the chat's model: stub (rules only, default) or claude; its LAB_CLAUDE_* and LAB_FALLBACK_* settings are in chat.mjs
import { createServer } from "node:http";
import { createPublicKey, randomBytes, verify } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve, sep } from "node:path";
import { ORIGIN, catalog, stores } from "./catalog.mjs";
import { handle } from "./mcp.mjs";
import { chatTurn } from "./chat.mjs";
import * as orders from "./orders.mjs";
import { clear as clearStoreCart } from "./woo.mjs";
import * as S from "./store.mjs";

const PORT = Number(process.env.LAB_PORT ?? 3103);
const SECURE = ORIGIN.startsWith("https://");
const HOST = new URL(ORIGIN).host;
const COOKIE = "lab_s";
const MAX_BODY = 64 * 1024;

// --- helpers ---------------------------------------------------------------------------------

const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58(s) {
  if (typeof s !== "string" || !/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s)) return null;
  let n = 0n;
  for (const ch of s) n = n * 58n + BigInt(B58.indexOf(ch));
  const bytes = [];
  while (n > 0n) {
    bytes.unshift(Number(n & 0xffn));
    n >>= 8n;
  }
  for (const ch of s) {
    if (ch !== "1") break;
    bytes.unshift(0);
  }
  return Buffer.from(bytes);
}
const isAddress = (a) => base58(a)?.length === 32;

// Ed25519: a Solana address is the raw public key.
function signedBy(address, text, signatureB64) {
  try {
    const raw = base58(address);
    const sig = Buffer.from(String(signatureB64), "base64");
    if (raw?.length !== 32 || sig.length !== 64) return false;
    const key = createPublicKey({ key: { kty: "OKP", crv: "Ed25519", x: raw.toString("base64url") }, format: "jwk" });
    return verify(null, Buffer.from(text, "utf8"), key, sig);
  } catch {
    return false;
  }
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function send(res, status, body, headers = {}) {
  const data = body === undefined ? "" : JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers });
  res.end(data);
}

// allowArray: /mcp answers a JSON-RPC batch with its own error, so it takes arrays through.
async function body(req, allowArray = false) {
  if (!/^application\/json\b/i.test(req.headers["content-type"] ?? "")) throw new HttpError(415, "Send JSON.");
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw new HttpError(413, "Too large.");
    chunks.push(c);
  }
  let v;
  try {
    v = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
  } catch {
    throw new HttpError(400, "Bad JSON.");
  }
  // Every route reads fields off an object: null, a number or an array is a bad request, not a crash.
  if (!v || typeof v !== "object" || (Array.isArray(v) && !allowArray)) throw new HttpError(400, "Bad JSON.");
  return v;
}

const cookies = (req) =>
  Object.fromEntries((req.headers.cookie ?? "").split(/;\s*/).filter(Boolean).map((c) => [c.slice(0, c.indexOf("=")), c.slice(c.indexOf("=") + 1)]));
const cookie = (value, maxAge) =>
  `${COOKIE}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${SECURE ? "; Secure" : ""}`;

// X-Forwarded-For is trusted only behind our own Caddy (LAB_TRUST_PROXY=1); otherwise anyone could fake it.
const TRUST_PROXY = process.env.LAB_TRUST_PROXY === "1";
const ip = (req) =>
  ((TRUST_PROXY && req.headers["x-forwarded-for"]?.split(",").at(-1).trim()) || req.socket.remoteAddress) ?? "?";

// Simple per-IP limit: n requests per minute per bucket.
const hits = new Map();
function limit(req, bucket, n) {
  const k = `${bucket}:${ip(req)}`;
  const t = Date.now();
  const h = hits.get(k);
  if (!h || h.reset < t) hits.set(k, { n: 1, reset: t + 60_000 });
  else if (++h.n > n) throw new HttpError(429, "Too many requests. Wait a minute.");
}
setInterval(() => {
  const t = Date.now();
  for (const [k, h] of hits) if (h.reset < t) hits.delete(k);
  S.sweep();
  orders.sweepOrders().catch((e) => console.error("sweep orders", e));
}, 60_000).unref();

// Requests that change something must come from our own pages (on top of SameSite=Strict).
function sameOrigin(req) {
  const o = req.headers.origin;
  if (o && o !== ORIGIN) throw new HttpError(403, "Wrong origin.");
  if (!o && req.headers["sec-fetch-site"] && req.headers["sec-fetch-site"] !== "same-origin") throw new HttpError(403, "Wrong origin.");
}

function signedIn(req) {
  const address = S.sessionAddress(cookies(req)[COOKIE]);
  if (!address) throw new HttpError(401, "Sign in with your wallet first.");
  return address;
}

// --- texts the wallet signs ----------------------------------------------------------------------

const SCOPES = {
  read_prefs: "read your sizes, budget and favourite stores",
  save_cart: "save carts and prepare orders for you to review (you place and pay yourself)",
};

const signInText = (address, nonce) =>
  [
    `Sign in to AsAsked Lab (${HOST})`,
    "",
    "This is not a transaction and costs nothing. It signs you in to your AsAsked Lab profile.",
    "",
    `Wallet: ${address}`,
    `Time: ${new Date().toISOString()}`,
    `Code: ${nonce}`,
  ].join("\n");

const grantText = (address, name, scopes, expires, nonce) =>
  [
    `Give an agent access to your AsAsked Lab profile (${HOST})`,
    "",
    "This is not a transaction and costs nothing. The agent cannot pay or place orders.",
    "",
    `Agent: ${name}`,
    ...scopes.map((s) => `Allowed: ${SCOPES[s]}`),
    `Until: ${new Date(expires).toISOString().slice(0, 10)}`,
    `Wallet: ${address}`,
    `Code: ${nonce}`,
  ].join("\n");

// --- preferences ---------------------------------------------------------------------------------

// Only what helps an agent pick sizes and products. No addresses, names or contacts.
function cleanPrefs(p) {
  if (!p || typeof p !== "object") throw new HttpError(400, "Preferences must be an object.");
  const out = {};
  if (p.sizes !== undefined) {
    if (typeof p.sizes !== "object" || Array.isArray(p.sizes)) throw new HttpError(400, "sizes must be an object.");
    const entries = Object.entries(p.sizes).slice(0, 8);
    out.sizes = {};
    for (const [k, v] of entries) {
      const key = String(k).trim().toLowerCase().slice(0, 20);
      const val = String(v).trim().slice(0, 12);
      if (!/^[a-z][a-z \-]*$/.test(key) || !/^[\w .\/\-]+$/.test(val)) throw new HttpError(400, `Size "${k}: ${v}" is not valid.`);
      out.sizes[key] = val;
    }
  }
  if (p.budget !== undefined && p.budget !== null) {
    const b = Number(p.budget);
    if (!Number.isFinite(b) || b <= 0 || b > 1e6) throw new HttpError(400, "budget must be a number of US dollars.");
    out.budget = Math.round(b * 100) / 100;
  }
  if (p.stores !== undefined) {
    const known = new Set(stores().map((s) => s.domain));
    if (!Array.isArray(p.stores)) throw new HttpError(400, "stores must be a list.");
    out.stores = [...new Set(p.stores.map(String))].filter((d) => known.has(d)).slice(0, 20);
  }
  if (p.crypto_only !== undefined) out.crypto_only = Boolean(p.crypto_only);
  return out;
}

// --- routes --------------------------------------------------------------------------------------

async function api(req, res, path) {
  const m = req.method;

  if (path === "/api/health" && m === "GET") return send(res, 200, { ok: true, products: catalog().data.products.length });

  if (path === "/api/auth/challenge" && m === "POST") {
    sameOrigin(req);
    limit(req, "auth", 20);
    const { address } = await body(req);
    if (!isAddress(address)) throw new HttpError(400, "That is not a Solana wallet address.");
    const nonce = randomBytes(12).toString("hex");
    const text = signInText(address, nonce);
    S.addChallenge({ nonce, address, purpose: "signin", text, expires: Date.now() + 5 * 60_000 });
    return send(res, 200, { nonce, text });
  }

  if (path === "/api/auth/verify" && m === "POST") {
    sameOrigin(req);
    limit(req, "auth", 20);
    const { nonce, signature } = await body(req);
    const c = S.takeChallenge(String(nonce ?? ""), "signin");
    if (!c) throw new HttpError(400, "The sign-in code expired. Try again.");
    if (!signedBy(c.address, c.text, signature)) throw new HttpError(401, "The signature did not match this wallet.");
    const token = S.addSession(c.address);
    return send(res, 200, { address: c.address }, { "set-cookie": cookie(token, 30 * 86400) });
  }

  if (path === "/api/auth/logout" && m === "POST") {
    sameOrigin(req);
    S.dropSession(cookies(req)[COOKIE]);
    return send(res, 200, { ok: true }, { "set-cookie": cookie("", 0) });
  }

  if (path === "/api/me" && m === "GET") {
    const address = S.sessionAddress(cookies(req)[COOKIE]);
    return send(res, 200, { address });
  }

  if (path === "/api/profile") {
    const address = signedIn(req);
    if (m === "GET") {
      const p = S.getProfile(address);
      return send(res, 200, { ...p, agents: S.listAgents(address), carts: S.listCarts(address), orders: S.listOrders(address) });
    }
    sameOrigin(req);
    if (m === "PUT") {
      const prefs = cleanPrefs((await body(req)).prefs);
      S.setPrefs(address, prefs);
      return send(res, 200, { prefs });
    }
    if (m === "DELETE") {
      for (const t of S.expireOrders(address)) await clearStoreCart(t.token, t.nonce);
      S.deleteAll(address);
      return send(res, 200, { deleted: true }, { "set-cookie": cookie("", 0) });
    }
  }

  if (path === "/api/history" && m === "POST") {
    const address = signedIn(req);
    sameOrigin(req);
    const { q, fits } = await body(req);
    const query = String(q ?? "").trim().slice(0, 200);
    if (!query) throw new HttpError(400, "Empty search.");
    const h = S.getProfile(address).history.filter((x) => x.q !== query);
    h.unshift({ q: query, at: new Date().toISOString(), ...(Number.isInteger(fits) ? { fits } : {}) });
    S.setHistory(address, h.slice(0, 50));
    return send(res, 200, { ok: true });
  }
  if (path === "/api/history" && m === "DELETE") {
    const address = signedIn(req);
    sameOrigin(req);
    S.setHistory(address, []);
    return send(res, 200, { ok: true });
  }

  const tooManyAgents = (address) => {
    if (S.listAgents(address).filter((a) => !a.revoked && a.expires > Date.now()).length >= 10)
      throw new HttpError(400, "You already have 10 agents with access. Take access from one first.");
  };

  // Giving an agent access takes a fresh wallet signature that names the agent and what it may do.
  if (path === "/api/agents/challenge" && m === "POST") {
    const address = signedIn(req);
    sameOrigin(req);
    limit(req, "auth", 20);
    const b = await body(req);
    const name = String(b.name ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
    if (!/^[\p{L}\p{N} ._\-()]{1,40}$/u.test(name)) throw new HttpError(400, "Name the agent, e.g. “Claude on my laptop”.");
    const scopes = [...new Set(Array.isArray(b.scopes) ? b.scopes : [])].filter((s) => s in SCOPES);
    if (!scopes.length) throw new HttpError(400, "Choose at least one thing the agent may do.");
    const days = [7, 30, 90].includes(b.days) ? b.days : 30;
    tooManyAgents(address);
    const nonce = randomBytes(12).toString("hex");
    const expires = Date.now() + days * 864e5;
    const text = grantText(address, name, scopes, expires, nonce);
    S.addChallenge({ nonce, address, purpose: "grant", text, data: { name, scopes, expires }, expires: Date.now() + 5 * 60_000 });
    return send(res, 200, { nonce, text });
  }

  if (path === "/api/agents" && m === "POST") {
    const address = signedIn(req);
    sameOrigin(req);
    const { nonce, signature } = await body(req);
    const c = S.takeChallenge(String(nonce ?? ""), "grant");
    if (!c || c.address !== address) throw new HttpError(400, "The code expired. Try again.");
    if (!signedBy(address, c.text, signature)) throw new HttpError(401, "The signature did not match this wallet.");
    // Checked again here: several codes could be asked for at once.
    tooManyAgents(address);
    // The same end date the person signed, not a new one counted from now.
    const a = S.addAgent(address, c.data.name, c.data.scopes, c.data.expires);
    // The token is shown once and stored only as a hash.
    return send(res, 200, { id: a.id, name: a.name, scopes: a.scopes, expires: a.expires, token: a.token, mcp_url: `${ORIGIN}/mcp` });
  }

  let r = path.match(/^\/api\/agents\/([\w-]{1,20})$/);
  if (r && m === "DELETE") {
    const address = signedIn(req);
    sameOrigin(req);
    return send(res, S.revokeAgent(address, r[1]) ? 200 : 404, { revoked: true });
  }

  r = path.match(/^\/api\/carts\/([\w-]{1,20})$/);
  if (r && m === "DELETE") {
    const address = signedIn(req);
    sameOrigin(req);
    return send(res, S.deleteCart(address, r[1]) ? 200 : 404, { deleted: true });
  }

  // Orders at Bottega Senatore. Prepare: no order yet. Place: only here, from our page, with the
  // unlocked address in this one request (never stored) and the total the person saw.
  // Our own chat: same tools and guard as outside agents; it can prepare, never place or pay.
  if (path === "/api/chat" && m === "POST") {
    sameOrigin(req);
    limit(req, "chat", 30);
    const address = S.sessionAddress(cookies(req)[COOKIE]) ?? null;
    const b = await body(req);
    const out = await chatTurn({ messages: b.messages, state: b.state }, address);
    return send(res, out.error ? 400 : 200, out);
  }
  if (path === "/api/orders") {
    const address = signedIn(req);
    if (m === "GET") return send(res, 200, { orders: S.listOrders(address) });
  }
  if (path === "/api/orders/prepare" && m === "POST") {
    const address = signedIn(req);
    sameOrigin(req);
    limit(req, "prepare", 20);
    const b = await body(req);
    try {
      const o = await orders.prepareOrder(address, { request: b.request, items: b.items, cart_id: typeof b.cart_id === "string" ? b.cart_id : undefined, where: b.where, agent: null });
      return send(res, 200, { order: o });
    } catch (e) {
      if (e instanceof orders.OrderError) return send(res, e.status, { error: e.message, order: e.order });
      throw e;
    }
  }
  r = path.match(/^\/api\/orders\/([\w-]{1,20})\/place$/);
  if (r && m === "POST") {
    const address = signedIn(req);
    sameOrigin(req);
    limit(req, "place", 10);
    const b = await body(req);
    try {
      const o = await orders.placeOrder(address, r[1], b.address, b.total_minor);
      return send(res, 200, { order: o });
    } catch (e) {
      if (e instanceof orders.OrderError) return send(res, e.status, { error: e.message, order: e.order });
      throw e;
    }
  }
  r = path.match(/^\/api\/orders\/([\w-]{1,20})$/);
  if (r && m === "DELETE") {
    const address = signedIn(req);
    sameOrigin(req);
    const done = (await orders.cancelOrder(address, r[1])) || S.deleteOrder(address, r[1]);
    return send(res, done ? 200 : 404, done ? { deleted: true } : { error: "No such order, or it is being placed right now." });
  }

  // The delivery address, locked in the browser. Only a well-formed box is accepted, so nothing readable can be saved here.
  if (path === "/api/address") {
    const address = signedIn(req);
    if (m === "GET") return send(res, 200, S.getBox(address));
    sameOrigin(req);
    if (m === "PUT") {
      limit(req, "address", 30);
      const box = cleanBox((await body(req)).box);
      S.setBox(address, box);
      return send(res, 200, S.getBox(address));
    }
    if (m === "DELETE") {
      S.deleteBox(address);
      return send(res, 200, { deleted: true });
    }
  }

  throw new HttpError(404, "Not found.");
}

// A box is {v: 1, salt, iv, ct}: base64 of 16 random bytes, 12 random bytes and AES-GCM ciphertext.
function cleanBox(b) {
  const bytes = (v, max) => {
    if (typeof v !== "string" || v.length > max * 2 || !/^[A-Za-z0-9+/]+={0,2}$/.test(v)) return null;
    return Buffer.from(v, "base64");
  };
  const keys = b && typeof b === "object" ? Object.keys(b).sort().join() : "";
  const salt = bytes(b?.salt, 16), iv = bytes(b?.iv, 12), ct = bytes(b?.ct, 4096);
  if (keys !== "ct,iv,salt,v" || b.v !== 1 || salt?.length !== 16 || iv?.length !== 12 || !ct || ct.length < 17 || ct.length > 4096)
    throw new HttpError(400, "Only an address locked in your browser can be saved.");
  return { v: 1, salt: b.salt, iv: b.iv, ct: b.ct };
}

// MCP clients run on other machines and in other sites, so /mcp allows any origin but never reads cookies.
const MCP_CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "POST, OPTIONS",
  "access-control-allow-headers": "authorization, content-type, mcp-protocol-version, mcp-session-id",
  "access-control-max-age": "86400",
};

async function mcp(req, res) {
  if (req.method === "OPTIONS") {
    res.writeHead(204, MCP_CORS);
    return res.end();
  }
  if (req.method !== "POST") return send(res, 405, { error: "Use POST." }, { ...MCP_CORS, allow: "POST" });
  limit(req, "mcp", 120);
  let agent = null;
  const auth = req.headers.authorization ?? "";
  if (auth) {
    const t = auth.match(/^Bearer\s+(aslab_[\w-]{20,})$/)?.[1];
    if (!t) return send(res, 401, { error: "Send your access token as: Authorization: Bearer aslab_… Get one at " + `${ORIGIN}/account` }, MCP_CORS);
    agent = S.agentByToken(t);
    if (!agent)
      return send(res, 401, { error: "This access token is not valid any more. Get a new one at " + `${ORIGIN}/account` }, MCP_CORS);
  }
  const msg = await body(req, true);
  if (Array.isArray(msg)) return send(res, 400, { jsonrpc: "2.0", id: null, error: { code: -32600, message: "Batches are not supported." } }, MCP_CORS);
  const out = await handle(msg, agent);
  if (!out) {
    res.writeHead(202, MCP_CORS);
    return res.end();
  }
  return send(res, 200, out, MCP_CORS);
}

// --- local static files (LAB_STATIC only) --------------------------------------------------------

const STATIC = process.env.LAB_STATIC ? resolve(process.env.LAB_STATIC) : null;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain" };
async function staticFile(res, path) {
  const isFile = (p) => stat(p).then((s) => s.isFile(), () => false);
  const tries = path === "/" ? ["/index.html"] : path.endsWith("/") ? [] : [path, `${path}.html`];
  for (const t of tries) {
    const f = join(STATIC, normalize(t));
    if ((f === STATIC || f.startsWith(STATIC + sep)) && (await isFile(f))) {
      res.writeHead(200, { "content-type": TYPES[extname(f)] ?? "application/octet-stream" });
      return res.end(await readFile(f));
    }
  }
  res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
  res.end(await readFile(join(STATIC, "404.html")).catch(() => "Not found"));
}

createServer(async (req, res) => {
  const path = new URL(req.url ?? "/", "http://x").pathname;
  try {
    if (path === "/mcp") return await mcp(req, res);
    if (path.startsWith("/api/")) return await api(req, res, path);
    if (STATIC) {
      let file;
      try {
        file = decodeURIComponent(path);
      } catch {
        throw new HttpError(400, "Bad address.");
      }
      return await staticFile(res, file);
    }
    throw new HttpError(404, "Not found.");
  } catch (e) {
    if (e instanceof HttpError) return send(res, e.status, { error: e.message }, path === "/mcp" ? MCP_CORS : {});
    console.error(req.method, path, e);
    return send(res, 500, { error: "Something went wrong on our side." });
  }
}).listen(PORT, "127.0.0.1", () => console.log(`lab server on http://127.0.0.1:${PORT} (origin ${ORIGIN})`));
