// Calling a language model to turn a person's words into facts. A port of
// src/asasked/llm_extract.py: the only place in the package that calls a model.
//
// Three interchangeable providers, same prompt and response schema:
//   gemini         Google's API (LLM_API_KEY, LLM_MODEL);
//   anthropic      Claude, directly or through a compatible proxy
//                  (CLAUDE_API_KEY or ANTHROPIC_API_KEY, CLAUDE_BASE_URL, CLAUDE_MODEL);
//   openai_compat  any OpenAI-compatible /chat/completions
//                  (OPENAI_COMPAT_BASE_URL, OPENAI_COMPAT_API_KEY, OPENAI_COMPAT_MODEL).
//
// Settings are read from the environment at call time. Unlike the Python
// package, no .env file is loaded: load it yourself (node --env-file=.env).
//
// If the model cannot return a valid answer, ExtractionError is thrown with
// the raw response text, so it shows up instead of hiding behind null fields.

import { RESPONSE_SCHEMA, SYSTEM_PROMPT } from "./prompt.js";
import { repr } from "./py.js";

export const PROVIDERS = ["gemini", "anthropic", "openai_compat"] as const;

/** The model did not return a valid answer in the IntentFacts schema. */
export class ExtractionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExtractionError";
  }
}

class BadRequest extends ExtractionError {}

function env(name: string): string | undefined {
  const value = (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process?.env?.[name];
  return value || undefined;
}

const sleep = (seconds: number) => new Promise((r) => setTimeout(r, seconds * 1000));


/** Providers that have a key set: a developer may have just one. */
export function configuredProviders(): string[] {
  const keys: Record<string, string> = { gemini: "LLM_API_KEY", anthropic: "CLAUDE_API_KEY",
    openai_compat: "OPENAI_COMPAT_API_KEY" };
  const found = Object.entries(keys).filter(([, k]) => env(k)).map(([p]) => p);
  if (!found.length && env("ANTHROPIC_API_KEY")) return ["anthropic"];
  return found;
}

/** Which providers extractIntentAgreed compares: LLM_AGREE_PROVIDERS, or every one with a key. */
export function agreeProviders(): string[] {
  const set = (env("LLM_AGREE_PROVIDERS") ?? "").split(",").map((p) => p.trim()).filter(Boolean);
  return set.length ? set : configuredProviders();
}

/** The first JSON object in the answer. Models sometimes wrap it in ```json
 * or append reasoning after it, with another JSON object inside. */
export function parseJson(text: string): Record<string, unknown> {
  if (!/\{[\s\S]*\}/.test(text)) throw new ExtractionError(`No JSON in the model's answer: ${repr(text)}`);
  for (let start = text.indexOf("{"); start !== -1; start = text.indexOf("{", start + 1)) {
    // The shortest prefix from here that parses: what raw_decode would return.
    for (let end = text.indexOf("}", start); end !== -1; end = text.indexOf("}", end + 1)) {
      let value: unknown;
      try {
        value = JSON.parse(text.slice(start, end + 1));
      } catch {
        continue;
      }
      if (value && typeof value === "object" && !Array.isArray(value)) {
        return value as Record<string, unknown>;
      }
      break;
    }
  }
  throw new ExtractionError(`The model returned invalid JSON: ${repr(text)}`);
}

export function systemPrompt(today?: string | null): string {
  if (!today) return SYSTEM_PROMPT;
  return `${SYSTEM_PROMPT}\n\nToday is ${today}. Use it to turn deadlines such as `
    + "'by Saturday' into a number of days.";
}

/** The model's raw answer with the schema's fields. Throws ExtractionError on failure. */
export async function callModel(request: string, provider?: string | null,
  today?: string | null): Promise<Record<string, unknown>> {
  provider = provider || env("LLM_PROVIDER") || "gemini";
  const system = systemPrompt(today);
  if (provider === "gemini") return callGemini(request, system);
  if (provider === "anthropic") return callAnthropic(request, system);
  if (provider === "openai_compat") return callOpenaiCompat(request, system);
  throw new ExtractionError(`Unknown provider ${repr(provider)}, available: ${PROVIDERS.join(", ")}`);
}

interface Posted { status: number; body: string }

async function post(url: string, body: unknown, headers: Record<string, string>,
  timeoutSeconds: number): Promise<Posted> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutSeconds * 1000),
    });
  } catch (e) {
    throw new ExtractionError(`Network unavailable: ${(e as Error).message}`);
  }
  return { status: response.status, body: await response.text() };
}

function decode(posted: Posted): unknown {
  try {
    return JSON.parse(posted.body);
  } catch {
    throw new ExtractionError(`Unexpected response format: ${posted.body}`);
  }
}

async function callGemini(request: string, system: string): Promise<Record<string, unknown>> {
  const key = env("LLM_API_KEY");
  if (!key) throw new ExtractionError("LLM_API_KEY is not set");
  const model = env("LLM_MODEL") ?? "gemini-flash-lite-latest";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  const body = {
    contents: [{ role: "user", parts: [{ text: request }] }],
    systemInstruction: { parts: [{ text: system }] },
    generationConfig: { temperature: 0, responseMimeType: "application/json" },
  };
  let lastError = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    const posted = await post(url, body, { "x-goog-api-key": key }, 30);
    if (posted.status >= 400) {
      lastError = `HTTP ${posted.status} from the model: ${posted.body}`;
      if ((posted.status === 429 || posted.status === 503) && attempt < 3) {
        const m = /"retryDelay":\s*"(\d+(?:\.\d+)?)s"/.exec(posted.body);
        await sleep(m ? Number(m[1]) + 0.5 : 2 ** attempt);
        continue;
      }
      throw new ExtractionError(lastError);
    }
    const payload = decode(posted) as { candidates?: { content?: { parts?: { text?: unknown }[] } }[] };
    const text = payload?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (typeof text !== "string") {
      throw new ExtractionError(`Unexpected response format: ${posted.body}`);
    }
    return parseJson(text);
  }
  throw new ExtractionError(lastError || "Could not get an answer from the model");
}

