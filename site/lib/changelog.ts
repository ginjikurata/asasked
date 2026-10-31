// What changed in the guard, the dataset, the store and the benchmark, newest first.
// Each entry names the commit it came from; facts only.

export type Change = { area: "guard" | "dataset" | "benchmark" | "store" | "spec" | "extraction" | "VI"; text: string; commit?: string };
export type Day = { date: string; changes: Change[] };

export const CHANGELOG: Day[] = [
  {
    date: "2026-10-31",
    changes: [
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
        text: "Review through a Russian translation; English naturalness checked by a model. Its first pass caught \"a intermediate\" in one template.",
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
