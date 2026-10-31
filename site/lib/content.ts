// Site content in one place. Facts only, each one checkable against the repository;
// anything not known yet stays null and renders as a visible placeholder.

export const SITE_URL = "https://asasked.dev";

/** Until launch the site is not indexed (robots.ts). */
export const LAUNCHED = false;

export const GITHUB_URL = "https://github.com/ginjikurata/asasked";

/** The package on PyPI and its current release; the version is the one in pyproject.toml. */
export const VERSION = "0.1.1";
export const PYPI_URL = "https://pypi.org/project/asasked/";
export const RELEASE_URL = `${GITHUB_URL}/releases/tag/v${VERSION}`;

export const CONCORD_URL = "https://concord.solutions";

export const VI_URL = "https://github.com/agent-intent/verifiable-intent";

export const NAV = [
  { href: "/#try", label: "Try it" },
  { href: "/#benchmark", label: "Benchmark" },
  { href: "/spec", label: "Spec" },
  { href: "/docs", label: "Docs" },
  { href: "/dataset", label: "Dataset" },
  { href: "/about", label: "About" },
] as const;

/** Status line in the header: facts about the last benchmark run. */
export const STATUS = "guard v0.1 · last benchmark run 27 Oct 2026 · 2,400 runs, 6 agents";

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
      "Two independent models turn the person's words into facts: brand, colour, size, budget, deadline, returns. " +
      "A fact they disagree on can only warn, never block — except deadlines and price limits, which models miss far more often than they invent.",
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
} as const;

/**
 * Benchmark results. `preliminary` marks numbers from the run of 2026-10-27, made before three
 * test-bench fixes; the models are being re-run, and these figures will be replaced.
 */
export const RESULTS = {
  preliminary: true,
  runDate: "27 October 2026",
  naive: { tasks: 200, wrongWithout: 198, wrongWith: 11, caught: 187, missed: 12, falseStops: 0 },
} as const;

export const LIMITATIONS = [
  "One sport and a catalog we built ourselves. Traps come from the catalog's structure, but it is still our catalog.",
  "One person reviewed the dataset: 44 tasks row by row, every other template through a concrete question about the right purchase. There is no inter-annotator agreement to report.",
  "Strong models rarely buy the wrong item in these tasks; their usual failure is not buying at all. Harder tasks are needed to measure the guard on them.",
  "A vague request cannot be checked: only the person knows the missing details.",
  "Extraction is not bit-reproducible. The deterministic half is, and it is the half that belongs in a dispute.",
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
  updated: "27 October 2026",
} as const;
