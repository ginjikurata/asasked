"use client";

import { useMemo, useState } from "react";
import tasks from "@/lib/dataset-open.json";
import { TEMPLATES } from "@/lib/content";

type Task = (typeof tasks)[number];

/** The open half of dataset v1: filter by trap template, search the requests. */
export function DatasetBrowser() {
  const [template, setTemplate] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const counts = useMemo(() => {
    const c = new Map<string, number>();
    for (const t of tasks) c.set(t.template, (c.get(t.template) ?? 0) + 1);
    return c;
  }, []);
  const shown = tasks.filter(
    (t: Task) =>
      (!template || t.template === template) &&
      (!query || `${t.request} ${t.id}`.toLowerCase().includes(query.toLowerCase())),
  );
  return (
    <div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Trap templates">
        <button
          type="button"
          aria-pressed={template === null}
          onClick={() => setTemplate(null)}
          className={`rounded-full border px-3 py-1 font-mono text-[12px] ${
            template === null ? "border-ink bg-ink text-paper" : "border-line text-muted hover:border-ink hover:text-ink"
          }`}
        >
          all · {tasks.length}
        </button>
        {[...counts.entries()].map(([key, n]) => (
          <button
            key={key}
            type="button"
            aria-pressed={template === key}
            onClick={() => setTemplate(template === key ? null : key)}
            className={`rounded-full border px-3 py-1 font-mono text-[12px] ${
              template === key ? "border-ink bg-ink text-paper" : "border-line text-muted hover:border-ink hover:text-ink"
            }`}
          >
            {TEMPLATES[key]?.name ?? key} · {n}
          </button>
        ))}
      </div>
      {template && TEMPLATES[template] && <p className="mt-4 text-muted">{TEMPLATES[template].what}</p>}
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="search requests or ids"
        aria-label="Search requests"
        className="mt-5 w-full border-b border-line bg-transparent py-2 font-mono text-[14px] outline-none placeholder:text-faint focus:border-ink"
      />
      <p className="meta mt-3">{shown.length} tasks</p>
      <ol className="mt-4 space-y-4">
        {shown.map((t: Task) => (
          <li key={t.id} className="receipt px-4 pt-3 font-mono text-[12.5px] leading-relaxed">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-faint">{t.id}</span>
              <span className="text-faint">{t.lang === "ru" ? "ru · " : ""}{TEMPLATES[t.template]?.name ?? t.template}</span>
            </div>
            <dl className="mt-2 space-y-1">
              <div className="grid grid-cols-[64px_1fr] gap-3">
                <dt className="text-faint">asks</dt>
                <dd className="font-sans text-[15px] text-ink">“{t.request}”</dd>
              </div>
              <div className="grid grid-cols-[64px_1fr] gap-3">
                <dt className="text-faint">right</dt>
                <dd>{t.label}</dd>
              </div>
              <div className="grid grid-cols-[64px_1fr] gap-3">
                <dt className="text-faint">trap</dt>
                <dd className="text-muted">{t.trap}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ol>
    </div>
  );
}
