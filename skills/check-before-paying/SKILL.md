---
name: check-before-paying
description: Use before paying for, ordering or checking out anything on a person's behalf. Checks the cart against the person's request with the AsAsked check_order tool and asks the person when they don't match.
---

Before you pay for anything on a person's behalf:

1. Call the `check_order` tool from the `asasked` server. Pass the person's request in their own words, exactly as they wrote it, and the cart you are about to pay for: name, brand, color, size, price of one item, quantity and anything else the shop shows.
2. If the decision is `proceed`, go ahead.
3. If the decision is `ask`, do not pay. Show the person the `question` as it is and wait for their answer. Then call `check_order` again with the same request, the cart you now intend to buy, and every question and answer so far in `answers`.
4. `notes` are things that could not be checked because the shop didn't say. Tell the person about the ones that matter.

Never rewrite or shorten the person's request before you pass it, and never pay while the last decision is `ask`.
