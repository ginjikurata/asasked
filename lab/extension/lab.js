// On lab.asasked.dev: when the person clicks Buy, remember what they chose so the checkout helper
// can compare the store's cart with it. Only product facts are kept, in this browser.
document.addEventListener(
  "click",
  (e) => {
    const a = e.target instanceof Element && e.target.closest("a[data-asasked-order]");
    if (!a) return;
    try {
      const order = JSON.parse(a.getAttribute("data-asasked-order"));
      order.at = new Date().toISOString();
      chrome.storage.local.set({ order });
    } catch {}
  },
  true,
);
// Lets the site show "helper installed" if it wants to; carries no data.
document.documentElement.setAttribute("data-asasked-helper", chrome.runtime.getManifest().version);
