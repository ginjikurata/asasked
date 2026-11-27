"use client";

import { useEffect, useState } from "react";

// The home page search box: sends the query to /search. Old links of the form /?q=… go there too.
export function HomeSearch({ placeholder }: { placeholder: string }) {
  const [q, setQ] = useState("");
  useEffect(() => {
    const old = new URLSearchParams(location.search).get("q");
    if (old) location.replace(`/search?q=${encodeURIComponent(old)}`);
  }, []);
  return (
    <form
      role="search"
      action="/search"
      onSubmit={(e) => {
        e.preventDefault();
        const v = q.trim();
        if (v) location.href = `/search?q=${encodeURIComponent(v)}`;
      }}
      className="flex h-14 w-full items-center gap-3 rounded-full border border-line bg-panel pl-5 pr-2 focus-within:border-ink sm:h-16"
    >
      <svg viewBox="0 0 16 16" className="size-[18px] shrink-0 text-faint" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="7" cy="7" r="4.5" />
        <path d="m10.5 10.5 3 3" />
      </svg>
      <input
        type="search"
        name="q"
        aria-label="Search products"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        enterKeyHint="search"
        className="h-full min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-faint sm:text-lg"
      />
      <button
        type="submit"
        aria-label="Search"
        disabled={!q.trim()}
        className="grid size-10 shrink-0 place-items-center rounded-full bg-signal text-white disabled:opacity-40 sm:size-12"
      >
        <svg viewBox="0 0 16 16" className="size-4" aria-hidden fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 13V3M4 7l4-4 4 4" />
        </svg>
      </button>
    </form>
  );
}
