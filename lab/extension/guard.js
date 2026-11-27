// The guard: pure checks, no page access. Each returns a list of lines {ok: true|false|null, text}.
// ok === null means "could not check" and never counts as a pass.
var AsGuard = (function () {
  const USDC_SOL_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
  const norm = (s) =>
    String(s || "")
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9.]+/g, " ")
      .trim();
  const money = (s) => {
    const t = String(s || "").replace(/[^0-9.,]/g, "");
    if (!t) return NaN;
    // "1.234,56" or "1,234.56" or "483"
    const lastSep = Math.max(t.lastIndexOf("."), t.lastIndexOf(","));
    if (lastSep > -1 && t.length - lastSep - 1 === 2) return Number(t.slice(0, lastSep).replace(/[.,]/g, "") + "." + t.slice(lastSep + 1));
    return Number(t.replace(/[.,]/g, ""));
  };
  const currencyOf = (s) => {
    s = String(s || "");
    if (s.includes("€")) return "EUR";
    if (s.includes("£")) return "GBP";
    if (s.includes("CHF")) return "CHF";
    if (s.includes("$")) return "USD";
    return "";
  };
  const fmt = (n, c) => (isFinite(n) ? `${n.toFixed(2)} ${c || ""}`.trim() : "?");

  // The cart on the store's checkout against what the person chose on lab.asasked.dev.
  // order: {title, size, price, currency}; cart: {items: [{name, qty, total}], subtotal, total, currency}
  function cart(order, c) {
    const out = [];
    if (!order) {
      out.push({ ok: null, text: "No order from AsAsked Lab in this browser. Click Buy on lab.asasked.dev first." });
      return out;
    }
    if (c.items.length !== 1) out.push({ ok: false, text: `The cart has ${c.items.length} different items; you chose one.` });
    const item = c.items[0];
    if (item) {
      const words = norm(order.title).split(" ").filter((w) => w.length > 2);
      const name = norm(item.name);
      const hit = words.filter((w) => name.includes(w)).length;
      out.push(
        words.length && hit / words.length >= 0.8
          ? { ok: true, text: `Product: ${order.title}` }
          : { ok: false, text: `Product in the cart is “${item.name}”, you chose “${order.title}”.` },
      );
      if (order.size) {
        // The store appends the chosen option to the item name: "… - 42" (shoe size) or "… - Near Mint" (card condition).
        const want = norm(order.size);
        const label = /^[0-9.]+$/.test(want) ? "Size" : "Option";
        const m = name.match(/ ([0-9]+(?:\.[0-9])?) *$/);
        const seen = label === "Size" && m ? m[1] : "";
        // Compare the whole part after the last " - ", so "Played" never passes for "Lightly Played".
        const cut = String(item.name).lastIndexOf(" - ");
        const tail = cut > -1 ? norm(String(item.name).slice(cut + 3)) : "";
        out.push(
          (cut > -1 ? tail === want : name.endsWith(" " + want))
            ? { ok: true, text: `${label} ${order.size}` }
            : { ok: false, text: seen ? `Size in the cart is ${seen}, you chose ${order.size}.` : `Could not find ${label.toLowerCase()} ${order.size} in the cart.` },
        );
      }
      out.push(item.qty === 1 ? { ok: true, text: "Quantity 1" } : { ok: false, text: `Quantity is ${item.qty}, not 1.` });
      if (c.currency && order.currency && c.currency !== order.currency)
        out.push({ ok: null, text: `The store shows ${c.currency}, the listing was in ${order.currency}. Check the price yourself.` });
      else if (isFinite(item.total) && isFinite(order.price))
        out.push(
          Math.abs(item.total - order.price) <= Math.max(0.01, order.price * 0.005)
            ? { ok: true, text: `Price ${fmt(item.total, c.currency)}, as listed` }
            : { ok: false, text: `Price is ${fmt(item.total, c.currency)}, listed at ${fmt(order.price, order.currency)}.` },
        );
    }
    if (isFinite(c.total) && isFinite(c.subtotal) && c.total > c.subtotal)
      out.push({ ok: true, text: `Shipping and fees add ${fmt(c.total - c.subtotal, c.currency)}. Total ${fmt(c.total, c.currency)}.` });
    else if (isFinite(c.total)) out.push({ ok: true, text: `Total ${fmt(c.total, c.currency)}` });
    return out;
  }

  // BitPay payment options (JSON Payment Protocol v2) against the order snapshot taken on the checkout.
  // opts: response of GET /i/<id>; snap: {total, currency, merchant}; usdPer: how many USD one unit of snap.currency is.
  function options(opts, snap, usdPer) {
    const out = [];
    const memo = String(opts.memo || "");
    const m = memo.match(/for merchant (.+)$/i);
    const merchant = m ? m[1].trim() : "";
    if (!snap) out.push({ ok: null, text: "No checkout from this browser to compare with. Check the amount yourself." });
    else
      out.push(
        merchant && norm(merchant).includes(norm(snap.merchant).split(" ")[0])
          ? { ok: true, text: `Invoice is for ${merchant}` }
          : { ok: false, text: `Invoice is for “${merchant || "unknown"}”, not ${snap.merchant}.` },
      );
    const exp = Date.parse(opts.expires);
    if (isFinite(exp)) out.push(exp > Date.now() ? { ok: true, text: `Expires in ${Math.max(0, Math.round((exp - Date.now()) / 60000))} min` } : { ok: false, text: "The invoice has expired." });
    const o = (opts.paymentOptions || []).find((x) => x.chain === "SOL" && x.currency === "USDC");
    if (!o) {
      out.push({ ok: false, text: "This invoice does not offer USDC on Solana." });
      return { lines: out, option: null };
    }
    out.push(o.network === "main" ? { ok: true, text: "USDC on Solana mainnet is offered" } : { ok: false, text: `Network is ${o.network}, not mainnet.` });
    const usdc = Number(o.estimatedAmount) / Math.pow(10, Number(o.decimals || 6));
    out.push(amount(usdc, snap, usdPer));
    return { lines: out, option: o, usdc };
  }

  function amount(usdc, snap, usdPer) {
    if (!snap || !isFinite(snap.total)) return { ok: null, text: `Amount ${usdc.toFixed(2)} USDC. No order total to compare with.` };
    if (!isFinite(usdPer)) return { ok: null, text: `Amount ${usdc.toFixed(2)} USDC for ${fmt(snap.total, snap.currency)}. No exchange rate; check it yourself.` };
    const want = snap.total * usdPer;
    const diff = (usdc - want) / want;
    // USDC is not exactly 1 USD and BitPay rounds; allow 2% over, any amount under.
    if (diff > 0.02) return { ok: false, text: `Amount ${usdc.toFixed(2)} USDC is ${(diff * 100).toFixed(1)}% more than the order (${snap.currency === "USD" ? fmt(want, "USD") : `${fmt(snap.total, snap.currency)} ≈ ${fmt(want, "USD")}`}).` };
    if (diff < -0.05) return { ok: false, text: `Amount ${usdc.toFixed(2)} USDC is much less than the order (${want.toFixed(2)} USD). Something is off.` };
    return { ok: true, text: `Amount ${usdc.toFixed(2)} USDC for ${fmt(snap.total, snap.currency)}` };
  }

  // Payment request for SOL/USDC: what the wallet will actually be asked to send.
  function request(req, opt) {
    const out = [];
    out.push(req.chain === "SOL" && req.network === "main" ? { ok: true, text: "Network: Solana mainnet" } : { ok: false, text: `Network: ${req.chain} ${req.network}` });
    const outputs = [];
    for (const ins of req.instructions || []) for (const o of ins.outputs || []) outputs.push(o);
    if (outputs.length !== 1) out.push({ ok: outputs.length ? null : false, text: `${outputs.length} payment outputs; expected one.` });
    const o = outputs[0];
    if (o) {
      const usdc = Number(o.amount) / Math.pow(10, Number((opt && opt.decimals) || 6));
      if (opt && Number(o.amount) !== Number(opt.estimatedAmount)) out.push({ ok: false, text: `Amount to send ${usdc.toFixed(6)} USDC differs from the quoted one.` });
      else out.push({ ok: true, text: `Send exactly ${usdc.toFixed(6)} USDC` });
      out.push({ ok: null, text: `To ${o.address}. Check that your wallet shows the same first and last 4 characters.` });
    }
    // If BitPay names the token mint anywhere, it must be the real USDC mint.
    const mints = JSON.stringify(req).match(/[1-9A-HJ-NP-Za-km-z]{43,44}/g) || [];
    const tokenish = JSON.stringify(req).match(/"(mint|tokenAddress|splToken|token)"\s*:\s*"([^"]+)"/i);
    if (tokenish) out.push(tokenish[2] === USDC_SOL_MINT ? { ok: true, text: "Token is USDC (official mint)" } : { ok: false, text: `Token mint ${tokenish[2]} is not USDC.` });
    else if (!mints.includes(USDC_SOL_MINT)) out.push({ ok: null, text: "BitPay does not name the token mint here. In your wallet, check the token is USDC." });
    return out;
  }

  function verdict(lines) {
    if (lines.some((l) => l.ok === false)) return "stop";
    if (lines.some((l) => l.ok === null)) return "check";
    return "pass";
  }

  return { cart, options, request, amount, verdict, money, currencyOf, norm, USDC_SOL_MINT };
})();
if (typeof module !== "undefined") module.exports = AsGuard;
