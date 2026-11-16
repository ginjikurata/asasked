// Paths the recorded vectors don't cover: calling a model over HTTP (with a
// stubbed fetch) and the guard's question-answer loop.
import { test } from "node:test";
import assert from "node:assert/strict";
import { ExtractionError, Guard, extractIntent, intentFacts, parseJson } from "../dist/index.js";

const ENV = ["LLM_PROVIDER", "CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_BASE_URL",
  "OPENAI_COMPAT_BASE_URL", "OPENAI_COMPAT_API_KEY", "OPENAI_COMPAT_MODEL", "LLM_API_KEY"];

async function withFetch(env, answers, fn) {
  const saved = { fetch: globalThis.fetch, env: Object.fromEntries(ENV.map((k) => [k, process.env[k]])) };
  for (const k of ENV) delete process.env[k];
  Object.assign(process.env, env);
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    const [status, body] = answers.shift();
    return new Response(typeof body === "string" ? body : JSON.stringify(body), { status });
  };
  try {
    return await fn(calls);
  } finally {
    globalThis.fetch = saved.fetch;
    for (const k of ENV) {
      if (saved.env[k] === undefined) delete process.env[k];
      else process.env[k] = saved.env[k];
    }
  }
}

test("parseJson takes the first object, past fences and trailing reasoning", () => {
  assert.deepEqual(parseJson('```json\n{"brand": "ASICS"}\n```\nalso {"x": 1}'), { brand: "ASICS" });
  assert.throws(() => parseJson("no json here"), ExtractionError);
});

test("anthropic: drops structured output on a 400 and reads the answer", async () => {
  const answer = { stop_reason: "end_turn", content: [{ type: "text",
    text: '{"brand": "ASICS", "color": "black", "soft_fields": ["color"]}' }] };
  await withFetch({ LLM_PROVIDER: "anthropic", CLAUDE_API_KEY: "test", CLAUDE_BASE_URL: "https://proxy.test/" },
    [[400, "no output_config"], [200, answer]], async (calls) => {
      const facts = await extractIntent("black ASICS, white is fine too");
      assert.equal(facts.brand, "ASICS");
      assert.deepEqual([...facts.soft], ["color"]);
      assert.equal(calls[0].url, "https://proxy.test/v1/messages");
      assert.ok("output_config" in calls[0].body);
      assert.ok(!("output_config" in calls[1].body));
      assert.equal(calls[1].init.headers["x-api-key"], "test");
    });
});

test("openai_compat: falls back to json_object, names itself", async () => {
  const answer = { choices: [{ message: { content: '{"quantity": 2}' } }] };
  await withFetch({ LLM_PROVIDER: "openai_compat", OPENAI_COMPAT_BASE_URL: "https://compat.test/v1",
    OPENAI_COMPAT_API_KEY: "test", OPENAI_COMPAT_MODEL: "m" },
  [[400, "bad format"], [200, answer]], async (calls) => {
    const facts = await extractIntent("two of them");
    assert.equal(facts.quantity, 2);
    assert.equal(calls[1].body.response_format.type, "json_object");
    assert.equal(calls[1].init.headers["User-Agent"], "asasked/0.1");
  });
});

test("a missing key is an ExtractionError, not a crash", async () => {
  await withFetch({ LLM_PROVIDER: "anthropic" }, [], async () => {
    await assert.rejects(extractIntent("anything"), ExtractionError);
  });
});

const shoe = { name: "ASICS Gel-Nimbus 26", price: 159, brand: "ASICS", color: "White", size: "42" };

test("guard: asks, the person agrees, the same cart goes through", async () => {
  const guard = new Guard("black ASICS size 42", {
    extract: (request) => intentFacts({ brand: "ASICS", color: "black", size_label: "42", raw: request }),
  });
  let paid = 0;
  const pay = guard.protect((item) => { paid++; return "paid"; }, (item) => [item]);
  const first = await pay(shoe);
  assert.equal(paid, 0);
  assert.match(first, /^NOT PAID/);
  assert.match(first, /black/i);
  guard.answer("yes, white is fine");
  // The answer joins the request: the facts are extracted again from it.
  guard.extract = (request) => {
    assert.match(request, /The person answered: yes, white is fine/);
    return intentFacts({ brand: "ASICS", color: "white", size_label: "42", raw: request });
  };
  assert.equal(await pay(shoe), "paid");
  assert.equal(paid, 1);
});

test("guard: when extraction fails, a bare yes approves the unchecked order", async () => {
  const guard = new Guard("black ASICS size 42", {
    extract: () => { throw new ExtractionError("model down"); },
  });
  const blocked = await guard.gate([shoe]);
  assert.match(blocked, /couldn't automatically check/);
  guard.answer("yes");
  assert.equal(await guard.gate([shoe]), null);
});
