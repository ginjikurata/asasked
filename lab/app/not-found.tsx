import type { Metadata } from "next";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="column pt-16 pb-20">
      <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] sm:text-[44px]">Page not found</h1>
      <p className="mt-3 max-w-[60ch] text-muted">There is nothing at this address. Try one of these:</p>
      <ul className="mt-6 flex flex-wrap gap-3 text-sm">
        <li><a href="/" className="link">Home</a></li>
        <li><a href="/stores" className="link">Stores</a></li>
        <li><a href="/search" className="link">Products</a></li>
        <li><a href="/chat" className="link">Chat</a></li>
      </ul>
    </main>
  );
}
