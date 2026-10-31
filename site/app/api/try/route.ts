import { createHash } from "node:crypto";

// The live window: forwards a visitor's request (or their answer to the agent's question) to the Python service (src/asasked/live.py)
// on the same machine. Limits and money are counted there; here only the visitor's id is
// derived, so the service never sees an IP address.
const LIVE_URL = process.env.ASASKED_LIVE_URL ?? "http://127.0.0.1:3005";
const MAX_CHARS = 300;

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Body must be JSON." }, { status: 400 });
  }
  // Either a new request, or the visitor's answer to the question that paused a run.
  const b = (body ?? {}) as { request?: unknown; conversation?: unknown; answer?: unknown };
  const text = (v: unknown) => (typeof v === "string" ? v.trim() : "");
  const conversation = text(b.conversation).slice(0, 64);
  const words = conversation ? text(b.answer) : text(b.request);
  if (!words)
    return Response.json(
      { error: conversation ? "Write your answer." : "Write what you'd like to buy." },
      { status: 400 },
    );
  if (words.length > MAX_CHARS)
    return Response.json({ error: `Keep it under ${MAX_CHARS} characters.` }, { status: 400 });

  // Caddy sets X-Forwarded-For to the client's address (an incoming one is not trusted).
  // Take the last hop anyway: it is the one our own proxy wrote, so a visitor who sends
  // a made-up header cannot pick their own id even if the proxy config changes.
  const ip = req.headers.get("x-forwarded-for")?.split(",").pop()?.trim() || "local";
  const visitor = createHash("sha256")
    .update(`${process.env.ASASKED_LIVE_SALT ?? "asasked"}:${ip}`)
    .digest("hex")
    .slice(0, 32);

  try {
    const r = await fetch(`${LIVE_URL}/try`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(conversation ? { conversation, answer: words, visitor } : { request: words, visitor }),
      signal: AbortSignal.timeout(300_000),
    });
    return new Response(await r.text(), {
      status: r.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return Response.json({ error: "The live demo is offline right now." }, { status: 503 });
  }
}
