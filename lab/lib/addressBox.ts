// The delivery address is locked in the browser. A wallet signature of a fixed text makes the key
// (HKDF-SHA256, then AES-GCM-256); the server only ever gets the locked box. Without that wallet
// signature nobody, us included, can read it.

export type Address = {
  name: string;
  line1: string;
  line2: string;
  city: string;
  region: string;
  postal: string;
  country: string;
  phone: string;
  email: string;
};
export type Box = { v: 1; salt: string; iv: string; ct: string };
export type Sign = (message: Uint8Array) => Promise<Uint8Array>;

export const EMPTY: Address = { name: "", line1: "", line2: "", city: "", region: "", postal: "", country: "", phone: "", email: "" };

// The same text every time, so the same wallet makes the same key. It has no code in it on purpose.
export const lockText = (wallet: string) =>
  [
    "Unlock your delivery address on AsAsked Lab (lab.asasked.dev).",
    "",
    "This is not a transaction and costs nothing.",
    "The signature makes the key that locks your address in this browser. AsAsked never sees it.",
    "Sign this only on lab.asasked.dev.",
    "",
    `Wallet: ${wallet}`,
  ].join("\n");

const MAX_CT = 4096;
const INFO = new TextEncoder().encode("asasked-lab address v1");
const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u));
const unb64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const same = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((x, i) => x === b[i]);

export class LockError extends Error {}

async function key(signature: Uint8Array, salt: Uint8Array) {
  const base = await crypto.subtle.importKey("raw", signature as BufferSource, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: salt as BufferSource, info: INFO },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

// First lock: sign twice and compare. A wallet that signs differently each time could never open the box again.
export async function signForLock(wallet: string, sign: Sign, check: boolean) {
  const text = new TextEncoder().encode(lockText(wallet));
  const signature = await sign(text);
  if (check && !same(signature, await sign(text)))
    throw new LockError("This wallet signs the same text differently each time, so it cannot lock an address. Try another wallet.");
  return signature;
}

export async function seal(fields: Address, wallet: string, signature: Uint8Array): Promise<Box> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const clean = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, String(fields[k as keyof Address] ?? "").trim().slice(0, 200)]));
  const plain = new TextEncoder().encode(JSON.stringify(clean));
  // The server takes at most 4096 bytes of locked data (the text plus a 16-byte check).
  if (plain.length + 16 > MAX_CT) throw new LockError("The address is too long to save. Shorten some of the fields.");
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: new TextEncoder().encode(wallet) },
    await key(signature, salt),
    plain,
  );
  return { v: 1, salt: b64(salt), iv: b64(iv), ct: b64(new Uint8Array(ct)) };
}

export async function open(box: Box, wallet: string, signature: Uint8Array): Promise<Address> {
  try {
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: unb64(box.iv) as BufferSource, additionalData: new TextEncoder().encode(wallet) },
      await key(signature, unb64(box.salt)),
      unb64(box.ct) as BufferSource,
    );
    return { ...EMPTY, ...JSON.parse(new TextDecoder().decode(plain)) };
  } catch {
    throw new LockError("This signature does not open the saved address. If you changed wallets, delete the address and add it again.");
  }
}
