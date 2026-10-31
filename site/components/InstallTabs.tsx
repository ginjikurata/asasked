"use client";

import { useEffect, useState } from "react";

export type InstallTab = { id: string; label: string; content: React.ReactNode };

/**
 * One tab per agent app. Every panel is in the page (inactive ones hidden), so all configs are
 * readable without JavaScript; the open tab follows the URL hash, so /install#cursor links to one.
 */
export function InstallTabs({ tabs }: { tabs: InstallTab[] }) {
  const [active, setActive] = useState(tabs[0].id);
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.slice(1);
      if (tabs.some((t) => t.id === id)) setActive(id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, [tabs]);

  const open = (id: string) => {
    setActive(id);
    history.replaceState(null, "", `#${id}`);
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Agent apps">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={active === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => open(t.id)}
            className={`rounded-full border px-3.5 py-1.5 text-[14px] ${
              active === t.id ? "border-ink bg-ink text-paper" : "border-line text-muted hover:border-ink hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`panel-${t.id}`}
          aria-labelledby={`tab-${t.id}`}
          hidden={active !== t.id}
          className="doc mt-8"
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}

/** A code block with a copy button. */
export function CopyCode({ children, title }: { children: string; title?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    let ok = false;
    try {
      await navigator.clipboard.writeText(children);
      ok = true;
    } catch {
      // Clipboard API blocked (insecure context, permissions): fall back to the old copy command.
      const area = document.createElement("textarea");
      area.value = children;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      ok = document.execCommand("copy");
      area.remove();
    }
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };
  return (
    <figure>
      <div className="mb-1 flex items-baseline justify-between gap-4">
        <figcaption className="meta">{title}</figcaption>
        <button type="button" onClick={copy} className="meta hover:text-ink">
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre>
        <code>{children}</code>
      </pre>
    </figure>
  );
}
