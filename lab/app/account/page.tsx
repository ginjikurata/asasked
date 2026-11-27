import type { Metadata } from "next";
import { Account } from "@/components/Account";
import { MERCHANTS } from "@/lib/merchants";

export const metadata: Metadata = {
  title: "Your account",
  description: "Sizes, budget and favourite stores tied to your wallet, and access for your own agent.",
};

export default function AccountPage() {
  const stores = MERCHANTS.filter((m) => m.status === "yes")
    .map((m) => ({ name: m.name, domain: m.domain }))
    .sort((a, b) => a.name.localeCompare(b.name));
  return (
    <main className="column pt-10 pb-20 sm:pt-14">
      <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] sm:text-[44px]">Your account</h1>
      <p className="mt-3 max-w-[60ch] text-muted">
        Tied to your wallet. Save your sizes and budget once, then let your own agent (Claude, ChatGPT or another) search the
        catalog with them and save carts here for you to review. No agent can pay or place an order.
      </p>
      <Account stores={stores} />
    </main>
  );
}
