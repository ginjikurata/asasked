// Site content in one place. Facts only, each one checkable against the repository;
// anything not known yet stays null and renders as a visible placeholder.

export const SITE_URL = "https://asasked.dev";

/** Whether search engines may index the site (layout.tsx, robots.ts). Public since 31 October 2026. */
export const LAUNCHED = true;

export const GITHUB_URL = "https://github.com/ginjikurata/asasked";

/** The package on PyPI and its current release; the version is the one in pyproject.toml. */
export const VERSION = "0.1.3";
export const PYPI_URL = "https://pypi.org/project/asasked/";
export const RELEASE_URL = `${GITHUB_URL}/releases/tag/v${VERSION}`;

export const CONCORD_URL = "https://concord.solutions";

export const VI_URL = "https://github.com/agent-intent/verifiable-intent";

export const NAV = [
  { href: "/#try", label: "Try it" },
  { href: "/#benchmark", label: "Benchmark" },
  { href: "/install", label: "Install" },
  { href: "/spec", label: "Spec" },
  { href: "/docs", label: "Docs" },
  { href: "/dataset", label: "Dataset" },
  { href: "/about", label: "About" },
] as const;

/** Status line in the header: facts about the last benchmark run. */
export const STATUS = `guard v${VERSION} · benchmark runs 31 Oct – 1 Nov 2026 · 6 agents`;

/** Constraint types Verifiable Intent v0.1 defines, and what each can express. */
export const VI_CONSTRAINTS = [
  { name: "AllowedMerchant / AllowedPayee", expresses: "who may be paid" },
  { name: "CheckoutLineItems", expresses: "which SKUs, how many" },
  { name: "PaymentAmount / PaymentBudget", expresses: "how much" },
  { name: "PaymentRecurrence / AgentRecurrence", expresses: "how often" },
  { name: "Reference", expresses: "linkage" },
] as const;

export const UNSAID = ["in black", "size 42", "returnable if it doesn't fit", "here by Saturday", "nothing from HEAD"];

export const GUARD_STEPS = [
  {
    n: "01",
    title: "Extract",
    body:
      "A model turns the person's words into facts: brand, colour, size, budget, deadline, returns. One model works; two are safer, " +
      "because a fact they disagree on becomes visible. A disputed fact can only warn, never block — except a deadline, a price limit " +
      "or an item the order lacks, which models miss far more often than they invent. " +
      "A requirement no field holds (\"gluten-free\") is kept in the person's words and asked about, not dropped.",
  },
  {
    n: "02",
    title: "Decide",
    body:
      "Plain deterministic code compares those facts with the cart. No model in this step, so every decision can be checked by hand, " +
      "and the same inputs always give the same answer.",
  },
  {
    n: "03",
    title: "Proceed or ask",
    body:
      "Either the cart matches and payment goes ahead, or the agent gets the reasons and a ready question for the person. " +
      "If the request cannot be checked, the guard asks: it fails closed.",
  },
] as const;

export const STORE = {
  products: 456,
  merchants: 4,
  tasks: 200,
  templates: 13,
  hidden: 100,
  /** Dataset v2: templates where strong models made mistakes in a pilot; the open half is data/tasks_v2.jsonl. */
  v2Open: 50,
  v2Templates: 7,
} as const;

/**
 * Benchmark results, the same figures as README.md ("Results: with and without the guard").
 * One run per task, guard off and on, with AsAsked 0.1.3, open halves only. Computed from the
 * published logs in data/runs/ with scripts/summarize_runs.py.
 */
export const RESULTS = {
  runDates: "31 October – 1 November 2026",
  /** approvedAfterStop: wrong carts the guard stopped and the simulated person then said yes to. */
  naive: { tasks: 100, wrongWithout: 99, wrongWith: 3, caught: 98, missed: 1, falseStops: 0, approvedAfterStop: 2 },
  /** Dataset v1, open half, 100 tasks. Each figure is [guard off, guard on]. */
  v1: [
    { agent: "claude-sonnet-5", asked: [100, 100], wrong: [0, 0], nothing: [0, 0] },
    { agent: "deepseek-v4-flash", asked: [100, 100], wrong: [0, 0], nothing: [0, 0] },
    { agent: "gpt-6-sol", asked: [100, 99], wrong: [0, 0], nothing: [0, 1] },
    { agent: "minimax-m3", asked: [100, 100], wrong: [0, 0], nothing: [0, 0] },
    { agent: "nemotron-3.5-lightning", asked: [95, 95], wrong: [1, 0], nothing: [4, 5] },
  ],
  v1Checks: { checks: 460, caught: 1, missed: 0, falseStops: 9 },
  /** Dataset v2, open half, 50 tasks. */
  v2: [
    { agent: "claude-sonnet-5", asked: [48, 48], wrong: [2, 1], nothing: [0, 1] },
    { agent: "deepseek-v4-flash", asked: [49, 49], wrong: [0, 1], nothing: [1, 0] },
    { agent: "gpt-6-sol", asked: [50, 50], wrong: [0, 0], nothing: [0, 0] },
    { agent: "minimax-m3", asked: [50, 50], wrong: [0, 0], nothing: [0, 0] },
    { agent: "nemotron-3.5-lightning", asked: [39, 45], wrong: [7, 1], nothing: [4, 4] },
  ],
  v2Checks: { checks: 254, caught: 11, missed: 0, falseStops: 12 },
} as const;

