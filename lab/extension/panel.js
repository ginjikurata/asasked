// A small panel in the page corner, inside a shadow root so the store's styles don't touch it.
var AsPanel = (function () {
  let root;
  function mount() {
    if (root) return root;
    const host = document.createElement("div");
    host.id = "asasked-lab-panel";
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;max-width:min(360px,calc(100vw - 32px))";
    document.documentElement.appendChild(host);
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      :host{all:initial}
      .p{font:13px/1.4 system-ui,-apple-system,sans-serif;color:#1d1b18;background:#faf8f4;border:1px solid #d9d3c7;border-radius:14px;box-shadow:0 12px 40px -12px rgba(0,0,0,.3);padding:12px 14px}
      h2{font-size:13px;font-weight:600;margin:0 0 6px;display:flex;gap:8px;align-items:center}
      h2 span{font:500 10px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:#6b655c}
      .x{margin-left:auto;border:0;background:none;font-size:16px;cursor:pointer;color:#6b655c}
      ul{list-style:none;margin:6px 0;padding:0;max-height:40vh;overflow:auto}
      li{padding:2px 0 2px 20px;position:relative;word-break:break-word}
      li:before{position:absolute;left:0;font-weight:700}
      li.ok:before{content:"✓";color:#2f7a4a} li.bad:before{content:"✕";color:#b3261e} li.q:before{content:"?";color:#9a6a0c}
      .v{border-radius:8px;padding:6px 8px;font-weight:600;margin:6px 0}
      .v.pass{background:#2f7a4a1a;color:#2f7a4a}.v.check{background:#c98a121a;color:#9a6a0c}.v.stop{background:#b3261e1a;color:#b3261e}
      p{margin:6px 0} .m{color:#6b655c;font-size:12px}
      button.b{font:inherit;border:1px solid #1d1b18;background:#1d1b18;color:#faf8f4;border-radius:999px;padding:6px 12px;cursor:pointer;margin:4px 6px 0 0}
      button.b.s{background:transparent;color:#1d1b18}
      button.b:disabled{opacity:.5;cursor:default}
    </style><div class="p" role="region" aria-label="AsAsked Lab checkout helper"><h2>AsAsked Lab <span>beta</span><button class="x" aria-label="Hide">×</button></h2><div class="c"></div></div>`;
    root.querySelector(".x").onclick = () => (host.style.display = "none");
    return root;
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const VERDICT = { pass: "Matches what you chose", check: "Check the marked lines yourself", stop: "Stop: something does not match" };
  // parts: [{lines}] | [{html}] | [{button, onClick, secondary}]
  function render(parts) {
    const c = mount().querySelector(".c");
    c.innerHTML = "";
    for (const part of parts) {
      if (part.lines) {
        const v = AsGuard.verdict(part.lines);
        if (part.title) c.insertAdjacentHTML("beforeend", `<p><b>${esc(part.title)}</b></p>`);
        if (!part.noVerdict) c.insertAdjacentHTML("beforeend", `<div class="v ${v}">${VERDICT[v]}</div>`);
        c.insertAdjacentHTML(
          "beforeend",
          `<ul>${part.lines.map((l) => `<li class="${l.ok === true ? "ok" : l.ok === false ? "bad" : "q"}">${esc(l.text)}</li>`).join("")}</ul>`,
        );
      } else if (part.text) c.insertAdjacentHTML("beforeend", `<p class="${part.muted ? "m" : ""}">${esc(part.text)}</p>`);
      else if (part.button) {
        const b = document.createElement("button");
        b.className = "b" + (part.secondary ? " s" : "");
        b.textContent = part.button;
        b.disabled = Boolean(part.disabled);
        b.onclick = part.onClick;
        c.appendChild(b);
      }
    }
  }
  return { render };
})();
