// On a BitPay invoice: read the invoice through BitPay's public JSON Payment Protocol and check it
// against the checkout this browser just filled. The person still pays from their own wallet.
(function () {
  const id = (location.pathname.match(/^\/i\/([A-Za-z0-9]+)/) || [])[1] || new URLSearchParams(location.search).get("id");
  if (!id || !/^[A-Za-z0-9]{10,40}$/.test(id)) return;
  const url = `https://bitpay.com/i/${id}`;
  const H = { "X-Paypro-Version": "2" };

  async function getJSON(u, init) {
    const r = await fetch(u, init);
    if (!r.ok) throw new Error(`${r.status} ${await r.text().catch(() => "")}`.slice(0, 200));
    return r.json();
  }
  // How many USD one unit of `cur` is, from BitPay's public rates (both quoted against BTC).
  async function usdPer(cur) {
    if (!cur || cur === "USD") return 1;
    try {
      const [usd, other] = await Promise.all([getJSON("https://bitpay.com/rates/BTC/USD"), getJSON(`https://bitpay.com/rates/BTC/${cur}`)]);
      return usd.data.rate / other.data.rate;
    } catch {
      return NaN;
    }
  }

  let first, option;
  async function start() {
    AsPanel.render([{ text: "Reading the invoice…", muted: true }]);
    const r = await new Promise((res) => chrome.storage.local.get(["checkout"], res));
    const snap = r.checkout && Date.now() - Date.parse(r.checkout.at) < 2 * 36e5 ? r.checkout : null;
    try {
      const opts = await getJSON(url, { headers: { ...H, Accept: "application/payment-options" } });
      const rate = snap ? await usdPer(snap.currency) : NaN;
      first = AsGuard.options(opts, snap, rate);
      option = first.option;
      const parts = [{ title: "Invoice check", lines: first.lines }];
      if (option)
        parts.push(
          { text: "Next: see exactly what your wallet will be asked to send. This picks USDC on Solana for this invoice, the same as choosing it on this page.", muted: true },
          { button: "Check USDC on Solana", onClick: details },
        );
      AsPanel.render(parts);
    } catch (e) {
      AsPanel.render([{ lines: [{ ok: null, text: `Could not read this invoice (${e.message}). Check the amount and merchant on the page yourself.` }] }]);
    }
  }

  async function details() {
    try {
      const req = await getJSON(url, {
        method: "POST",
        headers: { ...H, "Content-Type": "application/payment-request" },
        body: JSON.stringify({ chain: "SOL", currency: "USDC" }),
      });
      const lines = first.lines.concat(AsGuard.request(req, option));
      AsPanel.render([
        { title: "Invoice check", lines },
        { text: "If everything matches, pay from your own wallet (for example Phantom) and compare the address and amount it shows with the lines above. Nothing is sent from here.", muted: true },
      ]);
    } catch (e) {
      AsPanel.render([{ title: "Invoice check", lines: first.lines.concat([{ ok: null, text: `Could not get payment details (${e.message}).` }]) }]);
    }
  }

  start();
})();