async function callAnthropic(request: string, system: string): Promise<Record<string, unknown>> {
  const key = env("CLAUDE_API_KEY") ?? env("ANTHROPIC_API_KEY");
  if (!key) throw new ExtractionError("Claude: the key is missing (CLAUDE_API_KEY)");
  // Like the Anthropic SDK: the base URL without /v1/messages.
  const base = (env("CLAUDE_BASE_URL") ?? "https://api.anthropic.com").replace(/\/+$/, "");
  const body: Record<string, unknown> = {
    model: env("CLAUDE_MODEL") ?? "claude-haiku-5-5",
    max_tokens: 1024,
    system,
    messages: [{ role: "user", content: request }],
    output_config: { format: { type: "json_schema", schema: RESPONSE_SCHEMA } },
  };
  const headers = { "x-api-key": key, "anthropic-version": "2023-06-01" };
  let posted: Posted | null = null;
  for (let attempt = 0; attempt < 5; attempt++) {
    posted = await post(`${base}/v1/messages`, body, headers, 60);
    if (posted.status === 400 && "output_config" in body) {
      // A proxy may not support structured output. The schema is in the
      // prompt anyway, and extractIntent checks the answer's shape.
      delete body.output_config;
      attempt--;
      continue;
    }
    if ((posted.status === 429 || posted.status >= 500) && attempt < 4) {
      await sleep(Math.min(8, 0.5 * 2 ** attempt));
      continue;
    }
    break;
  }
  if (posted!.status === 401 || posted!.status === 403) {
    throw new ExtractionError("Claude: the key is missing or wrong (CLAUDE_API_KEY and CLAUDE_BASE_URL)");
  }
  if (posted!.status >= 400) throw new ExtractionError(`HTTP ${posted!.status} from Claude: ${posted!.body}`);
  const response = decode(posted!) as { stop_reason?: unknown; content?: { type?: string; text?: string }[] };
  if (response?.stop_reason !== "end_turn") {
    throw new ExtractionError(`Claude did not finish its answer: stop_reason=${repr(String(response?.stop_reason))}`);
  }
  const text = (response.content ?? []).find((b) => b.type === "text")?.text;
  if (typeof text !== "string") {
    throw new ExtractionError(`No text in Claude's answer: ${JSON.stringify(response.content)}`);
  }
  return parseJson(text);
}

async function callOpenaiCompat(request: string, system: string): Promise<Record<string, unknown>> {
  const base = (env("OPENAI_COMPAT_BASE_URL") ?? "").replace(/\/+$/, "");
  const key = env("OPENAI_COMPAT_API_KEY");
  const model = env("OPENAI_COMPAT_MODEL");
  if (!(base && key && model)) {
    throw new ExtractionError("openai_compat needs OPENAI_COMPAT_BASE_URL, "
      + "OPENAI_COMPAT_API_KEY and OPENAI_COMPAT_MODEL");
  }
  // Not every compatible server understands json_schema: on a refusal (400)
  // ask for plain JSON, then for no format at all; the schema is in the prompt.
  const formats = [
    { type: "json_schema", json_schema: { name: "intent_facts", strict: true, schema: RESPONSE_SCHEMA } },
    { type: "json_object" },
    null,
  ];
  let lastError = "";
  for (const format of formats) {
    const body: Record<string, unknown> = {
      model,
      messages: [{ role: "system", content: system }, { role: "user", content: request }],
      temperature: 0,
    };
    if (format) body.response_format = format;
    let payload: { choices?: { message?: { content?: unknown } }[] };
    try {
      payload = await postWithRetries(`${base}/chat/completions`, body, key) as typeof payload;
    } catch (e) {
      if (e instanceof BadRequest) {
        lastError = e.message;
        continue;
      }
      throw e;
    }
    const message = payload?.choices?.[0]?.message;
    if (!message) throw new ExtractionError(`Unexpected response format: ${JSON.stringify(payload)}`);
    if (typeof message.content !== "string") {
      throw new ExtractionError(`No text in the answer: ${JSON.stringify(payload)}`);
    }
    return parseJson(message.content);
  }
  throw new ExtractionError(lastError || "The server rejected every request format");
}

async function postWithRetries(url: string, body: unknown, key: string): Promise<unknown> {
  let lastError = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    // Cloudflare in front of some proxies blocks unnamed clients, so we
    // introduce ourselves by name.
    const posted = await post(url, body, { Authorization: `Bearer ${key}`, "User-Agent": "asasked/0.1" }, 60);
    if (posted.status >= 400) {
      lastError = `HTTP ${posted.status} from the model: ${posted.body}`;
      if (posted.status === 400) throw new BadRequest(lastError);
      // Proxies like AnyModel briefly answer 503 and suggest a pause.
      if ([429, 500, 502, 503].includes(posted.status) && attempt < 3) {
        const m = /"retry_after_seconds":\s*(\d+(?:\.\d+)?)/.exec(posted.body);
        await sleep(m ? Number(m[1]) + 0.5 : 2 ** (attempt + 1));
        continue;
      }
      throw new ExtractionError(lastError);
    }
    try {
      return JSON.parse(posted.body);
    } catch {
      // A proxy sometimes cuts the answer off midway: a reason to retry.
      lastError = "Answer cut off";
      if (attempt < 3) {
        await sleep(2 ** (attempt + 1));
        continue;
      }
      throw new ExtractionError(lastError);
    }
  }
  throw new ExtractionError(lastError || "Could not get an answer from the model");
}
