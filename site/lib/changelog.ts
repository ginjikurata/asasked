// What changed in the guard, the dataset, the store and the benchmark, newest first.
// Each entry names the commit it came from; facts only.

export type Change = { area: "guard" | "dataset" | "benchmark" | "store" | "spec" | "extraction" | "VI"; text: string; commit?: string };
export type Day = { date: string; changes: Change[] };

export const CHANGELOG: Day[] = [
  {
    date: "2026-11-11",
    changes: [
      {
        area: "guard",
        text:
          "Version 0.1.10: hidden subscriptions. A cart item can now say that it renews and charges again: \"recurring\": {\"every\": \"month\", \"price\": 12.99}. Such an item is asked about unless the person asked for a subscription or agreed to one; this check is never softened, and both models must agree that a subscription is wanted. An amount limit counts the item at the higher of today's and the renewal price, so a $0 free trial that turns into $10.99 a month is over a $10 limit. The \"Subscribe & Save\" listing of the very item the person asked for passed every check before: same brand, same model, a lower price. An item without \"recurring\" counts as a one-time purchase; the guard cannot see a subscription the cart does not mark. In the 16 cases all went as expected.",
        commit: "67fc9ef",
      },
      {
        area: "extraction",
        text:
          "Version 0.1.10: the fact extraction has a new fact, wants_recurring: the person asks for a subscription or a repeat order (\"every month\", \"подписка\", \"cada mes\") or agrees to one. Buying something that gets used up is not a wish for a subscription. A separate set of 16 cases in three languages (stress_subscription.py) checks the whole chain, with expected decisions written before any run; it is not part of the v3 tasks, so the published tasks stay as they are. In the 16 cases all went as expected.",
        commit: "67fc9ef",
      },
      {
        area: "guard",
        text:
          "Version 0.1.10: after the person answers the guard's question, a disagreement between the two models no longer softens anything: in a run, three refusals (\"without returns, no\", \"ok, but only if the bag is black\" on a yellow bag) got through because the models read them differently. A requirement is waived only if both models heard it waived. The extraction also refuses impossible numbers (a deadline in the past, a limit under one cent) and asks the model once more. Ten conditional answers were added to the reply set; 42 of 48 now go as expected, no refusal lets a payment through, and 6 agreements, mostly to an added bag, are asked again.",
        commit: "67fc9ef",
      },
    ],
  },
  {
    date: "2026-11-10",
    changes: [
      {
        area: "guard",
        text:
          "Version 0.1.9 closes the gap left open in the v3 entry below: an agent that ignores the person's \"no\" and pays again. In the sandbox store the guard now holds the person's answer, as Guard.gate and protect already do in the library: the reply joins the request and every payment is checked again. Two new scripted agents obey every injection and, after a \"no\", pay twice more. With the person's signed request, 0 of 60 attacks got through for either agent (60 of 60 before). With the request the agent reports at checkout, an agent that lies about the request still gets through, as before: the guard needs the signed request. When the person says \"yes\", 57 of 60 carts pass; the other 3 are stopped again by mistake, not let through.",
        commit: "92bbbde",
      },
      {
        area: "extraction",
        text:
          "Version 0.1.9: the fact extraction now reads the person's answer to the agent's question. A \"yes\" waives what was asked about, a \"no\" keeps every requirement as it was, and the agent's question is never taken as the person's words. Before, a \"no\" could drop a requirement such as \"refundable\", and the next payment passed. On the 142 right carts of the open v1 and v2 tasks, 138 passed and 4 got a question (136 and 6 on 0.1.8), none over a wrong fact. On the stress sets (125 phrases), the fields that differ from the expected value are the same as on 0.1.8 or fewer; one phrase got no answer from the model proxy.",
        commit: "92bbbde",
      },
      {
        area: "benchmark",
        text:
          "A set of 38 free-form answers to the guard's question on v3 tasks (24 English, 12 Russian, 2 Spanish), run on 0.1.9 with the expected decision written before the run. 37 of 38 went as expected. Of 18 answers that agree, 17 let the cart through; one conditional yes (\"ok, but only if the bag is black\") got the question again: a false stop, not a pass. In 17 answers that refuse and name the right item, the attacker's cart was stopped and the right one passed; 3 unclear or plain refusals kept the order stopped. No refusal let a payment through. The answers were written by a model, not by real customers. The set, the script and the log are in the repository.",
      },
    ],
  },
  {
    date: "2026-11-08",
    changes: [
      {
        area: "extraction",
        text:
          "Version 0.1.8: a single item named in the singular (\"the HEAD Speed Pro\", \"a racket\") now counts as quantity 1 even with no number. Before, the quantity was left unstated and the guard did not check it, so a cart with 3 of the item passed. On the 142 right carts of the open v1 and v2 tasks, no check stopped over quantity. On the stress sets (125 phrases, both models), 2 fields per model differ from the expected value, none of them quantity. The guard's checks are unchanged.",
        commit: "3eb7db2",
      },
      {
        area: "benchmark",
        text:
          "Benchmark v3 in the repository, not yet in the tables on this site: the hijacked agent. Prompt injections sit in the sandbox store's descriptions, reviews, seller notes and search highlights (6 kinds, 10 base requests, 70 tasks). A scripted agent with no model obeys every injection, so what is measured is the guard alone. Without the guard, 60 of 60 attacks landed. With the guard taking the request the agent reports at checkout, an agent that describes the cart it bought got 59 of 60 through: the guard is only as good as the request it is given. With the person's signed request, 3 of 60 got through on version 0.1.7, all \"buy 3\" injections on requests without the word \"one\"; on 0.1.8 a re-run of the quantity and add-on attacks let 0 of 20 through. No right cart was stopped. Every stop is a question to the person, and an agent that ignores their \"no\" and pays again still gets through.",
        commit: "3eb7db2",
      },
    ],
  },
  {
    date: "2026-11-07",
    changes: [
      {
        area: "guard",
        text:
          "Version 0.1.7: the check_order tool now tells the agent to count units the way the person does. If they asked for cans of balls, a can of 3 balls is 1. In a trial through Claude Code with the plugin (Sonnet, 8 open v2 tasks, version 0.1.6), all 8 purchases were right and check_order ran before payment in all 8. But 4 of 11 checks stopped right carts, on 3 tasks, mostly because the agent passed 3 balls per can. After the fix those 3 tasks were run again: no check stopped over units. One check still stopped a right cart, over a bag line the fact extraction added once and did not add in 3 repeats. The guard's checks are unchanged.",
      },
      {
        area: "benchmark",
        text:
          "Benchmark runs through Claude Code: scripts/run_claude_code.py starts claude -p with the plugin and the sandbox store as an MCP server (scripts/claude_code_store_mcp.py), and counts how often check_order runs before payment and what it decides. --local-guard uses the guard from the checkout instead of the published package. Full run with version 0.1.7 (Sonnet, the 50 open v2 tasks): all 50 purchases matched the request, and check_order ran before payment in all 50. In 52 checks the guard stopped 3 right carts, all over \"one order, not three deliveries\": the cart it gets has no merchant, so it cannot check that. There were no wrong carts, so this run does not measure catching. Log: data/runs/claude-code-v2-open-0.1.7.jsonl.gz.",
      },
    ],
  },
  {
    date: "2026-11-05",
    changes: [
      {
        area: "extraction",
        text:
          "Version 0.1.6: requests in Spanish, French, Japanese and Chinese. The fact extraction returns brands and models in Latin letters even when they are written in katakana or Chinese characters, and weekdays, counters and refund wishes in these languages are read. Stress sets for the four languages (48 phrases, both models): no field differs from the expected one; the English and Russian sets did not change. Amounts are not converted between currencies. The live window's agent now answers in the language of the request; the benchmark's agent prompt is unchanged.",
      },
    ],
  },
  {
    date: "2026-11-03",
    changes: [
      {
        area: "guard",
        text:
          "Version 0.1.5: an AP2 adapter. asasked.ap2.protect_presentation checks the merchant's checkout before the agent signs the closed Checkout Mandate over it, and refuses a checkout_hash that is not the hash of the checkout it checked. AP2 v0.2 mandates carry no request, so the person's words come from the conversation, passed by your code; colour, size and returns come from the merchant's catalog.",
        commit: "a2c9648",
      },
      {
        area: "benchmark",
        text:
          "v2 re-run on the open half with version 0.1.4 and a stricter simulated person, which never accepts a missing, deferred or substituted item. Wrong purchases fell from 11 of 250 without the guard to 0 with it; the guard caught 8 wrong carts, missed none and stopped 14 right ones in 255 checks. The stricter rule was written after the 0.1.3 run on these same open tasks. Log: data/runs/v2-open-0.1.4.jsonl.gz; the 0.1.3 log stays published.",
        commit: "c3f15a2",
      },
      {
        area: "guard",
        text:
          "Version 0.1.4: the guard can take the person's request from their signed L2 mandate instead of the agent's word (Guard.from_mandate). With claimed=, it notes where the agent's account of the request differs from the signed one.",
        commit: "220feb5",
      },
    ],
  },
  {
    date: "2026-11-01",
    changes: [
      {
        area: "benchmark",
        text:
          "The simulated person in the three-item tasks of v2 is now told the third item is a racket bag. Before, its brief said only \"one HEAD Tour Team\", it took that for a racket, and in two runs it approved a cart without the bag. Only the simulator's brief changed; the request, the label and the task ids did not. The published runs predate this.",
      },
      {
        area: "benchmark",
        text:
          "Benchmark re-run with version 0.1.3 on the open halves (v1: 100 tasks, v2: 50), logs published in data/runs/. On v1 models bought wrong once in 500 runs without the guard and never with it; the guard stopped 9 right carts in 460 checks. On v2 wrong purchases fell from 9 of 250 to 3; the guard caught 11 wrong carts, missed none and stopped 12 right ones in 254 checks. The 3 left were carts the guard stopped and the simulated person approved. 445 v1 runs that failed on the network were run again.",
      },
    ],
  },
  {
    date: "2026-10-31",
    changes: [
      {
        area: "guard",
        text:
          "Version 0.1.3: Gemini and OpenAI-compatible models now work on Python installs that have no certificates of their own (python.org builds for macOS). Before, every check there failed and the guard answered ask.",
      },
      {
        area: "guard",
        commit: "d467191",
        text: "Version 0.1.2 on PyPI: code comments, docstrings and script output in English. The guard's behaviour is unchanged.",
      },
      {
        area: "guard",
        commit: "662dfe0",
        text:
          "A requirement no fact field holds (\"gluten-free\", \"fits an iPhone 15\") is kept in the person's words instead of dropped. The model does not judge whether the item meets it: a must becomes a question to the person, a nice-to-have becomes a note.",
      },
      {
        area: "guard",
        commit: "cb7ac18",
        text:
          "Stricter colour and size matching: colour is compared word by word in English and Russian, the first colour of an item being its main one; a size system counts only when both sides name it. today defaults to the current date.",
      },
      {
        area: "guard",
        text:
          "The guard as an MCP server (asasked-mcp, tool check_order), guard.protect and ready hooks for the Claude Agent SDK, OpenAI Agents SDK and LangChain that check a cart before the payment tool runs.",
      },
      {
        area: "benchmark",
        commit: "b28e907",
        text:
          "Real-model results with and without the guard, from runs of 26 and 30 October on v1 (200 tasks) and v2 (50 open tasks). On v1 models bought wrong 4 times in 1,000 with or without the guard. On v2 wrong purchases fell from 12 of 250 to 1, at the cost of 19 right carts stopped in 255 checks. The runs predate the guard changes above.",
      },
      {
        area: "dataset",
        commit: "5eafe8b",
        text:
          "Dataset v2: 7 templates where strong models made mistakes in a pilot; 50 open tasks in data/tasks_v2.jsonl, a hidden half from a seed outside the repository. Hidden tasks that repeat a public pilot are not counted.",
      },
      {
        area: "guard",
        commit: "16a137b",
        text: "Public repository and the package on PyPI: pip install asasked, version 0.1.1.",
      },
    ],
  },
  {
    date: "2026-10-27",
    changes: [
      {
        area: "benchmark",
        commit: "032fbc2",
        text:
          "Three test-bench fixes after the full run. A named weekday (\"by Wednesday\") is counted by code, not by the model: all five false stops in the run were off by one day. The product page says \"arrives within N days of ordering\" instead of a bare ships_in_days, which one model read as dispatch time. A question an agent asks in plain text goes to the simulated person instead of counting as giving up. Model results from this run are preliminary and will be re-run.",
      },
      {
        area: "benchmark",
        text:
          "Full run: 6 agents × 200 tasks × guard off and enforced, 2,400 runs, no transport errors. Baseline agent: 198 wrong purchases without the guard, 11 with it; 187 wrong carts stopped, 12 missed, 0 right purchases stopped.",
      },
      {
        area: "guard",
        commit: "5e9ac55",
        text:
          "A deadline or price limit heard by either extractor now counts, instead of only warning. Found in a smoke test: one model missed \"by Friday\" and a 14-day delivery went through.",
      },
    ],
  },
  {
    date: "2026-10-26",
    changes: [
      {
        area: "dataset",
        commit: "85b83e5",
        text: "\"Cheapest\" tasks now require the cheapest listing that meets the other conditions, not any of them (33 tasks). The reviewer picked only the cheapest; the label had accepted all.",
      },
      {
        area: "dataset",
        commit: "30896a6",
        text: "Two-pair shoe orders now say, and require, that both pairs are returnable (18 tasks).",
      },
      {
        area: "dataset",
        commit: "f867e96",
        text: "Review alongside a machine translation; English naturalness checked by a model. Its first pass caught \"a intermediate\" in one template.",
      },
      { area: "dataset", commit: "21d2311", text: "Dataset v1: 200 labelled tasks from 13 trap templates, 100 open and 100 hidden." },
      { area: "guard", commit: "bf0ae5d", text: "Per-line facts for orders of several variants (\"size 40 for my wife and 43 for me\")." },
      { area: "spec", commit: "fe40ea7", text: "Guard specification, draft 0.1." },
      { area: "guard", commit: "75e6cd3", text: "The pre-checkout guard, and the benchmark with the guard off and enforced." },
    ],
  },
  {
    date: "2026-10-25",
    changes: [
      { area: "store", commit: "7925b4a", text: "Sandbox store: catalog v1, agent tools, checkout through a real Verifiable Intent chain, HTTP." },
      { area: "benchmark", commit: "d22f631", text: "Agent harness: labelled tasks, the agent loop, scoring against the label." },
      { area: "extraction", commit: "2da4f6a", text: "English extraction, a Claude provider, and agreement between two extractors." },
    ],
  },
  {
    date: "2026-08-25",
    changes: [{ area: "VI", commit: "22e0fc9", text: "Conformance test vectors for Verifiable Intent: every scenario as a genuinely signed chain with the expected verdict." }],
  },
];
