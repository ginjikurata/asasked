import type { Metadata } from "next";
import { MERCHANTS } from "@/lib/merchants";

export const metadata: Metadata = {
  title: "What's coming",
  description:
    "AsAsked Lab is in beta. What works now, what is being tested (orders with a guard that checks every cart and invoice) and what comes later.",
};

type Step = { tag: string; title: string; body: string; now?: boolean; links?: [string, string][] };

const STEPS: Step[] = [
  {
    tag: "Live now",
    now: true,
    title: "A list of shops that take crypto, checked one by one",
    body: `${MERCHANTS.length} stores where we found signs they take crypto, products you can open in their cart in one click, and gift cards for big brands that don't take crypto yet.`,
    links: [["/stores", "Browse stores"], ["/search", "Search products"]],
  },
  {
    tag: "Live now",
    now: true,
    title: "Ask in your own words, keep your sizes with your wallet",
    body: "Type “black loafers, size 42, under $500” instead of filters, and the AsAsked guard shows what fits your request and what doesn't. Sign in by signing a short text (no transaction, no fee) to keep your sizes, budget and stores. One button deletes everything.",
    links: [["/search", "Try a search"], ["/account", "Your account"]],
  },
  {
    tag: "Live now",
    now: true,
    title: "Connect your own agent",
    body: "Claude, ChatGPT or any agent that supports MCP can search the catalog, check products against what you asked and save carts to your account. You give it access with your wallet and can take it back at any moment. It can't place an order, see your address or pay.",
    links: [["/account", "Connect an agent"]],
  },
  {
    tag: "Ready · first orders being tested",
    now: true,
    title: "Order at Bottega Senatore, you sign",
    body: "The store cart is built for you and the guard checks it against your request. You place the order on the page, then the guard checks the BitPay invoice: seller, amount, network and expiry. Your address is locked with your wallet and opened only for that one order. You pay from your own wallet.",
    links: [["/demo", "See it on test shops"]],
  },
  {
    tag: "Live now · early version",
    now: true,
    title: "Our own agent, in a chat",
    body: "Ask in a chat on the site. The agent searches, checks each result against what you asked, saves a cart and prepares an order at Bottega Senatore, with the same guard and the same rules. It can't place the order or pay: you do that from your own wallet.",
    links: [["/chat", "Open the chat"]],
  },
  {
    tag: "Later",
    title: "Let the agent pay within a limit you set",
    body: "Give the agent an allowance you choose and can revoke at any moment. Anything the guard isn't sure about still waits for you. This comes only after a legal review and an independent security check.",
  },
];

const RULES = [
  "We never hold your money or your keys. You pay the store directly.",
  "If a store blocks bots, our agent doesn't shop there. We don't get around captchas or bot protection.",
  "Crypto payments can't be reversed, so the guard asks you whenever a cart doesn't match what you said.",
];

export default function Coming() {
  return (
    <main className="column pt-10 sm:pt-14">
      <p className="inline-flex items-center gap-2 rounded-full border border-signal/30 bg-signal-soft px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-signal-ink">
        Beta
      </p>
      <h1 className="mt-4 text-[32px] font-semibold leading-[1.08] tracking-[-0.02em] sm:text-[44px]">
        From a list of shops to an agent that buys as you asked
      </h1>
      <p className="mt-3 max-w-[60ch] text-[17px] text-muted">
        AsAsked Lab is in beta. Here is where it is going. No dates: each step ships when it is safe, not before.
      </p>

      <ol className="relative ml-4 mt-12 border-l border-line">
        {STEPS.map((s, i) => (
          <li key={s.title} className={`relative pl-9 ${i < STEPS.length - 1 ? "pb-10" : ""}`}>
            <span
              className={`absolute -left-4 top-0 grid size-8 place-items-center rounded-full border font-mono text-[12px] ${
                s.now ? "border-pass bg-pass text-white" : "border-line bg-panel text-signal-ink"
              }`}
            >
              {s.now ? "✓" : `0${i - STEPS.filter((x) => x.now).length + 1}`}
            </span>
            <p className={`pt-1.5 font-mono text-[11px] uppercase tracking-wider ${s.now ? "text-pass" : "text-faint"}`}>{s.tag}</p>
            <h2 className="mt-1 text-[19px] font-semibold tracking-[-0.01em]">{s.title}</h2>
            <p className="mt-1.5 max-w-[60ch] text-[15px] text-muted">{s.body}</p>
            {s.links && (
              <p className="mt-3 flex flex-wrap gap-2 text-sm">
                {s.links.map(([href, label]) => (
                  <a key={href + label} href={href} className="rounded-full border border-line bg-panel px-3.5 py-1.5 hover:border-ink">
                    {label}
                  </a>
                ))}
              </p>
            )}
          </li>
        ))}
      </ol>

      <section className="mt-16 rounded-3xl bg-panel p-5 sm:p-8">
        <h2 className="text-[22px] font-semibold tracking-[-0.01em]">What won&apos;t change</h2>
        <ul className="mt-4 flex flex-col gap-3">
          {RULES.map((r) => (
            <li key={r} className="flex gap-3 text-[15px]">
              <span className="mt-[7px] size-2 shrink-0 bg-signal" aria-hidden />
              {r}
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-10 text-sm text-muted">
        Questions or a store we should check? Write to{" "}
        <a href="https://x.com/asaskedconcord" className="link text-ink">
          @asaskedconcord
        </a>{" "}
        on X.
      </p>
    </main>
  );
}
