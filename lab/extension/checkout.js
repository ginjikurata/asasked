// On the store's checkout: fill delivery details the person saved in this extension, choose the crypto
// payment, and check the cart against what they chose on lab.asasked.dev.
// It never fills an account password, never ticks a terms box and never clicks Place order:
// those stay with the person.
(function () {
  // What differs between the stores' WooCommerce checkouts.
  const SITES = {
    "www.bottegasenatore.com": {
      merchant: "Bottega Senatore",
      pay: "payment_method_bitpay_checkout_gateway",
      payName: "BitPay",
      yourPart:
        "Your part: type a password for your new store account, tick the terms box after reading them, then click Place order. On the BitPay page choose USDC on Solana; this helper checks the invoice there.",
      password: true,
    },
    "satoshitcg.com": {
      merchant: "SatoshiTCG",
      pay: "payment_method_sc_crypto",
      payName: "SatoshiTCG crypto",
      // The store's own coin list; Solana is the network the lab wallet tools speak.
      coin: { id: "sc_coin", value: "sol", name: "SOL on Solana" },
      yourPart:
        "Your part: check the coin (SOL on Solana is picked; change it if you pay with another), then click Place order & view crypto payment. The store then shows an address and an exact amount valid for 30 minutes. Send it from your own wallet and click Paid. The store checks payments by hand, so the order stays on hold until then.",
    },
  };
  const site = SITES[location.hostname];
  if (!site) return;
  const MERCHANT = site.merchant;
  const form = document.querySelector('form[name="checkout"]');
  if (!form) return;
  const $ = (s) => document.querySelector(s);
  const text = (el) => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");

  function readCart() {
    const items = [...document.querySelectorAll("#order_review tr.cart_item, .woocommerce-checkout-review-order-table tr.cart_item")].map((tr) => {
      const cell = tr.querySelector(".product-name");
      const qtyEl = cell && cell.querySelector(".product-quantity");
      const qty = Number(text(qtyEl).replace(/[^0-9]/g, "")) || 1;
      const name = text(cell).replace(text(qtyEl), "").trim();
      return { name, qty, total: AsGuard.money(text(tr.querySelector(".product-total .amount"))) };
    });
    const totalEl = $(".order-total .amount");
    return {
      items,
      subtotal: AsGuard.money(text($(".cart-subtotal .amount"))),
      total: AsGuard.money(text(totalEl)),
      currency: AsGuard.currencyOf(text(totalEl)),
    };
  }

  // Set a value the way a typing person would, so the store's own scripts see it.
  function put(id, value) {
    const el = document.getElementById(id);
    if (!el || value == null || value === "") return false;
    if (el.tagName === "SELECT") {
      const want = String(value).toLowerCase();
      const opt = [...el.options].find((o) => o.value.toLowerCase() === want || o.text.trim().toLowerCase() === want);
      if (!opt) return false;
      el.value = opt.value;
    } else {
      const setter = Object.getOwnPropertyDescriptor(el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, "value").set;
      setter.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  async function fill(p) {
    const missed = [];
    const f = (id, v, label) => {
      if (v && !put(id, v)) missed.push(label);
    };
    f("billing_email", p.email, "email");
    f("billing_first_name", p.first, "first name");
    f("billing_last_name", p.last, "last name");
    f("billing_country", p.country, "country");
    await wait(400); // the store swaps the state field after the country changes
    f("billing_address_1", p.address1, "address");
    f("billing_address_2", p.address2, "address line 2");
    f("billing_city", p.city, "city");
    f("billing_state", p.state, "state or province");
    f("billing_postcode", p.postcode, "postcode");
    f("billing_phone", p.phone, "phone");
    const ship = document.getElementById("ship-to-different-address-checkbox");
    if (ship && ship.checked) missed.push("a different shipping address is ticked; fill it yourself");
    const pay = document.getElementById(site.pay);
    if (pay && !pay.checked) pay.click();
    if (!pay) missed.push(`${site.payName} is not offered on this page`);
    if (site.coin) {
      await wait(300); // the coin list sits in the payment box that opens on click
      if (!put(site.coin.id, site.coin.value)) missed.push(`coin ${site.coin.name}`);
    }
    return missed;
  }

  let state = { order: null, profile: null, filled: false, missed: [] };

  function draw() {
    const cart = readCart();
    const lines = AsGuard.cart(state.order, cart);
    const pay = document.getElementById(site.pay);
    const coinEl = site.coin && document.getElementById(site.coin.id);
    const coin = coinEl ? coinEl.value : "";
    if (state.filled) {
      lines.push(pay && pay.checked ? { ok: true, text: `Payment: ${site.payName}` } : { ok: false, text: `Payment is not ${site.payName}` });
      if (coinEl) {
        const label = text(coinEl.selectedOptions[0]);
        lines.push(coin === site.coin.value ? { ok: true, text: `Coin: ${label}` } : { ok: null, text: `Coin: ${label}. You changed it; pay only on that network.` });
      }
    }
    // Kept for the payment check on the next page; only totals and the coin, no personal data.
    chrome.storage.local.set({ checkout: { merchant: MERCHANT, total: cart.total, currency: cart.currency, coin, at: new Date().toISOString() } });

    const parts = [{ title: "Cart check", lines }];
    if (!state.profile) {
      parts.push({ text: "Save your delivery details in the extension first. They stay in this browser.", muted: true });
      parts.push({ button: "Open delivery details", onClick: () => chrome.runtime.openOptionsPage && chrome.runtime.openOptionsPage() });
    } else if (!state.filled) {
      parts.push({ button: "Fill delivery details", onClick: run });
    } else {
      if (state.missed.length) parts.push({ lines: state.missed.map((m) => ({ ok: null, text: `Not filled: ${m}` })), noVerdict: true });
      parts.push({ text: site.yourPart });
      if (site.password && document.getElementById("account_password"))
        parts.push({ button: "Show the password field", secondary: true, onClick: () => focusOn("account_password") });
    }
    AsPanel.render(parts);
  }

  function focusOn(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.style.outline = "3px solid #c98a12";
    el.focus();
  }

  async function run() {
    state.missed = await fill(state.profile);
    state.filled = true;
    draw();
  }

  chrome.storage.local.get(["order", "profile"], (r) => {
    // An order older than a day is probably not this one.
    state.order = r.order && Date.now() - Date.parse(r.order.at) < 864e5 ? r.order : null;
    state.profile = r.profile || null;
    draw();
  });
  chrome.storage.onChanged.addListener((ch) => {
    if (ch.profile) state.profile = ch.profile.newValue || null;
    if (ch.order) state.order = ch.order.newValue || null;
    if (ch.profile || ch.order) draw();
  });
  // The store redraws the order table after every address or shipping change.
  let t;
  const review = $("#order_review") || form;
  new MutationObserver(() => {
    clearTimeout(t);
    t = setTimeout(draw, 300);
  }).observe(review, { childList: true, subtree: true });
})();
