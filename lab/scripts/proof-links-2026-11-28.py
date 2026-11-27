#!/usr/bin/env python3
# Writes proof links (found 2026-11-28) into ../research/merchants.csv, column verified_how.
# NOT run yet: needs the owner's OK, because merchants.csv is shared with other sessions.
# Makes a backup merchants.csv.bak-proof-2026-11-28 first. Changes only the rows listed below.
# Run:  python3 scripts/proof-links-2026-11-28.py          (dry run, prints what would change)
#       python3 scripts/proof-links-2026-11-28.py --write  (writes)
import csv, shutil, sys, os
D = "2026-11-28"
LINKS = {
 "bitrefill.com": "https://docs.bitrefill.com/docs/crypto-payments — crypto payments: BTC, USDC and more",
 "bottegasenatore.com": "https://www.bottegasenatore.com/faq/ — FAQ: cryptocurrency via BitPay",
 "bullionexchanges.com": "https://bullionexchanges.com/terms-conditions — terms: cryptocurrency via BitPay",
 "capucinne.com": "https://www.capucinne.com/pages/buy-jewelry-with-crypto-cryptocurrency-bitcoin-ethereum — BTC, ETH, USDC",
 "coincards.com": "https://coincards.com/frequently-asked-questions/#cc-faq-payment-methods — FAQ: Bitcoin on-chain and Lightning",
 "djkit.com": "https://www.djkit.com/blogs/news/drop-the-bass-not-your-cash-djkit-now-accepts-usdc-payments — USDC at checkout",
 "hostkey.com": "https://hostkey.com/dedicated-servers/bitcoin/ — crypto via BitPay",
 "jasboutique.co.uk": "https://www.jasboutique.co.uk/cryptocurrency/ — BitPay: BTC, ETH",
 "leibish.com": "https://www.leibish.com/pages/leibish-cryptocurrency-payment-policy — crypto via BitPay, online orders",
 "lindaslook.com": "https://lindaslook.com/pages/pay-with-usdc-cryptocurrency-at-checkout — USDC on Base at checkout",
 "littlewildkid.store": "https://littlewildkid.store/pages/faq — FAQ: USDC accepted",
 "maingear.com": "https://help.maingear.com/article/13-does-maingear-accept-bitcoin — BTC, ETH, USDC",
 "mukorombolt.hu": "https://mukorombolt.hu/en/blogs/hirek/uj-fizetesi-lehetoseg-usdc-kriptovaluta — new payment option: USDC",
 "plusshop.ca": "https://plusshop.ca/pages/bitpayplus — BitPay page",
 "providentmetals.com": "https://help.providentmetals.com/article/261-how-do-i-pay-with-bitcoin — Bitcoin via BitPay",
 "qeeq.com": "https://m.qeeq.com/rent-a-car-with-bitcoin — BTC, BCH, ETH, XRP, stablecoins",
 "raydin.store": "https://raydin.store/pages/articles — now accepting USDC",
 "safari-guru.com": "https://safari-guru.com/2021/11/18/the-next-generation-of-safari-bookings/ — payments via BitPay (page from 2021)",
 "sharpspixley.com": "https://www.sharpspixley.com/buy-gold-with-cryptocurrency — Bitcoin via BitPay",
 "simply-jet.ch": "https://simply-jet.ch/en/crypto-payments — cryptocurrency via BitPay",
 "truefacet.com": "https://www.truefacet.com/bitpay-terms — checkout with crypto via BitPay",
 "shopvoltvault.com": "https://shopvoltvault.com/pay-with-usdc — USDC on Base, Ethereum, Solana",
 "wristaficionado.com": "https://wristaficionado.com/pages/bitpay — now accepting BitPay",
}
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.normpath(os.path.join(here, "..", "..", "research", "merchants.csv"))
rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
fields = list(rows[0].keys())
seen, changed = set(), 0
for r in rows:
    new = LINKS.get(r["domain"])
    if not new: continue
    seen.add(r["domain"])
    val = f"{new}; {D}"
    if r["verified_how"] != val:
        print(f"{r['domain']}\n  was: {r['verified_how']}\n  now: {val}")
        r["verified_how"] = val; changed += 1
missing = sorted(set(LINKS) - seen)
if missing: print("not in csv:", ", ".join(missing))
print(f"{changed} rows to change")
if "--write" in sys.argv and changed:
    shutil.copy2(path, path + ".bak-proof-2026-11-28")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    print("written; backup", path + ".bak-proof-2026-11-28")
