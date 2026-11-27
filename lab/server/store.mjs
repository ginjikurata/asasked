// Server data: wallet sign-in codes, sessions, profiles, agent access, saved carts and orders.
// SQLite file in LAB_DATA (default server/data). A delivery address is kept only as a box the
// person's browser locked with a key from their wallet signature (table boxes): we cannot read it.
// No readable addresses, emails or phones are stored here.
import { DatabaseSync } from "node:sqlite";
import { createHash, randomBytes } from "node:crypto";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const dir = process.env.LAB_DATA ?? join(import.meta.dirname, "data");
mkdirSync(dir, { recursive: true, mode: 0o700 });
export const db = new DatabaseSync(join(dir, "lab.db"));

db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;
  CREATE TABLE IF NOT EXISTS challenges (nonce TEXT PRIMARY KEY, address TEXT NOT NULL, purpose TEXT NOT NULL, text TEXT NOT NULL, data TEXT, expires INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, address TEXT NOT NULL, expires INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS profiles (address TEXT PRIMARY KEY, prefs TEXT NOT NULL DEFAULT '{}', history TEXT NOT NULL DEFAULT '[]', created INTEGER NOT NULL, updated INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, address TEXT NOT NULL, name TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, scopes TEXT NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL, last_used INTEGER, revoked INTEGER);
  CREATE TABLE IF NOT EXISTS carts (id TEXT PRIMARY KEY, address TEXT NOT NULL, agent_id TEXT, agent_name TEXT, request TEXT NOT NULL, items TEXT NOT NULL, created INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS boxes (address TEXT PRIMARY KEY, box TEXT NOT NULL, updated INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, address TEXT NOT NULL, agent_name TEXT, request TEXT NOT NULL, items TEXT NOT NULL, fit TEXT NOT NULL, country TEXT, token TEXT, nonce TEXT, snap TEXT NOT NULL, status TEXT NOT NULL, order_id TEXT, invoice_url TEXT, invoice TEXT, note TEXT, created INTEGER NOT NULL, expires INTEGER NOT NULL);
  CREATE INDEX IF NOT EXISTS orders_by_address ON orders(address, created);
  CREATE INDEX IF NOT EXISTS agents_by_address ON agents(address);
  CREATE INDEX IF NOT EXISTS carts_by_address ON carts(address, created);
`);

export const now = () => Date.now();
export const id = (n = 9) => randomBytes(n).toString("base64url");
export const sha = (s) => createHash("sha256").update(s).digest("hex");
const json = (s, fallback) => {
  try {
    return JSON.parse(s);
  } catch {
    return fallback;
  }
};

// Old codes and sessions go away on their own.
export function sweep() {
  db.prepare("DELETE FROM challenges WHERE expires < ?").run(now());
  db.prepare("DELETE FROM sessions WHERE expires < ?").run(now());
}

export function addChallenge(c) {
  db.prepare("INSERT INTO challenges (nonce, address, purpose, text, data, expires) VALUES (?, ?, ?, ?, ?, ?)").run(
    c.nonce, c.address, c.purpose, c.text, c.data ? JSON.stringify(c.data) : null, c.expires,
  );
}

// A code works once: it is deleted whether the signature turns out good or not.
export function takeChallenge(nonce, purpose) {
  const row = db.prepare("SELECT * FROM challenges WHERE nonce = ? AND purpose = ?").get(nonce, purpose);
  if (!row) return null;
  db.prepare("DELETE FROM challenges WHERE nonce = ?").run(nonce);
  if (row.expires < now()) return null;
  return { ...row, data: row.data ? json(row.data, null) : null };
}

export function addSession(address, days = 30) {
  const token = id(32);
  db.prepare("INSERT INTO sessions (hash, address, expires) VALUES (?, ?, ?)").run(sha(token), address, now() + days * 864e5);
  return token;
}
export const sessionAddress = (token) =>
  token ? db.prepare("SELECT address FROM sessions WHERE hash = ? AND expires > ?").get(sha(token), now())?.address ?? null : null;
export const dropSession = (token) => token && db.prepare("DELETE FROM sessions WHERE hash = ?").run(sha(token));

export function getProfile(address) {
  const row = db.prepare("SELECT * FROM profiles WHERE address = ?").get(address);
  if (!row) return { address, prefs: {}, history: [], created: null, updated: null };
  return { address, prefs: json(row.prefs, {}), history: json(row.history, []), created: row.created, updated: row.updated };
}
function upsert(address, field, value) {
  db.prepare(
    `INSERT INTO profiles (address, ${field}, created, updated) VALUES (?, ?, ?, ?)
     ON CONFLICT(address) DO UPDATE SET ${field} = excluded.${field}, updated = excluded.updated`,
  ).run(address, JSON.stringify(value), now(), now());
}
export const setPrefs = (address, prefs) => upsert(address, "prefs", prefs);
export const setHistory = (address, history) => upsert(address, "history", history);

// "Delete everything": profile, agent access, carts, orders, the locked address and every session of this wallet.
export function deleteAll(address) {
  for (const t of ["profiles", "agents", "carts", "boxes", "orders", "sessions", "challenges"]) db.prepare(`DELETE FROM ${t} WHERE address = ?`).run(address);
}

// The locked delivery address: ciphertext only, opened in the browser with a wallet signature.
export function getBox(address) {
  const row = db.prepare("SELECT box, updated FROM boxes WHERE address = ?").get(address);
  return row ? { box: json(row.box, null), updated: row.updated } : { box: null, updated: null };
}
export function setBox(address, box) {
  db.prepare("INSERT INTO boxes (address, box, updated) VALUES (?, ?, ?) ON CONFLICT(address) DO UPDATE SET box = excluded.box, updated = excluded.updated").run(
    address, JSON.stringify(box), now(),
  );
}
export const deleteBox = (address) => db.prepare("DELETE FROM boxes WHERE address = ?").run(address).changes > 0;

// expires is the end date the person signed for.
export function addAgent(address, name, scopes, expires) {
  const token = `aslab_${id(32)}`;
  const a = { id: id(6), address, name, scopes, created: now(), expires };
  db.prepare("INSERT INTO agents (id, address, name, hash, scopes, created, expires) VALUES (?, ?, ?, ?, ?, ?, ?)").run(
    a.id, address, name, sha(token), JSON.stringify(scopes), a.created, a.expires,
  );
  return { ...a, token };
}
const agentRow = (r) => ({ id: r.id, name: r.name, scopes: json(r.scopes, []), created: r.created, expires: r.expires, last_used: r.last_used, revoked: r.revoked });
export const listAgents = (address) =>
  db.prepare("SELECT * FROM agents WHERE address = ? ORDER BY created DESC").all(address).map(agentRow);
export const revokeAgent = (address, agentId) =>
  db.prepare("UPDATE agents SET revoked = ? WHERE address = ? AND id = ? AND revoked IS NULL").run(now(), address, agentId).changes > 0;
export function agentByToken(token) {
  const r = db.prepare("SELECT * FROM agents WHERE hash = ?").get(sha(token));
  if (!r || r.revoked || r.expires < now()) return null;
  db.prepare("UPDATE agents SET last_used = ? WHERE id = ?").run(now(), r.id);
  return { ...agentRow(r), address: r.address };
}

const MAX_CARTS = 20;
export function addCart(address, agent, request, items) {
  const c = { id: id(6), created: now() };
  db.prepare("INSERT INTO carts (id, address, agent_id, agent_name, request, items, created) VALUES (?, ?, ?, ?, ?, ?, ?)").run(
    c.id, address, agent?.id ?? null, agent?.name ?? null, request, JSON.stringify(items), c.created,
  );
  // Keep only the newest carts.
  db.prepare("DELETE FROM carts WHERE address = ? AND id NOT IN (SELECT id FROM carts WHERE address = ? ORDER BY created DESC LIMIT ?)").run(address, address, MAX_CARTS);
  return c;
}
export const listCarts = (address) =>
  db.prepare("SELECT * FROM carts WHERE address = ? ORDER BY created DESC").all(address).map((r) => ({
    id: r.id, agent: r.agent_name, request: r.request, items: json(r.items, []), created: r.created,
  }));
export const deleteCart = (address, cartId) => db.prepare("DELETE FROM carts WHERE address = ? AND id = ?").run(address, cartId).changes > 0;

// Orders at a store. Kept: what was asked, the store's cart totals, the guard results, the store's
// order number and the invoice link. Never kept: the delivery address, email, phone, postcode or the
// store's order key. The store cart token is kept only while the order is "prepared" (30 minutes):
// after the person adds their address the store cart holds it, so the token is dropped then.
const MAX_ORDERS = 20;
export const ORDER_MINUTES = 30;
const orderRow = (r) => ({
  id: r.id, agent: r.agent_name, request: r.request, items: json(r.items, []), fit: json(r.fit, null), snap: json(r.snap, null),
  status: r.status, order_id: r.order_id, invoice_url: r.invoice_url, invoice: r.invoice ? json(r.invoice, null) : null, note: r.note,
  created: r.created, expires: r.expires,
});
export function addOrder(address, o) {
  const row = { id: id(6), created: now(), expires: now() + ORDER_MINUTES * 60_000 };
  db.prepare(
    "INSERT INTO orders (id, address, agent_name, request, items, fit, country, token, nonce, snap, status, created, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?)",
  ).run(row.id, address, o.agent ?? null, o.request, JSON.stringify(o.items), JSON.stringify(o.fit), o.country ?? null, o.token, o.nonce, JSON.stringify(o.snap), row.created, row.expires);
  return getOrder(address, row.id);
}
// Keep the newest MAX_ORDERS per person. A row in the middle of placing stays. Returns the store
// carts of dropped rows that still hold items, so the caller can empty them at the store.
export function pruneOrders(address) {
  const old = "address = ? AND status != 'placing' AND id NOT IN (SELECT id FROM orders WHERE address = ? ORDER BY created DESC LIMIT ?)";
  const carts = db.prepare(`SELECT token, nonce FROM orders WHERE ${old} AND token IS NOT NULL`).all(address, address, MAX_ORDERS);
  db.prepare(`DELETE FROM orders WHERE ${old}`).run(address, address, MAX_ORDERS);
  return carts;
}
export function getOrder(address, orderId) {
  const r = db.prepare("SELECT * FROM orders WHERE address = ? AND id = ?").get(address, orderId);
  return r ? orderRow(r) : null;
}
export const listOrders = (address) => db.prepare("SELECT * FROM orders WHERE address = ? ORDER BY created DESC").all(address).map(orderRow);

// Only one request can place an order: the row moves from prepared to placing in one step.
export function takeForPlacing(address, orderId) {
  const r = db.prepare("UPDATE orders SET status = 'placing' WHERE address = ? AND id = ? AND status = 'prepared' AND expires > ? AND token IS NOT NULL RETURNING *").get(address, orderId, now());
  return r ? { ...orderRow(r), token: r.token, nonce: r.nonce, country: r.country } : null;
}
// The store's total changed when the address went in: show the new total and let the person decide.
export function backToPrepared(orderId, token, nonce, snap, fit) {
  db.prepare("UPDATE orders SET status = 'prepared', token = ?, nonce = ?, snap = ?, fit = COALESCE(?, fit) WHERE id = ? AND status = 'placing'").run(
    token, nonce, JSON.stringify(snap), fit ? JSON.stringify(fit) : null, orderId,
  );
}
// The person drops a prepared order. Returns the cart token so the caller can empty the store cart.
// RETURNING would give the values after the update (token already NULL), so read first.
// One process, synchronous SQLite: nothing runs between the read and the update.
export function cancelOrder(address, orderId) {
  const r = db.prepare("SELECT token, nonce FROM orders WHERE address = ? AND id = ? AND status = 'prepared'").get(address, orderId);
  if (!r) return null;
  db.prepare("UPDATE orders SET status = 'canceled', token = NULL, nonce = NULL WHERE address = ? AND id = ? AND status = 'prepared'").run(address, orderId);
  return { token: r.token, nonce: r.nonce };
}
export function finishOrder(orderId, f) {
  db.prepare("UPDATE orders SET status = ?, token = NULL, nonce = NULL, order_id = ?, invoice_url = ?, invoice = ?, note = ?, snap = COALESCE(?, snap) WHERE id = ?").run(
    f.status, f.order_id ?? null, f.invoice_url ?? null, f.invoice ? JSON.stringify(f.invoice) : null, f.note ?? null, f.snap ? JSON.stringify(f.snap) : null, orderId,
  );
}
// Prepared orders that ran out of time, or (with address) all this wallet's prepared ones.
// They become "expired" and lose the token; the caller empties those store carts.
export function expireOrders(address) {
  const where = address ? "address = ? AND status = 'prepared'" : "status = 'prepared' AND expires < ?";
  const arg = address ?? now();
  const rows = db.prepare(`SELECT token, nonce FROM orders WHERE ${where}`).all(arg);
  db.prepare(`UPDATE orders SET status = 'expired', token = NULL, nonce = NULL WHERE ${where}`).run(arg);
  // A crash in the middle of placing leaves "placing": after an hour it is marked failed.
  if (!address) db.prepare("UPDATE orders SET status = 'failed', token = NULL, nonce = NULL, note = 'Stopped in the middle. Check your email from the store.' WHERE status = 'placing' AND expires < ?").run(now() - 30 * 60_000);
  return rows.filter((r) => r.token);
}
export const deleteOrder = (address, orderId) =>
  db.prepare("DELETE FROM orders WHERE address = ? AND id = ? AND status NOT IN ('prepared', 'placing')").run(address, orderId).changes > 0;