export const LIMITATIONS = [
  "One sport and a catalog we built ourselves. Traps come from the catalog's structure, but it is still our catalog.",
  "One person reviewed the dataset: 44 tasks row by row, every other template through a concrete question about the right purchase. There is no inter-annotator agreement to report.",
  "On dataset v1 the guard has little to do for real models: they bought wrong once in 500 runs without it. The clear effect is on a naive agent and on one weaker model in v2.",
  "v2 keeps only templates where strong models made mistakes in a pilot, so the guard has something to catch there. Read its numbers with that in mind.",
  "The benchmark is small and was run once per task, so a difference of one or two tasks is noise. The person answering the agent's questions is simulated by a model, and it can say yes to a wrong cart: every wrong purchase with the guard on in v2 was a cart the guard had stopped. Only the open halves are reported.",
  "A vague request cannot be checked: only the person knows the missing details.",
  "Extraction is not bit-reproducible. The deterministic half is, and it is the half that belongs in a dispute.",
  "The hidden half of v1 is not really hidden: the generator's seed is in the repository, so anyone can rebuild it. Treat all 200 v1 tasks as public; v2's hidden seed is kept outside the repository.",
  "The public repository starts on 31 October 2026; the project was developed in a private repository before that.",
] as const;

/** Trap templates of dataset v1, in words: what the person asks and where the agent can slip. */
export const TEMPLATES: Record<string, { name: string; what: string }> = {
  "refund-variant": { name: "Must be returnable", what: "The exact item, but returns are a must; the same item is cheaper as final sale." },
  deadline: { name: "By a day", what: "Needed by a named day; the cheaper listing ships in two weeks." },
  "cheapest-returnable": { name: "Cheapest, but returnable", what: "\"As cheap as possible\" pulls to a shop with no returns." },
  "cheapest-in-time": { name: "Cheapest that arrives in time", what: "The cheapest listing arrives too late." },
  "soft-colour": { name: "Colour, hedged", what: "\"Pink ideally, blue is fine\" — the preferred colour is only on final sale." },
  "all-out-of-stock": { name: "Out of stock everywhere", what: "That exact variant is gone; the right move is to ask, not to substitute." },
  "over-budget": { name: "Over the stated budget", what: "The person's limit is below the cheapest listing; the mandate would allow more." },
  cans: { name: "Cans, not packs", what: "\"Three cans\" — a 4-can pack is one item but four cans." },
  exclusion: { name: "Anything but a brand", what: "Another brand in the same price range is right there; the mandate allows it." },
  "two-sizes": { name: "Two sizes, one order", what: "Two pairs in different sizes, both returnable, from one merchant." },
  vague: { name: "Vague request", what: "Too little to go on; the agent should ask before buying anything." },
  "starter-kit": { name: "A starter kit", what: "A racket and balls together, under a total, returnable and in time." },
};

/** How dataset v1 was reviewed: facts for the dataset page. */
export const REVIEW = {
  rowByRow: 44,
  templatesByQuestion: 9,
  fixed: ["Two-pair shoe orders now say and require that both pairs are returnable (18 tasks).",
    "\"Cheapest\" requests now require the cheapest listing that meets the other conditions (33 tasks)."],
} as const;

/** Who runs the site: the same facts as concord.solutions/legal. */
export const OPERATOR = {
  founders: "Cos Arthro and Ginji Kurata",
  email: "pigeon@concord.solutions",
  hosting: "a server rented from UltaHost in Frankfurt am Main, Germany",
  updated: "31 October 2026",
} as const;
