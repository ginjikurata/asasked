import type { Metadata } from "next";
import { Chat } from "@/components/Chat";

export const metadata: Metadata = {
  title: "Chat",
  description: "Ask in a chat. The agent searches stores that take crypto, checks each result and prepares an order. You place it and pay.",
};

export default function ChatPage() {
  return (
    <main className="column pt-10 pb-20 sm:pt-14">
      <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] sm:text-[44px]">Chat</h1>
      <p className="mt-3 max-w-[60ch] text-muted sm:hidden">
        Ask in your own words. The agent searches and checks; you place the order and pay.
      </p>
      <details className="meta mt-2 sm:hidden">
        <summary className="cursor-pointer py-2">How it works</summary>
        <p className="mt-1">
          Same tools and guard as your own agent over MCP. It can save a cart and prepare an order at Bottega Senatore, never
          place it or pay. Early version: if the model is slow or down, simple rules answer, so short requests work best.
        </p>
      </details>
      <p className="mt-3 hidden max-w-[60ch] text-muted sm:block">
        Ask in your own words. The agent uses the same tools and the same guard as your own agent over MCP: it searches,
        checks each result against what you asked, saves a cart and prepares an order at Bottega Senatore. It cannot place an
        order or pay. You do that on <a href="/account" className="link text-ink">your account</a>, from your own wallet.
      </p>
      <p className="meta mt-3 hidden max-w-[60ch] sm:block">
        Early version. A Claude model reads your request and calls the tools; if it is unavailable, a backup model
        answers. If that fails too, simple rules answer, and short requests like save 1, details 2 or more work best then.
      </p>
      <Chat />
    </main>
  );
}
