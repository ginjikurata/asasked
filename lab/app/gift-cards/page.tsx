import type { Metadata } from "next";
import { GIFT_CARDS, cbUrl, giftUrl } from "@/components/giftCards";
import { slug } from "@/lib/catalog";

export const metadata: Metadata = {
  title: "Gift cards for crypto",
  description: `${GIFT_CARDS.length} big brands that don't take crypto, and where to buy their gift cards with crypto.`,
};

export default function GiftCards() {
  const cards = [...GIFT_CARDS].sort((a, b) => a.n.localeCompare(b.n));
  return (
    <main className="wide pt-10 sm:pt-14">
      <h1 className="text-[32px] font-semibold tracking-[-0.02em] sm:text-[42px]">Gift cards for crypto</h1>
      <p className="mt-2 max-w-[62ch] text-muted">
        These brands don&apos;t take crypto on their own checkout. CoinGate and Coinsbee sell their gift cards for crypto;
        you then pay the store with the card. Check the card&apos;s country and the seller&apos;s fee before paying.
      </p>
      <p className="mt-2 max-w-[62ch] text-muted">
        The links below go to CoinGate and Coinsbee because their pages for each brand are easy to link to. Gift card
        sellers from our checked list are on{" "}
        <a href="/stores?c=gift-cards" className="link text-ink">
          Stores → Gift cards
        </a>{" "}
        (Bitrefill, CoinCards, Coinsbee). CoinGate isn&apos;t on that list yet: we haven&apos;t checked it the same way.
      </p>
      <ul className="mt-8 overflow-hidden rounded-xl border border-line">
        {cards.map((g) => {
          const sellers = [
            { name: "CoinGate", url: giftUrl(g) },
            { name: "Coinsbee", url: cbUrl(g) },
          ].filter((x) => x.url);
          return (
            <li
              key={g.n}
              id={slug(g.n)}
              className="flex scroll-mt-16 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line px-4 py-3 first:border-t-0 target:bg-panel"
            >
              <span className="font-medium">{g.n}</span>
              <span className="flex gap-2">
                {sellers.map((x) => (
                  <a
                    key={x.name}
                    href={x.url!}
                    rel="nofollow noopener noreferrer sponsored"
                    target="_blank"
                    className="flex h-9 items-center gap-1 rounded-lg border border-line bg-paper px-3 text-sm hover:border-ink"
                  >
                    {x.name} <span className="text-muted">↗</span>
                  </a>
                ))}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="meta mt-4">
        CoinGate and Coinsbee are separate companies; we don&apos;t sell gift cards. Brand names belong to their owners.
      </p>
    </main>
  );
}
